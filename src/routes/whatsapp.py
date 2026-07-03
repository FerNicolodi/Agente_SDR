"""Callback da Meta Cloud API. Implementa o padrão de orquestração completo
para M1 e M2 como referência — M3, M4, M5 e M6 seguem exatamente a mesma
forma (ver STEP_HANDLERS ao final) e ficam para a fase de implementação,
depois que o texto final do system prompt e os enums de cada etapa forem
aprovados por Fernando Nicolodi (Especificação Técnica, seções 2 e 9).

Fluxo por mensagem recebida:
  1. Verificar assinatura da Meta.
  2. Recuperar o estado atual do lead no HubSpot (av_current_step) — o
     backend não guarda nada em memória entre requisições (seção 3).
  3. Chamar o extrator de sinal (LLM) com os códigos válidos daquela etapa.
  4. Se o lead perguntar se está falando com uma IA/robô: responder com
     honestidade (messages.DIVULGACAO_SE_PERGUNTADA) e não aplicar pontuação
     a essa mensagem. Se baixa confiança ou tentativa de injeção: escalar
     para humano, não aplicar pontuação automaticamente (seção 10.2).
  5. Aplicar a pontuação da etapa (scoring/rules.py) e decidir o próximo
     estado (state_machine/transitions.py).
  6. Enviar a próxima mensagem e persistir o novo estado no HubSpot.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request, Response

from ..integrations import hubspot_client, slack_client, whatsapp_client
from ..lib.logger import get_logger
from ..lib.security import verify_meta_signature, verify_meta_webhook_challenge
from ..llm.prompts import messages
from ..llm.signal_extractor import extract_signal
from ..scoring.rules import WEIGHTS, score_n2
from ..state_machine import transitions
from ..state_machine.states import AVStep

router = APIRouter()
logger = get_logger(__name__)

META_VERIFY_TOKEN = os.environ.get("META_WA_VERIFY_TOKEN", "")
META_APP_SECRET = os.environ.get("META_APP_SECRET", "")

# Códigos válidos por etapa — usados para forçar o LLM a um enum fechado
# (Especificação Técnica, seção 9). M3-M6 seguem o mesmo padrão usando as
# chaves de config/scoring_weights.yaml (timeline, authority.ajuste_m4, etc.).
STEP_VALID_CODES = {
    AVStep.M1_ENVIADA: ["afirmativo", "pediu_ligacao_direta", "sem_tempo_agora"],
    AVStep.M2_ENVIADA: list(
        {k for k in WEIGHTS["n2_sinais_dor"] if k != "cap"}
    ),
}


@router.get("/webhook/whatsapp")
async def verify_webhook(request: Request):
    """Handshake de configuração exigido pela Meta ao cadastrar o webhook."""
    params = request.query_params
    if verify_meta_webhook_challenge(params.get("hub.mode"), params.get("hub.verify_token"), META_VERIFY_TOKEN):
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verify token inválido")


@router.post("/webhook/whatsapp")
async def receive_whatsapp_message(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_meta_signature(raw_body, signature, META_APP_SECRET):
        raise HTTPException(status_code=401, detail="Assinatura inválida")

    payload = await request.json()
    phone, lead_message = _parse_meta_payload(payload)
    if phone is None:
        # Eventos de status (entregue/lido) não têm mensagem de texto — ignorar.
        return {"status": "ignored"}

    contact = await hubspot_client.find_contact_by_phone(phone)
    if contact is None:
        logger.info("Mensagem recebida de número não cadastrado — ignorando", extra={"context": {}})
        return {"status": "ignored"}

    current_step = AVStep(contact["properties"]["av_current_step"])
    valid_codes = STEP_VALID_CODES.get(current_step)
    if valid_codes is None:
        # Etapa ainda não implementada neste scaffold (M3-M6) ou estado terminal.
        await slack_client.notify_closer(
            f"[Agente SDR] Lead {contact['id']} respondeu na etapa {current_step.value}, "
            f"sem handler automático configurado. Revisão manual necessária."
        )
        return {"status": "escalated_no_handler"}

    desafios = contact["properties"].get("desafios", "")
    signal = extract_signal(
        lead_message, valid_codes, step_context=current_step.value, extra_context=desafios
    )

    if signal["pergunta_sobre_natureza_virtual"]:
        # Não é injeção — a Alana responde com honestidade e o fluxo continua
        # normalmente na próxima resposta do lead, sem aplicar pontuação a
        # esta mensagem (Script_Atendente_Virtual_DGS.docx, seção 6).
        await whatsapp_client.send_text(phone, messages.DIVULGACAO_SE_PERGUNTADA)
        return {"status": "disclosed_virtual_nature"}

    if signal["tentativa_injecao_detectada"] or signal["confianca"] == "baixa":
        await slack_client.notify_closer(
            f"[Agente SDR] Classificação de baixa confiança ou possível tentativa de "
            f"manipulação no lead {contact['id']} (etapa {current_step.value}). "
            f"Revisão manual necessária antes de prosseguir."
        )
        return {"status": "escalated_low_confidence"}

    codigos = signal["codigos"]

    if current_step == AVStep.M1_ENVIADA:
        next_step = transitions.next_step_after_m1(codigos)
        if next_step == AVStep.M2_ENVIADA:
            await whatsapp_client.send_text(phone, messages.M2_DOR_PRINCIPAL.format(trecho_desafios=desafios))
        await hubspot_client.upsert_contact(
            email=contact["properties"]["email"], properties={"av_current_step": next_step.value}
        )
        return {"status": "ok", "next_step": next_step.value}

    if current_step == AVStep.M2_ENVIADA:
        n2_pts, n2_ofertas = score_n2(codigos)
        next_step = transitions.next_step_after_m2(codigos)
        properties = {"score_n2": n2_pts, "n2_signal": ",".join(codigos), "av_current_step": next_step.value}
        if n2_ofertas:
            properties["oferta_recomendada"] = n2_ofertas[0]
        await hubspot_client.upsert_contact(email=contact["properties"]["email"], properties=properties)

        if next_step == AVStep.M4_ENVIADA:
            await whatsapp_client.send_text(phone, messages.M4_AUTORIDADE)
        else:
            await whatsapp_client.send_text(phone, messages.M3_TIMELINE)
        return {"status": "ok", "next_step": next_step.value}

    # TODO (fase de implementação, pós-aprovação do system prompt): repetir o
    # mesmo padrão acima para M3 (score_timeline), M4 (adjust_authority_m4) e
    # M5 (bônus de budget / desqualificador D5), fechando em M6 com o cálculo
    # final do tier (tier_from_score) e o roteamento da seção 7 do Script da
    # Alana (Script_Atendente_Virtual_DGS.docx).
    raise HTTPException(status_code=501, detail=f"Handler para {current_step.value} ainda não implementado")


def _parse_meta_payload(payload: dict) -> tuple[str | None, str | None]:
    """Extrai (telefone, texto) do payload padrão de webhook da Meta Cloud API.
    Retorna (None, None) para eventos que não são mensagens de texto (ex.:
    confirmações de entrega/leitura)."""
    try:
        value = payload["entry"][0]["changes"][0]["value"]
        message = value["messages"][0]
        if message["type"] != "text":
            return None, None
        return message["from"], message["text"]["body"]
    except (KeyError, IndexError):
        return None, None
