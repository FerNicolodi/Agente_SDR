"""Cliente Z-API — canal WhatsApp da Alana.

Z-API é um SaaS gerenciado de API para WhatsApp (z-api.io). Diferente da
Meta Cloud API oficial:
  - Não requer aprovação de templates nem conta Meta Business verificada.
  - Não há janela de 24h — mensagens podem ser enviadas a qualquer momento.
  - Conecta um número WhatsApp via QR code no painel Z-API.
  - Sem servidor para gerenciar — Z-API cuida da infraestrutura.

Configuração necessária (`.env`):
  ZAPI_INSTANCE_ID   ID da instância no painel Z-API
  ZAPI_TOKEN         Token da instância no painel Z-API
  ZAPI_CLIENT_TOKEN  Security Token configurado no painel Z-API (webhook auth)

Endpoint de envio:
  POST https://api.z-api.io/instances/{instanceId}/token/{token}/send-text
  Body: {"phone": "5511999999999", "message": "texto"}

Compatibilidade com site_form.py: `send_template` continua existindo mas
envia texto livre via `send_text`, extraindo o nome do lead dos `components`
Meta e formatando o M1_ABERTURA. Nenhuma mudança necessária em site_form.py.
"""
from __future__ import annotations

import os
import time

import httpx

from ..lib.logger import get_logger, mask_phone

logger = get_logger(__name__)

_ZAPI_BASE = "https://api.z-api.io"


def _send_url() -> str:
    instance_id = os.environ["ZAPI_INSTANCE_ID"]
    token = os.environ["ZAPI_TOKEN"]
    return f"{_ZAPI_BASE}/instances/{instance_id}/token/{token}/send-text"


def _headers() -> dict:
    return {
        "Content-Type": "application/json",
        "client-token": os.environ["ZAPI_CLIENT_TOKEN"],
    }


async def send_text(to: str, body: str) -> dict:
    """Envia mensagem de texto para o número `to` via Z-API.

    `to` deve ser o número no formato internacional sem + (ex: 5544999999999).
    A Z-API usa o campo `phone` com apenas os dígitos.
    """
    t0 = time.monotonic()
    payload = {"phone": to, "message": body}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(_send_url(), headers=_headers(), json=payload)
            resp.raise_for_status()
            result = resp.json()
        logger.info(
            "whatsapp:send_text",
            extra={
                "context": {
                    "tool": "whatsapp.send_text",
                    "to": mask_phone(to),
                    "body_length": len(body),
                    "status_code": resp.status_code,
                    "duration_ms": round((time.monotonic() - t0) * 1000),
                }
            },
        )
        return result
    except Exception as exc:
        logger.error(
            "whatsapp:send_text:error",
            extra={
                "context": {
                    "tool": "whatsapp.send_text",
                    "to": mask_phone(to),
                    "body_length": len(body),
                    "error": str(exc),
                    "duration_ms": round((time.monotonic() - t0) * 1000),
                }
            },
        )
        raise


async def send_template(
    to: str,
    template_name: str,
    language_code: str = "pt_BR",
    components: list | None = None,
) -> dict:
    """Compatibilidade com site_form.py — a Z-API não usa templates Meta.

    Extrai o nome do lead do primeiro parâmetro `body` nos `components`
    (formato Meta) e envia M1_ABERTURA como texto livre.
    Se não encontrar o nome, envia sem a personalização.

    O parâmetro `template_name` é ignorado — aqui só existe M1.
    """
    # Import local para evitar circular: messages → (nada) → ok
    from ..llm.prompts.messages import M1_ABERTURA

    nome = ""
    if components:
        for comp in components:
            if comp.get("type") == "body":
                params = comp.get("parameters", [])
                if params and params[0].get("type") == "text":
                    nome = params[0].get("text", "")
                    break

    texto = M1_ABERTURA.format(nome=nome) if nome else M1_ABERTURA
    logger.info(
        "whatsapp:send_template→send_text",
        extra={
            "context": {
                "tool": "whatsapp.send_template",
                "to": mask_phone(to),
                "template_name": template_name,
                "nome_extraido": bool(nome),
            }
        },
    )
    return await send_text(to, texto)
