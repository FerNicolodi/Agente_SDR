"""Notificação ao Closer via Slack (Especificação Técnica, seção 4).
Requer SLACK_BOT_TOKEN e SLACK_CLOSER_CHANNEL no ambiente.
"""
from __future__ import annotations

import os
import time

import httpx

from ..lib.logger import get_logger

logger = get_logger(__name__)

BASE_URL = "https://slack.com/api/chat.postMessage"


async def notify_closer(briefing_text: str, channel: str | None = None) -> dict:
    """`briefing_text` deve seguir exatamente os campos do protocolo de
    handoff (nome/cargo, empresa/setor, faturamento, score e tier, dor
    principal, urgência, nível decisório, oferta recomendada, horário
    preferencial, origem do lead) — ver Script da Alana
    (Script_Atendente_Virtual_DGS.docx, seção 5).
    """
    resolved_channel = channel or os.environ["SLACK_CLOSER_CHANNEL"]
    t0 = time.monotonic()
    payload = {
        "channel": resolved_channel,
        "text": briefing_text,
    }
    headers = {
        "Authorization": f"Bearer {os.environ['SLACK_BOT_TOKEN']}",
        "Content-Type": "application/json; charset=utf-8",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(BASE_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(f"Falha ao notificar Slack: {data}")
        logger.info(
            "slack:notify_closer",
            extra={
                "context": {
                    "tool": "slack.notify_closer",
                    "channel": resolved_channel,
                    "status_code": resp.status_code,
                    "slack_ok": data.get("ok"),
                    "duration_ms": round((time.monotonic() - t0) * 1000),
                }
            },
        )
        return data
    except Exception as exc:
        logger.error(
            "slack:notify_closer:error",
            extra={
                "context": {
                    "tool": "slack.notify_closer",
                    "channel": resolved_channel,
                    "error": str(exc),
                    "duration_ms": round((time.monotonic() - t0) * 1000),
                }
            },
        )
        raise
