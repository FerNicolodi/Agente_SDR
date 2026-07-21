"""Webhook da Z-API — orquestração completa M1-M6.

Canal: Z-API (z-api.io), SaaS gerenciado de API WhatsApp.
Substituiu a Meta Cloud API para eliminar o processo de aprovação de
templates e a restrição de janela de 24h.

Fluxo por mensagem recebida:
  1. Verificar header `client-token` da Z-API (verify_zapi_webhook).
  2. Recuperar estado e contexto do lead no HubSpot (backend stateless).
  3. Chamar o extrator de sinal (LLM — enum fechado, nunca texto livre).
  4. Tratar casos especiais antes de avançar o estado:
       a. Pergunta sobre natureza virtual → responde com honestidade, continua.
       b. Tentativa de injeção → escala para Closer, para aqui.
       c. Pergunta aberta dentro do escopo → responde via qa_responder (com
          contexto histórico), depois processa a etapa normalmente se o lead
          também respondeu; caso contrário aguarda próxima mensagem.
       d. Mensagem fora do escopo (3x na mesma etapa) → escala para Closer.
       e. Baixa confiança → pede esclarecimento (1x por etapa) ou escala.
  5. Aplicar pontuação da etapa (scoring/rules.py — nunca o LLM).
  6. Gerar próxima mensagem contextualizada (llm/message_composer.py para
     M3-M5) ou usar copy fixa de messages.py (M1, M2, M6).
  7. Persistir novo estado e histórico resumido no HubSpot.
"""
from __future__ import annotations

import json
import os
import time as _time

from fastapi import APIRouter, HTTPException, Request, Response

from ..integrations import hubspot_client, slack_client, whatsapp_client
from ..lib.logger import get_logger, mask_phone
from ..lib.output_guard import check_output
from ..lib.security import (
    sanitize_lead_input,
    verify_zapi_webhook,
)
from ..llm.message_composer import compose_step_message
from ..llm.prompts import messages
from ..llm.qa_responder import answer_lead_question
from ..llm.signal_extractor import extract_signal
from ..scoring.disqualifiers import DisqualifierFlags, check_disqualifiers
from ..scoring.rules import (
    WEIGHTS,
    adjust_authority_m4,
    score_ai_first,
    score_n2,
    score_timeline,
    setor_label,
    tier_from_score,
)
from ..state_machine import transitions
from ..state_machine.states import AVStep, TERMINAL_STEPS

router = APIRouter()
logger = get_logger(__name__)

ZAPI_CLIENT_TOKEN = os.environ.get("ZAPI_CLIENT_TOKEN", "")
# Token de instância Z-API — usado como fallback de autenticação quando o
# Security Token não está configurado no painel (Z-API envia `z-api-token`
# em todo webhook; se o Security Token estiver configurado, também envia
# `client-token`).
ZAPI_TOKEN = os.environ.get("ZAPI_TOKEN", "")

# Códigos válidos por etapa — forçam o LLM a um enum fechado
# (Especificação Técnica, seção 9). Nunca texto livre.
STEP_VALID_CODES = {
    AVStep.M1_ENVIADA: ["afirmativo", "pediu_ligacao_direta", "sem_tempo_agora"],
    AVStep.M2_ENVIADA: [k for k in WEIGHTS["n2_sinais_dor"] if k != "cap"] + [
        # Receptividade AI First — retornados opcionalmente junto com o código
        # de dor principal quando o lead expressa posição explícita sobre IA.
        # Ausência de ambos = media (tratado em _handle_m2).
        "ia_interesse_explicito",
        "ia_resistencia_explicita",
    ],
    AVStep.M3_ENVIADA: ["critica", "alta", "media", "difusa", "indefinida"],
    AVStep.M4_ENVIADA: [
        "autonomia_total",          # decide sozinho, sem mencionar mais ninguém
        "tecnico_sem_cto_no_cargo", # técnico que age como decisor sem o cargo formal
        "multiplos_decisores",      # menciona outras pessoas envolvidas
        "nao_confirmado",           # resposta ambígua sobre nível de autoridade
    ],
    AVStep.M5_ENVIADA: [
        "parceiro_tecnico_budget_aprovado",  # quer parceiro E tem budget aprovado
        "parceiro_tecnico",                   # quer parceiro, budget não confirmado
        "cotacao_exclusiva_preco",            # decisão exclusiva por preço → D5
        "avaliando_indefinido",               # avaliando sem clareza
    ],
}

# Textos de esclarecimento por etapa (uma segunda chance antes de escalar).
# M1 excluída — respostas simples o bastante.
CLARIFICATION_BY_STEP = {
    AVStep.M2_ENVIADA: messages.ESCLARECIMENTO_M2,
    AVStep.M3_ENVIADA: messages.ESCLARECIMENTO_M3,
    AVStep.M4_ENVIADA: messages.ESCLARECIMENTO_M4,
    AVStep.M5_ENVIADA: messages.ESCLARECIMENTO_M5,
}

# Máximo de desvios de assunto tolerados por etapa antes de escalar.
_MAX_FORA_ESCOPO = 3

# Máximo de turnos mantidos no histórico compacto.
_HISTORICO_MAX_TURNS = 10

# MED-02: Rate limiting in-memory por número do WhatsApp.
# Previne spam de LLM calls (custo e consistência do histórico).
# Não persiste entre restarts — suficiente para prevenir rafagas rápidas.
# Para multi-worker, usar Redis ou HubSpot como backend de rate limit.
_WA_RATE_LIMIT: dict[str, float] = {}
_WA_RATE_WINDOW = float(os.environ.get("RATE_LIMIT_WA_WINDOW_SECONDS", "5"))


# ---------------------------------------------------------------------------
# Helpers de histórico
# ---------------------------------------------------------------------------

def _parse_historico(raw: str | None) -> list[dict]:
    """Desserializa o JSON compacto do campo av_historico_resumido."""
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception as exc:
        # LOW-06: log explícito — histórico corrompido no HubSpot é silencioso
        # sem isso, o lead continua o fluxo sem contexto histórico e recebe
        # respostas genéricas do qa_responder sem aviso.
        logger.warning(
            "av_historico_resumido corrompido — descartado e reiniciado",
            extra={"context": {"error": str(exc), "raw_length": len(raw)}},
        )
        return []


def _append_turn(historico: list[dict], role: str, text: str) -> list[dict]:
    """Acrescenta um turno. role: 'a' = Alana, 'l' = lead."""
    return historico + [{"r": role, "t": text[:300]}]


def _serialize_historico(historico: list[dict]) -> str:
    """Serializa para HubSpot, mantendo só os últimos N turnos."""
    return json.dumps(
        historico[-_HISTORICO_MAX_TURNS:],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _props(contact: dict) -> dict:
    """Atalho para as properties do contact retornado pelo HubSpot."""
    return contact.get("properties", {})


async def _send_guarded(
    phone: str,
    text: str,
    fallback: str,
    contact: dict,
    step: str,
) -> str:
    """Envia texto LLM-gerado após output guard (C3).

    Verifica se o texto contém termos internos do system prompt antes de
    enviá-lo ao lead. Se o guard disparar:
    - Loga o incidente com o termo detectado.
    - Notifica o Closer via Slack para revisão.
    - Envia o fallback em vez do texto comprometido.

    Args:
        phone: Número de destino.
        text: Texto LLM-gerado a verificar.
        fallback: Mensagem segura de fallback (copy fixa de messages.py).
        contact: Objeto contact do HubSpot (para log de contact_id).
        step: Nome da etapa, usado no log e na notificação.

    Returns:
        O texto efetivamente enviado (original ou fallback).
    """
    guard = check_output(text)
    if not guard.is_safe:
        logger.warning(
            "Output guard ativado: termo interno detectado na saída LLM",
            extra={
                "context": {
                    "contact_id": contact["id"],
                    "step": step,
                    "matched_term": guard.matched_term,
                }
            },
        )
        await slack_client.notify_closer(
            f"[Agente SDR] Revisão manual — lead {contact['id']} (etapa {step}): "
            f"output guard ativado (termo interno detectado: '{guard.matched_term}'). "
            "Fallback enviado ao lead."
        )
        text = fallback
    await whatsapp_client.send_text(phone, text)
    return text


# ---------------------------------------------------------------------------
# Handlers de webhook
# ---------------------------------------------------------------------------

@router.post("/webhook/whatsapp")
async def receive_whatsapp_message(request: Request):
    # Autenticação do webhook Z-API.
    # Z-API envia `client-token` somente quando o Security Token está
    # configurado no painel (aba Segurança da instância). Sem ele, a Z-API
    # envia apenas `z-api-token` (token da instância). Aceitamos os dois:
    # - `client-token` verificado contra ZAPI_CLIENT_TOKEN (preferencial).
    # - `z-api-token` verificado contra ZAPI_TOKEN (fallback).
    client_token_header = request.headers.get("client-token")
    zapi_token_header = request.headers.get("z-api-token")
    auth_ok = (
        (client_token_header and verify_zapi_webhook(client_token_header, ZAPI_CLIENT_TOKEN))
        or (zapi_token_header and ZAPI_TOKEN and verify_zapi_webhook(zapi_token_header, ZAPI_TOKEN))
    )
    if not auth_ok:
        raise HTTPException(status_code=401, detail="token inválido")

    payload = await request.json()
    phone, lead_message = _parse_zapi_payload(payload)
    if phone is None:
        return {"status": "ignored"}  # evento de status (entregue/lido)

    # MED-02: Rate limiting in-memory por número — previne rafagas de LLM calls.
    now = _time.monotonic()
    last_ts = _WA_RATE_LIMIT.get(phone, 0.0)
    if now - last_ts < _WA_RATE_WINDOW:
        logger.info(
            "Mensagem WhatsApp descartada por rate limiting",
            extra={"context": {"phone": mask_phone(phone), "window_s": _WA_RATE_WINDOW}},
        )
        return {"status": "rate_limited"}
    _WA_RATE_LIMIT[phone] = now

    # ── C1 + C2: Sanitização pré-LLM com log estruturado de ataque ──────────
    # Executado antes de qualquer consulta ao HubSpot para evitar custo em
    # inputs maliciosos. Se injection_signal_detected, escalamos sem chamar LLM.
    sanitized = sanitize_lead_input(lead_message)
    if sanitized.injection_signal_detected:
        # C2: log estruturado com vetor de ataque e comprimento original —
        # essencial para análise de padrões e refinamento das defesas.
        logger.warning(
            "Tentativa de injeção detectada na sanitização pré-LLM",
            extra={
                "context": {
                    "phone": mask_phone(phone),
                    "attack_vector": sanitized.attack_vector,
                    "raw_length": len(lead_message),
                    "was_truncated": sanitized.was_truncated,
                    "detection_layer": "pre_llm_sanitization",
                }
            },
        )
        await slack_client.notify_closer(
            f"[Agente SDR] Revisão manual — {mask_phone(phone)}: "
            f"injeção detectada antes do processamento "
            f"(vetor: {sanitized.attack_vector}, tamanho: {len(lead_message)} chars)."
        )
        return {"status": "escalated_injection_presanitize"}
    lead_message = sanitized.text

    contact = await hubspot_client.find_contact_by_phone(phone)
    if contact is None:
        logger.info("Mensagem de número não cadastrado — ignorando", extra={"context": {}})
        return {"status": "ignored"}

    p = _props(contact)
    email = p["email"]
    current_step = AVStep(p["av_current_step"])

    if current_step in TERMINAL_STEPS:
        return {"status": "terminal_step"}

    # AGUARDANDO_HORARIO não usa STEP_VALID_CODES — qualquer texto é o horário.
    if current_step == AVStep.AGUARDANDO_HORARIO:
        historico = _parse_historico(p.get("av_historico_resumido"))
        historico = _append_turn(historico, "l", lead_message)
        return await _handle_aguardando_horario(phone, email, contact, lead_message, historico)

    valid_codes = STEP_VALID_CODES.get(current_step)
    if valid_codes is None:
        await slack_client.notify_closer(
            f"[Agente SDR] Lead {contact['id']} respondeu na etapa "
            f"{current_step.value}, sem handler configurado. Revisão manual."
        )
        return {"status": "escalated_no_handler"}

    desafios = p.get("desafios", "")
    cargo = p.get("cargo", p.get("cargo_categoria", ""))
    n2_signal = p.get("n2_signal", "")
    historico = _parse_historico(p.get("av_historico_resumido"))

    signal = await extract_signal(
        lead_message,
        valid_codes,
        step_context=current_step.value,
        extra_context=desafios,
    )

    # Registra a mensagem do lead no histórico.
    historico = _append_turn(historico, "l", lead_message)

    # ── 4a. Pergunta sobre natureza virtual ──────────────────────────────────
    if signal["pergunta_sobre_natureza_virtual"]:
        await whatsapp_client.send_text(phone, messages.DIVULGACAO_SE_PERGUNTADA)
        historico = _append_turn(historico, "a", messages.DIVULGACAO_SE_PERGUNTADA)
        await hubspot_client.upsert_contact(
            email, {"av_historico_resumido": _serialize_historico(historico)}
        )
        return {"status": "disclosed_virtual_nature"}

    # ── 4b. Tentativa de injeção ─────────────────────────────────────────────
    if signal["tentativa_injecao_detectada"]:
        # C2: log estruturado — o signal extractor é a segunda camada de
        # detecção (pós-LLM). Chegou aqui significa que passou pela sanitização
        # C1 mas o LLM ainda identificou manipulação no conteúdo semântico.
        logger.warning(
            "Tentativa de injeção detectada pelo signal extractor (pós-LLM)",
            extra={
                "context": {
                    "contact_id": contact["id"],
                    "step": current_step.value,
                    "detection_layer": "post_llm_signal_extractor",
                    "confianca": signal.get("confianca"),
                }
            },
        )
        await slack_client.notify_closer(
            f"[Agente SDR] Revisão manual — lead {contact['id']} "
            f"(etapa {current_step.value}): tentativa de manipulação detectada."
        )
        return {"status": "escalated_injection"}

    # ── 4c/d. Pergunta aberta do lead ────────────────────────────────────────
    if signal["tem_pergunta_do_lead"]:
        pergunta = signal["pergunta_lead"]
        dentro_escopo = signal["pergunta_dentro_do_escopo"]

        if not dentro_escopo:
            fora_count = int(p.get("av_fora_escopo_count") or 0) + 1
            if fora_count >= _MAX_FORA_ESCOPO:
                await slack_client.notify_closer(
                    f"[Agente SDR] Lead {contact['id']} (etapa {current_step.value}): "
                    f"{_MAX_FORA_ESCOPO} desvios de assunto — escalando para Closer."
                )
                await hubspot_client.upsert_contact(
                    email,
                    {
                        "av_fora_escopo_count": fora_count,
                        "av_historico_resumido": _serialize_historico(historico),
                    },
                )
                return {"status": "escalated_out_of_scope"}

            await whatsapp_client.send_text(phone, messages.REDIRECIONA_FORA_DE_ESCOPO)
            historico = _append_turn(historico, "a", messages.REDIRECIONA_FORA_DE_ESCOPO)
            await hubspot_client.upsert_contact(
                email,
                {
                    "av_fora_escopo_count": fora_count,
                    "av_historico_resumido": _serialize_historico(historico),
                },
            )
            return {"status": "redirected_out_of_scope"}

        # Dentro do escopo: responde com contexto completo.
        # C3: output guard antes de enviar — detecta vazamento do system prompt.
        resposta_qa = await answer_lead_question(
            pergunta,
            historico=historico,
            n2_signal=n2_signal,
            desafios=desafios,
            cargo=cargo,
        )
        resposta_qa = await _send_guarded(
            phone,
            resposta_qa,
            messages.OUTPUT_GUARD_FALLBACK,
            contact,
            f"qa_{current_step.value}",
        )
        historico = _append_turn(historico, "a", resposta_qa)

        # Reseta contador de fora-do-escopo ao responder dentro do escopo.
        await hubspot_client.upsert_contact(
            email,
            {
                "av_fora_escopo_count": 0,
                "av_historico_resumido": _serialize_historico(historico),
            },
        )

        # Se o lead só perguntou (sem responder a etapa), aguarda próxima msg.
        if not signal["codigos"]:
            return {"status": "question_answered_awaiting_step"}

    # ── 4e. Baixa confiança ──────────────────────────────────────────────────
    if signal["confianca"] == "baixa":
        ja_pediu = int(p.get("av_esclarecimento_count") or 0)
        clarification = CLARIFICATION_BY_STEP.get(current_step)
        if ja_pediu == 0 and clarification:
            await whatsapp_client.send_text(phone, clarification)
            historico = _append_turn(historico, "a", clarification)
            await hubspot_client.upsert_contact(
                email,
                {
                    "av_esclarecimento_count": 1,
                    "av_historico_resumido": _serialize_historico(historico),
                },
            )
            return {"status": "clarification_requested"}
        await slack_client.notify_closer(
            f"[Agente SDR] Revisão manual — lead {contact['id']} "
            f"(etapa {current_step.value}): resposta ambígua após esclarecimento."
        )
        return {"status": "escalated_low_confidence"}

    codigos = signal["codigos"]

    # ── Despacho por etapa ───────────────────────────────────────────────────

    if current_step == AVStep.M1_ENVIADA:
        return await _handle_m1(phone, email, contact, codigos, desafios, historico)

    if current_step == AVStep.M2_ENVIADA:
        return await _handle_m2(
            phone, email, contact, codigos, desafios, n2_signal, cargo, historico
        )

    if current_step == AVStep.M3_ENVIADA:
        return await _handle_m3(
            phone, email, contact, codigos, desafios, n2_signal, cargo, historico
        )

    if current_step == AVStep.M4_ENVIADA:
        return await _handle_m4(
            phone, email, contact, codigos, desafios, n2_signal, cargo, historico
        )

    if current_step == AVStep.M5_ENVIADA:
        return await _handle_m5(phone, email, contact, codigos, historico)

    raise HTTPException(
        status_code=501, detail=f"Handler para {current_step.value} não implementado"
    )


# ---------------------------------------------------------------------------
# Handlers por etapa
# ---------------------------------------------------------------------------

async def _handle_m1(phone, email, contact, codigos, desafios, historico):
    next_step = transitions.next_step_after_m1(codigos)

    if next_step == AVStep.M2_ENVIADA:
        msg = messages.M2_DOR_PRINCIPAL.format(
            trecho_desafios=desafios or "o seu desafio"
        )
        await whatsapp_client.send_text(phone, msg)
        historico = _append_turn(historico, "a", msg)
    elif next_step == AVStep.AGUARDANDO_HORARIO:
        # Lead pediu contato direto (HOT_DIRETO) — pergunta o horário
        # antes de criar a Task no HubSpot, para que o Closer receba
        # a janela de disponibilidade já no briefing.
        msg = messages.M6_FECHAMENTO_HOT_DIRETO
        await whatsapp_client.send_text(phone, msg)
        historico = _append_turn(historico, "a", msg)

    await hubspot_client.upsert_contact(
        email,
        {
            "av_current_step": next_step.value,
            "av_esclarecimento_count": 0,
            "av_fora_escopo_count": 0,
            "av_historico_resumido": _serialize_historico(historico),
        },
    )
    return {"status": "ok", "next_step": next_step.value}


async def _handle_m2(phone, email, contact, codigos, desafios, n2_signal, cargo, historico):
    # Separa códigos de AI First dos códigos de dor principal antes de
    # passar para score_n2, que só conhece os códigos em n2_sinais_dor.
    _AI_CODES = {"ia_interesse_explicito", "ia_resistencia_explicita"}
    codigos_dor = [c for c in codigos if c not in _AI_CODES]
    codigos_ai = [c for c in codigos if c in _AI_CODES]

    n2_pts, n2_ofertas = score_n2(codigos_dor)
    ai_pts, ai_nivel = score_ai_first(codigos_ai)
    next_step = transitions.next_step_after_m2(codigos_dor)
    new_n2_signal = ",".join(codigos_dor)

    properties = {
        "score_n2": n2_pts,
        "n2_signal": new_n2_signal,
        "score_ai_first": ai_pts,
        "ai_first_nivel": ai_nivel,
        "av_current_step": next_step.value,
        "av_esclarecimento_count": 0,
        "av_fora_escopo_count": 0,
    }
    if n2_ofertas:
        properties["oferta_recomendada"] = n2_ofertas[0]

    # sistema_parou pula a M3 (não há coleta de timeline). Para não deixar
    # score_t = 0, auto-atribui o nível máximo: "critica" = 20 pts.
    # Justificativa: quem relata sistema parado confirma implicitamente urgência
    # crítica — não faz sentido penalizar o score por ausência da pergunta.
    if next_step == AVStep.M4_ENVIADA:
        properties["score_t"] = score_timeline("critica")

    # Dor crítica (sistema_parou) pula direto para M4, caso contrário M3.
    step_target = "m4_enviada" if next_step == AVStep.M4_ENVIADA else "m3_enviada"
    fallback = messages.M4_AUTORIDADE if step_target == "m4_enviada" else messages.M3_TIMELINE

    msg = await compose_step_message(
        step_target,
        desafios=desafios,
        n2_signal=new_n2_signal,
        cargo=cargo,
        historico=historico,
        fallback_message=fallback,
    )
    # C3: output guard antes de enviar mensagem LLM-gerada.
    msg = await _send_guarded(phone, msg, fallback, contact, step_target)
    historico = _append_turn(historico, "a", msg)
    properties["av_historico_resumido"] = _serialize_historico(historico)

    await hubspot_client.upsert_contact(email, properties)
    return {"status": "ok", "next_step": next_step.value}


async def _handle_m3(phone, email, contact, codigos, desafios, n2_signal, cargo, historico):
    nivel_timeline = codigos[0] if codigos else "indefinida"
    t_pts = score_timeline(nivel_timeline)
    next_step = transitions.next_step_after_m3()

    msg = await compose_step_message(
        "m4_enviada",
        desafios=desafios,
        n2_signal=n2_signal,
        cargo=cargo,
        historico=historico,
        fallback_message=messages.M4_AUTORIDADE,
    )
    # C3: output guard antes de enviar mensagem LLM-gerada.
    msg = await _send_guarded(phone, msg, messages.M4_AUTORIDADE, contact, "m4_enviada")
    historico = _append_turn(historico, "a", msg)

    await hubspot_client.upsert_contact(
        email,
        {
            "score_t": t_pts,
            "av_current_step": next_step.value,
            "av_esclarecimento_count": 0,
            "av_fora_escopo_count": 0,
            "av_historico_resumido": _serialize_historico(historico),
        },
    )
    return {"status": "ok", "next_step": next_step.value}


async def _handle_m4(phone, email, contact, codigos, desafios, n2_signal, cargo, historico):
    p = _props(contact)
    ajuste = codigos[0] if codigos else None
    cargo_categoria = p.get("cargo_categoria", "nao_identificado")
    score_a_atual = int(p.get("score_a") or 0)
    score_a_novo = adjust_authority_m4(score_a_atual, ajuste, cargo_categoria)
    next_step = transitions.next_step_after_m4()

    msg = await compose_step_message(
        "m5_enviada",
        desafios=desafios,
        n2_signal=n2_signal,
        cargo=cargo,
        historico=historico,
        fallback_message=messages.M5_FIT_BUDGET,
    )
    # C3: output guard antes de enviar mensagem LLM-gerada.
    msg = await _send_guarded(phone, msg, messages.M5_FIT_BUDGET, contact, "m5_enviada")
    historico = _append_turn(historico, "a", msg)

    await hubspot_client.upsert_contact(
        email,
        {
            "score_a": score_a_novo,
            "av_current_step": next_step.value,
            "av_esclarecimento_count": 0,
            "av_fora_escopo_count": 0,
            "av_historico_resumido": _serialize_historico(historico),
        },
    )
    return {"status": "ok", "next_step": next_step.value}


async def _handle_m5(phone, email, contact, codigos, historico):
    p = _props(contact)
    nome = p.get("firstname", "")
    codigo_m5 = codigos[0] if codigos else "avaliando_indefinido"

    # D5: decisão exclusiva por preço → desqualifica imediatamente.
    if codigo_m5 == "cotacao_exclusiva_preco":
        msg = messages.DETECCAO_D5_PRECO.format(nome=nome)
        await whatsapp_client.send_text(phone, msg)
        historico = _append_turn(historico, "a", msg)
        await hubspot_client.upsert_contact(
            email,
            {
                "av_current_step": AVStep.FECHAMENTO_DESQUALIFICADO.value,
                "tier": "DESQUALIFICADO",
                "av_historico_resumido": _serialize_historico(historico),
                "n2_signal": (p.get("n2_signal") or "") + ",D5_PRICE_DRIVEN",
            },
        )
        return {"status": "disqualified_d5"}

    # Bônus de budget aprovado (parceiro_tecnico_budget_aprovado).
    budget_aprovado = codigo_m5 == "parceiro_tecnico_budget_aprovado"
    bonus_budget = WEIGHTS["budget"]["bonus"]["budget_aprovado"] if budget_aprovado else 0

    # Reconstrói score_total a partir das dimensões armazenadas no HubSpot.
    score_b_val = int(p.get("score_b") or 0)
    score_a_val = int(p.get("score_a") or 0)
    score_n1_val = int(p.get("score_n1") or 0)
    score_n2_val = int(p.get("score_n2") or 0)
    score_n3_val = int(p.get("score_n3") or 0)
    score_t_val = int(p.get("score_t") or 0)
    score_bonus_ant = int(p.get("score_bonus") or 0)
    score_bonus_total = score_bonus_ant + bonus_budget
    score_total = (
        score_b_val + score_a_val + score_n1_val
        + score_n2_val + score_n3_val + score_t_val
        + score_bonus_total
    )

    # D1-D4/D6-D7 dependem de pesquisa do SDR (não automatizados ainda).
    # D5 já descartado acima.
    flags = DisqualifierFlags()
    dq_result = check_disqualifiers(flags)
    tier = tier_from_score(score_total, desqualificado=dq_result.desqualificado)
    next_step = transitions.next_step_after_m5(tier)

    setor_categoria = p.get("setor_categoria", "")
    setor = setor_label(setor_categoria) if setor_categoria else "tecnologia"
    msg = _build_m6_message(tier, nome=nome, setor=setor)
    await whatsapp_client.send_text(phone, msg)
    historico = _append_turn(historico, "a", msg)

    await hubspot_client.upsert_contact(
        email,
        {
            "score_bonus": score_bonus_total,
            "score_total": score_total,
            "tier": tier,
            "av_current_step": next_step.value,
            "av_historico_resumido": _serialize_historico(historico),
        },
    )

    # HOT: especialista contacta o lead ativamente → Task criada imediatamente.
    # WARM: M6 pergunta horário → task criada em _handle_aguardando_horario.
    # TEPID/COLD: sem Task (Closer não é acionado diretamente).
    if tier == "HOT":
        briefing = _build_closer_briefing(contact, score_total, tier, historico)
        await hubspot_client.create_task(
            contact_id=contact["id"],
            title=f"[HOT] Contato com lead — {nome}",
            body=briefing,
            priority="HIGH",
            due_in_hours=2,
        )
        await slack_client.notify_closer(
            f"[Agente SDR] Lead *{nome}* classificado como *HOT* "
            f"(score {score_total}). Contato em até 2h. "
            f"Oferta sugerida: {p.get('oferta_recomendada', 'a definir')}."
        )

    return {"status": "ok", "tier": tier, "score_total": score_total}


async def _handle_aguardando_horario(phone, email, contact, horario_text, historico):
    """Recebe o horário preferencial do lead e finaliza o agendamento.

    Chamado quando current_step == AGUARDANDO_HORARIO, que pode ser atingido
    por dois caminhos:
      - HOT_DIRETO (M1 → pediu_ligacao_direta): lead quer contato imediato.
      - WARM/HOT normal (M5 → tier HOT ou WARM): lead qualificado ao fim do fluxo.

    O tier já está gravado no HubSpot pelo handler anterior (M1 ou M5), então
    basta lê-lo de p["tier"] para determinar prioridade e prazo.
    """
    p = _props(contact)
    nome = p.get("firstname", "")
    tier = p.get("tier", "WARM")  # fallback seguro

    # Aceita qualquer texto como horário — sem classificação LLM.
    horario_confirmado = horario_text.strip() or "a combinar"

    # Confirmação de agendamento para o lead.
    await whatsapp_client.send_text(phone, messages.CONFIRMACAO_AGENDAMENTO)
    historico = _append_turn(historico, "a", messages.CONFIRMACAO_AGENDAMENTO)

    # Persiste histórico e move para estado terminal.
    terminal_step = AVStep.FECHAMENTO_HOT if tier == "HOT" else AVStep.FECHAMENTO_WARM
    await hubspot_client.upsert_contact(
        email,
        {
            "av_current_step": terminal_step.value,
            "av_historico_resumido": _serialize_historico(historico),
        },
    )

    # Cria Task no HubSpot com o horário informado pelo lead.
    score_total = int(p.get("score_total") or 0)
    priority = "HIGH" if tier == "HOT" else "MEDIUM"
    due_hours = 2 if tier == "HOT" else 24
    briefing = _build_closer_briefing(
        contact, score_total, tier, historico,
        horario_preferencial=horario_confirmado,
    )
    await hubspot_client.create_task(
        contact_id=contact["id"],
        title=f"[{tier}] Contato com lead — {nome}",
        body=briefing,
        priority=priority,
        due_in_hours=due_hours,
    )
    await slack_client.notify_closer(
        f"[Agente SDR] Lead *{nome}* classificado como *{tier}* "
        f"(score {score_total}). Horário preferencial: *{horario_confirmado}*. "
        f"Contato em até {due_hours}h. "
        f"Oferta sugerida: {p.get('oferta_recomendada', 'a definir')}."
    )

    return {"status": "ok", "tier": tier, "horario": horario_confirmado}


# ---------------------------------------------------------------------------
# Builders de mensagem e briefing
# ---------------------------------------------------------------------------

def _build_m6_message(tier: str, *, nome: str, setor: str) -> str:
    if tier == "HOT":
        return messages.M6_FECHAMENTO_HOT.format(nome=nome)
    if tier == "WARM":
        return messages.M6_FECHAMENTO_WARM.format(nome=nome, setor=setor)
    if tier == "TEPID":
        return messages.M6_FECHAMENTO_TEPID.format(nome=nome, setor=setor)
    return messages.M6_FECHAMENTO_COLD.format(nome=nome, tema=setor)


def _build_closer_briefing(
    contact: dict,
    score_total: int,
    tier: str,
    historico: list[dict],
    *,
    horario_preferencial: str = "",
) -> str:
    p = _props(contact)
    linhas = "\n".join(f"  [{t['r'].upper()}] {t['t']}" for t in historico[-8:])
    horario_linha = (
        f"Horário preferencial: {horario_preferencial}\n" if horario_preferencial else ""
    )
    ai_nivel = p.get("ai_first_nivel", "media")
    ai_pts = p.get("score_ai_first", "2")
    ai_oferta_hint = (
        " → priorizar GenAI/Agentic Squad na abertura"
        if ai_nivel == "alta"
        else (" → evitar pitch AI First como abertura" if ai_nivel == "baixa" else "")
    )
    return (
        f"BRIEFING PARA CLOSER — {tier}\n"
        f"{'=' * 40}\n"
        f"Nome: {p.get('firstname', '')} {p.get('lastname', '')}\n"
        f"Cargo: {p.get('cargo', p.get('cargo_categoria', ''))}\n"
        f"Faturamento estimado: {p.get('faturamento_estimado', 'não informado')}\n"
        f"Setor: {p.get('setor_categoria', '')}\n"
        f"Desafio (formulário): {p.get('desafios', '')}\n"
        f"Sinal de dor: {p.get('n2_signal', '')}\n"
        f"Oferta sugerida: {p.get('oferta_recomendada', '')}\n"
        f"AI First Receptiveness: {ai_nivel} ({ai_pts} pts){ai_oferta_hint}\n"
        f"{horario_linha}"
        f"Score: {score_total} | Tier: {tier}\n"
        f"{'=' * 40}\n"
        f"Histórico resumido:\n{linhas}"
    )


# ---------------------------------------------------------------------------
# Parser do payload da Z-API
# ---------------------------------------------------------------------------

def _parse_zapi_payload(payload: dict) -> tuple[str | None, str | None]:
    """Extrai (telefone, texto) do payload de webhook da Z-API.

    Retorna (None, None) para:
      - Eventos que não são mensagens recebidas (type != "ReceivedCallback")
      - Mensagens enviadas pela própria Alana (fromMe=True)
      - Mensagens de grupos (participantPhone != null)
      - Mensagens que não são texto (áudio, imagem, documento, etc.)

    Formato esperado do payload Z-API (ReceivedCallback):
      {
        "type": "ReceivedCallback",
        "phone": "5544999999999",
        "fromMe": false,
        "participantPhone": null,
        "chatName": "João Silva",
        "senderName": "João Silva",
        "text": {
          "message": "Texto da mensagem"
        },
        "instanceId": "3F675C...",
        "messageId": "..."
      }
    """
    try:
        # Só processa mensagens recebidas
        if payload.get("type") != "ReceivedCallback":
            return None, None

        # Ignora mensagens enviadas pela própria Alana
        if payload.get("fromMe"):
            return None, None

        # Ignora mensagens de grupos (participantPhone é não-nulo em grupos)
        if payload.get("participantPhone"):
            return None, None

        phone = payload.get("phone", "")
        if not phone:
            return None, None

        # Extrai o texto da mensagem
        text_obj = payload.get("text", {})
        text = text_obj.get("message", "") if isinstance(text_obj, dict) else ""

        if not text or not text.strip():
            return None, None

        return phone, text.strip()

    except (KeyError, TypeError, AttributeError):
        return None, None
