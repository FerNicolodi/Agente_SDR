"""Verificação de assinatura dos webhooks e sanitização de entrada (C1).

Nenhum payload deve ser processado sem passar pelas checagens de assinatura.
Toda mensagem do lead deve ser sanitizada com `sanitize_lead_input` antes
de chegar ao LLM.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


# ── HMAC / Webhook ────────────────────────────────────────────────────────────


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


def verify_evolution_webhook(apikey_header: str | None, expected_key: str) -> bool:
    """Verifica o header `apikey` enviado pela Evolution API em cada webhook.

    A Evolution envia o header `apikey: <sua-api-key>` em todas as
    requisições de webhook — é o mecanismo de autenticação nativo.
    Usa hmac.compare_digest para evitar timing attacks.

    Args:
        apikey_header: Valor do header `apikey` recebido na requisição.
        expected_key: Valor de EVOLUTION_API_KEY no ambiente.

    Returns:
        True se o header está presente e bate com a chave configurada.
    """
    if not apikey_header or not expected_key:
        return False
    return hmac.compare_digest(apikey_header.strip(), expected_key.strip())


def verify_zapi_webhook(client_token_header: str | None, expected_token: str) -> bool:
    """Verifica o header `client-token` enviado pela Z-API em cada webhook.

    A Z-API envia o header `client-token: <Security Token>` em todas as
    requisições de webhook quando o Security Token está configurado no painel.
    Usa hmac.compare_digest para evitar timing attacks.

    Args:
        client_token_header: Valor do header `client-token` recebido.
        expected_token: Valor de ZAPI_CLIENT_TOKEN no ambiente.

    Returns:
        True se o header está presente e bate com o token configurado.
    """
    if not client_token_header or not expected_token:
        return False
    return hmac.compare_digest(client_token_header.strip(), expected_token.strip())


# ── Rate Limiting ─────────────────────────────────────────────────────────────

# Janela mínima entre submissões do mesmo identificador (telefone ou e-mail).
# Configurável via variável de ambiente; padrão: 60 segundos.
_RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))


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


# ── Sanitização de Entrada (C1) ───────────────────────────────────────────────

# Comprimento máximo aceito para mensagens do lead antes de passar ao LLM.
# Ataques many-shot requerem inputs muito longos — truncar limita a superfície.
MAX_LEAD_INPUT_LENGTH = int(os.environ.get("MAX_LEAD_INPUT_LENGTH", "2000"))

# Caracteres Unicode zero-width: invisíveis no chat, usados para ofuscar injeção.
# Removidos via tabela de tradução (mais eficiente que regex para chars isolados).
_ZERO_WIDTH_STRIP = str.maketrans(
    "",
    "",
    "".join([
        "​",  # ZERO WIDTH SPACE
        "‌",  # ZERO WIDTH NON-JOINER
        "‍",  # ZERO WIDTH JOINER
        "﻿",  # ZERO WIDTH NO-BREAK SPACE (BOM)
        "‎",  # LEFT-TO-RIGHT MARK
        "‏",  # RIGHT-TO-LEFT MARK
        "‪",  # LEFT-TO-RIGHT EMBEDDING
        "‫",  # RIGHT-TO-LEFT EMBEDDING
        "‬",  # POP DIRECTIONAL FORMATTING
        "‭",  # LEFT-TO-RIGHT OVERRIDE
        "‮",  # RIGHT-TO-LEFT OVERRIDE
        "⁠",  # WORD JOINER
    ]),
)

# Role-indicator strings usadas em ataques de prompt injection por delimitador.
# Padrões: "SYSTEM:", "[SYSTEM]", "<|system|>", "<im_start>", "INST"
_ROLE_INDICATOR_RE = re.compile(
    r"(?:SYSTEM|HUMAN|ASSISTANT|USER|OPERATOR)\s*:"
    r"|<\|?(?:im_start|im_end|system|user|assistant)\|?>"
    r"|\[(?:SYSTEM|HUMAN|ASSISTANT|USER|INST|OPERATOR)\]"
    r"|\bINST\b",
    re.IGNORECASE,
)

# URL percent-encoding (%XX): mensagens legítimas no WhatsApp nunca usam isso.
_URL_ENCODED_RE = re.compile(r"%[0-9A-Fa-f]{2}")

# Base64 candidatos: sequências ≥ 40 chars para reduzir falsos positivos em
# textos comuns. Verificamos apenas se o conteúdo decodificado tem role-indicators.
_BASE64_CANDIDATE_RE = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")


@dataclass
class SanitizationResult:
    """Resultado da sanitização de uma mensagem do lead.

    Attributes:
        text: Texto limpo, pronto para passar ao LLM.
        was_truncated: True se o input original excedeu MAX_LEAD_INPUT_LENGTH.
        injection_signal_detected: True se role-indicators ou encoding bypass
            foram encontrados. A rota deve tratar como tentativa de manipulação
            e escalar para o Closer sem chamar o LLM.
        attack_vector: Tipo de vetor detectado, ou None se injection_signal_detected
            for False. Valores possíveis:
            - "role_indicator_direct"  → role-indicator no texto puro
            - "url_encoded"            → role-indicator após decodificação %XX
            - "base64"                 → role-indicator no conteúdo Base64 decodificado
            Usado para log estruturado (C2) e análise de padrões de ataque.
    """
    text: str
    was_truncated: bool
    injection_signal_detected: bool
    attack_vector: str | None = None


def sanitize_lead_input(raw: str) -> SanitizationResult:
    """Sanitiza a mensagem do lead antes de passar ao LLM (checklist C1).

    Aplica (nessa ordem):
    1. Strip de caracteres Unicode zero-width (ofuscação invisível).
    2. Verificação de role-indicators no texto puro.
    3. Normalização de URL encoding (%XX) e re-verificação de role-indicators
       no texto decodificado — detecta bypass por encoding.
    4. Verificação de Base64: decodifica candidatos e checa role-indicators
       no conteúdo decodificado — detecta bypass por Base64.
    5. Remoção de role-indicator strings do texto final (hardening defensivo,
       mesmo quando injection_signal_detected=False).
    6. Truncamento ao limite configurável (MAX_LEAD_INPUT_LENGTH).

    Returns:
        SanitizationResult. Se injection_signal_detected=True, a rota deve
        escalar imediatamente para o Closer sem invocar o LLM.
    """
    injection_signal_detected = False
    attack_vector: str | None = None

    # 1. Strip zero-width chars
    text = raw.translate(_ZERO_WIDTH_STRIP)

    # 2. Role-indicators no texto puro
    if _ROLE_INDICATOR_RE.search(text):
        injection_signal_detected = True
        attack_vector = "role_indicator_direct"

    # 3. URL encoding: normaliza e re-verifica no texto decodificado
    if _URL_ENCODED_RE.search(text):
        try:
            decoded_url = urllib.parse.unquote(text)
        except Exception:
            decoded_url = text
        if _ROLE_INDICATOR_RE.search(decoded_url):
            injection_signal_detected = True
            if attack_vector is None:
                attack_vector = "url_encoded"
        text = decoded_url  # sempre normaliza para evitar bypass residual

    # 4. Base64: verifica role-indicators no conteúdo decodificado
    for match in _BASE64_CANDIDATE_RE.finditer(text):
        try:
            # Padding flexível (+== para cobrir comprimentos variados)
            decoded_b64 = base64.b64decode(match.group() + "==").decode("utf-8", errors="replace")
            if _ROLE_INDICATOR_RE.search(decoded_b64):
                injection_signal_detected = True
                if attack_vector is None:
                    attack_vector = "base64"
                break
        except Exception:
            pass  # candidato não é Base64 válido, ignora

    # 5. Remove role-indicators do texto final (hardening independente da flag)
    text = _ROLE_INDICATOR_RE.sub("", text).strip()

    # 6. Truncate
    was_truncated = len(text) > MAX_LEAD_INPUT_LENGTH
    text = text[:MAX_LEAD_INPUT_LENGTH]

    return SanitizationResult(
        text=text,
        was_truncated=was_truncated,
        injection_signal_detected=injection_signal_detected,
        attack_vector=attack_vector,
    )
