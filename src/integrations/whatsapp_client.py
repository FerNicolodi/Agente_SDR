"""Cliente da Meta WhatsApp Cloud API (canal escolhido — ver Especificação
Técnica, seção 2). Requer META_WA_TOKEN e META_WA_PHONE_NUMBER_ID no
ambiente (.env, nunca commitado — ver seção 10.3).
"""
from __future__ import annotations

import os

import httpx

GRAPH_API_VERSION = "v20.0"


def _base_url() -> str:
    phone_number_id = os.environ["META_WA_PHONE_NUMBER_ID"]
    return f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/messages"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['META_WA_TOKEN']}",
        "Content-Type": "application/json",
    }


async def send_template(to: str, template_name: str, language_code: str = "pt_BR", components: list | None = None) -> dict:
    """Envia uma mensagem de template pré-aprovada pela Meta. Obrigatório para
    a Mensagem 1 — é a empresa que inicia a conversa, não o lead (ver
    Especificação Técnica, seção 5, passo 4)."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            **({"components": components} if components else {}),
        },
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(_base_url(), headers=_headers(), json=payload)
        resp.raise_for_status()
        return resp.json()


async def send_text(to: str, body: str) -> dict:
    """Mensagens de texto livre — só permitido dentro da janela de 24h aberta
    pela última resposta do lead (regra da própria Meta)."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body},
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(_base_url(), headers=_headers(), json=payload)
        resp.raise_for_status()
        return resp.json()
