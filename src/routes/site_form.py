"""Recebe a submissão do formulário do site, calcula o Score de Entrada
(B, A, N2 parcial) e dispara a Mensagem 1 (Especificação Técnica, seção 5,
passos 1-4).

NOTA de design: o campo `cargo_categoria` no payload deve vir de uma lista
fechada no próprio formulário do site (dropdown), não de texto livre — a
pontuação de Authority depende de bater exatamente com uma chave de
config/scoring_weights.yaml. Alinhar isso com o time do site antes do
go-live (ver Especificação Técnica, seção 12).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from ..integrations import hubspot_client, whatsapp_client
from ..lib.logger import get_logger, mask_name, mask_phone
from ..lib.security import verify_hmac_signature, is_rate_limited
from ..scoring.rules import compute_score
from ..state_machine.states import AVStep

router = APIRouter()
logger = get_logger(__name__)

WHATSAPP_M1_TEMPLATE_NAME = os.environ.get("META_WA_M1_TEMPLATE_NAME", "abertura_qualificacao_v1")

REQUIRED_FIELDS = ["nome", "email", "telefone", "cargo_categoria", "faturamento_anual", "desafios"]


@router.post("/webhook/site-form")
async def receive_site_form(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("X-Signature")
    if not verify_hmac_signature(raw_body, signature, os.environ["SITE_FORM_HMAC_SECRET"]):
        raise HTTPException(status_code=401, detail="Assinatura inválida")

    payload = await request.json()
    missing = [f for f in REQUIRED_FIELDS if f not in payload]
    if missing:
        raise HTTPException(status_code=422, detail=f"Campos obrigatórios ausentes: {missing}")

    # Rate limiting: rejeita resubmissão do mesmo e-mail dentro da janela
    # configurada (RATE_LIMIT_WINDOW_SECONDS, padrão 60s). O timestamp é lido
    # do HubSpot — sem estado em memória (Especificação Técnica, seção 3).
    existing = await hubspot_client.find_contact_by_phone(payload.get("telefone", ""))
    if existing:
        last_ts = existing["properties"].get("av_last_submission_at")
        if is_rate_limited(last_ts):
            raise HTTPException(status_code=429, detail="Submissão duplicada — aguarde antes de reenviar")

    logger.info(
        "Novo lead recebido do formulário do site",
        extra={
            "context": {
                "nome": mask_name(payload["nome"]),
                "telefone": mask_phone(payload["telefone"]),
            }
        },
    )

    # Nesta etapa: B e A vêm direto do formulário. N1 (setor) e N3
    # (tecnografia) dependem da pesquisa do SDR e ainda não estão
    # disponíveis. T (timeline) só é confirmado na conversa (M3). N2 usa
    # apenas os sinais que já puderem ser extraídos do texto livre do campo
    # "desafios" nesse momento (ver llm/signal_extractor.py) — se esse
    # pipeline de pré-extração ainda não estiver plugado, o payload pode
    # trazer `n2_signal_codes_form` vazio e o N2 é completado depois na M2.
    breakdown = compute_score(
        faturamento_anual=payload["faturamento_anual"],
        cargo_categoria=payload["cargo_categoria"],
        setor_categoria=payload.get("setor_categoria", "tech_native_sem_projeto"),
        n2_signal_codes=payload.get("n2_signal_codes_form", []),
        n3_signal_codes=[],
        timeline_nivel="indefinida",
    )

    await hubspot_client.upsert_contact(
        email=payload["email"],
        properties={
            # Identificação
            "firstname": payload["nome"],
            "phone": payload["telefone"],
            # Contexto do formulário — salvo para personalização nas M2-M6
            "desafios": payload.get("desafios", ""),
            "cargo_categoria": payload["cargo_categoria"],
            "cargo": payload.get("cargo", payload["cargo_categoria"]),
            "setor_categoria": payload.get("setor_categoria", "tech_native_sem_projeto"),
            "faturamento_estimado": str(payload.get("faturamento_anual", "")),
            # Scores de entrada
            "score_b": breakdown.b,
            "score_a": breakdown.a,
            "score_n1": breakdown.n1,
            "score_n2": breakdown.n2,
            "score_total": breakdown.total,
            # Estado inicial
            "av_current_step": AVStep.AGUARDANDO_M1.value,
            "av_fora_escopo_count": 0,
            "av_esclarecimento_count": 0,
            "av_last_submission_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    await whatsapp_client.send_template(
        to=payload["telefone"],
        template_name=WHATSAPP_M1_TEMPLATE_NAME,
        components=[{"type": "body", "parameters": [{"type": "text", "text": payload["nome"]}]}],
    )

    await hubspot_client.upsert_contact(
        email=payload["email"],
        properties={"av_current_step": AVStep.M1_ENVIADA.value},
    )

    return {"status": "ok"}
