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


import os
from datetime import datetime, timezone, timedelta


# Janela mínima entre submissões do mesmo identificador (telefone ou e-mail).
# Configurável via variável de ambiente; padrão: 60 segundos.
_RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))

# Timestamp ISO da última submissão aceita, lido do HubSpot antes de chamar
# esta função. Deve ser passado como `last_submission_iso` pelo chamador.
# A gravação do novo timestamp após aceitar a requisição é responsabilidade
# da camada de rota (não desta função — mantém separação de responsabilidades).


def is_rate_limited(last_submission_iso: str | None) -> bool:
    """Verifica se o identificador está dentro da janela de rate limiting.

    Args:
        last_submission_iso: Valor da propriedade `av_last_submission_at` do
            Contact no HubSpot (string ISO 8601), ou None se for o primeiro
            contato. O HubSpot é a fonte de verdade — o backend não mantém
            estado em memória (Especificação Técnica, seção 3).

    Returns:
        True se a requisição deve ser rejeitada (dentro da janela).
        False se pode prosseguir.

    Uso na rota:
        last_ts = contact["properties"].get("av_last_submission_at")
        if is_rate_limited(last_ts):
            raise HTTPException(status_code=429, detail="Muitas requisições")
        # ... processa ...
        await hubspot_client.upsert_contact(email, {
            "av_last_submission_at": datetime.now(timezone.utc).isoformat()
        })
    """
    if not last_submission_iso:
        return False  # primeiro contato, sempre aceita
    try:
        last_dt = datetime.fromisoformat(last_submission_iso)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        elapsed = datetime.now(timezone.utc) - last_dt
        return elapsed < timedelta(seconds=_RATE_LIMIT_WINDOW_SECONDS)
    except ValueError:
        return False  # timestamp malformado → aceita e sobrescreve
