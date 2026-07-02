"""Verificação de assinatura dos webhooks (Especificação Técnica, seção 10.3).

Nenhum payload deve ser processado sem passar por uma destas checagens.
"""
from __future__ import annotations

import hmac
import hashlib


def verify_hmac_signature(payload: bytes, signature_header: str | None, shared_secret: str) -> bool:
    """Verifica a assinatura do webhook do formulário do site.

    Espera um header no formato "sha256=<hex>", calculado pelo site com o
    mesmo segredo compartilhado (SITE_FORM_HMAC_SECRET).
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(shared_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)


def verify_meta_signature(payload: bytes, signature_header: str | None, app_secret: str) -> bool:
    """Verifica o header X-Hub-Signature-256 enviado pela Meta Cloud API em
    todo webhook de mensagem inbound do WhatsApp."""
    return verify_hmac_signature(payload, signature_header, app_secret)


def verify_meta_webhook_challenge(mode: str | None, token: str | None, expected_verify_token: str) -> bool:
    """Usado no handshake GET de configuração do webhook na Meta (hub.mode=subscribe)."""
    return mode == "subscribe" and token == expected_verify_token


# NOTA (Especificação Técnica, seção 3): o backend roda em um container
# stateless (Portal de Deploy DB1, sem persistência local). Rate limiting por
# telefone/IP não pode depender de um contador em memória — precisa consultar
# um estado externo (ex.: timestamp da última submissão gravado no HubSpot,
# ou um cache gerenciado fora do container). Ainda não implementado neste
# scaffold; tratar antes do go-live (ver seção 12 - pendências).
def is_rate_limited(_identifier: str) -> bool:
    raise NotImplementedError(
        "Rate limiting depende de um estado externo ao container — "
        "definir a fonte (HubSpot ou cache externo) antes do go-live."
    )
