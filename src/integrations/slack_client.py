"""Notificação ao Closer via Slack (Especificação Técnica, seção 4).
Requer SLACK_BOT_TOKEN e SLACK_CLOSER_CHANNEL no ambiente.
"""
from __future__ import annotations

import os

import httpx

BASE_URL = "https://slack.com/api/chat.postMessage"


async def notify_closer(briefing_text: str, channel: str | None = None) -> dict:
    """`briefing_text` deve seguir exatamente os campos do protocolo de
    handoff (nome/cargo, empresa/setor, faturamento, score e tier, dor
    principal, urgência, nível decisório, oferta recomendada, horário
    preferencial, origem do lead) — ver Script da Alana
    (Script_Atendente_Virtual_DGS.docx, seção 5).
    """
    payload = {
        "channel": channel or os.environ["SLACK_CLOSER_CHANNEL"],
        "text": briefing_text,
    }
    headers = {
        "Authorization": f"Bearer {os.environ['SLACK_BOT_TOKEN']}",
        "Content-Type": "application/json; charset=utf-8",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(BASE_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Falha ao notificar Slack: {data}")
        return data
