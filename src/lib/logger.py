"""Log estruturado com mascaramento de PII (Especificação Técnica, seção 10.3).

Telefone e nome nunca devem aparecer em texto claro fora do HubSpot.

M2 — Log storage separado:
  - Logs gerais: stdout (capturado pelo orquestrador de contêiner)
  - Logs de segurança: arquivo rotativo em logs/security.log (separado, 10 MB × 5 backups)
    Inclui: tentativas de injeção, output guard, kill switch, rate limit.
    Controlado por SECURITY_LOG_FILE (default: logs/security.log).
    Definir SECURITY_LOG_FILE="" para desativar o arquivo e usar só stdout.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Módulos cujos logs são considerados de segurança e devem ir também para o
# arquivo separado. Adicionar novos módulos aqui se necessário.
_SECURITY_LOGGERS = {
    "src.routes.whatsapp",
    "src.routes.site_form",
    "src.lib.security",
    "src.lib.output_guard",
    "src.main",  # kill switch
}

_SECURITY_LOG_FILE = os.environ.get("SECURITY_LOG_FILE", "logs/security.log")
_security_file_handler: RotatingFileHandler | None = None


def _get_security_file_handler() -> RotatingFileHandler | None:
    """Cria (lazy) o handler de arquivo rotativo para logs de segurança (M2)."""
    global _security_file_handler
    if _security_file_handler is not None:
        return _security_file_handler
    if not _SECURITY_LOG_FILE:
        return None
    try:
        Path(_SECURITY_LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        _security_file_handler = RotatingFileHandler(
            _SECURITY_LOG_FILE,
            maxBytes=10 * 1024 * 1024,  # 10 MB por arquivo
            backupCount=5,              # mantém os últimos 5 arquivos rotacionados
            encoding="utf-8",
        )
        _security_file_handler.setFormatter(JSONFormatter())
        return _security_file_handler
    except OSError:
        # Em ambientes read-only (ex: testes), falha silenciosa — só stdout.
        return None


def mask_phone(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) <= 4:
        return "*" * len(digits)
    return "*" * (len(digits) - 4) + digits[-4:]


def mask_name(name: str) -> str:
    parts = name.strip().split()
    if not parts:
        return name
    first = parts[0]
    return first if len(parts) == 1 else f"{first} {'*' * len(parts[-1])}"


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "correlation_id"):
            payload["correlation_id"] = record.correlation_id
        if hasattr(record, "context"):
            payload["context"] = record.context
        return json.dumps(payload, ensure_ascii=False)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        # Handler principal: stdout (capturado pelo Docker/orquestrador)
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(JSONFormatter())
        logger.addHandler(stdout_handler)

        # Handler secundário: arquivo de segurança rotativo (M2)
        # Adicionado apenas para módulos de segurança, evitando duplicação
        # de logs de negócio no arquivo de segurança.
        if name in _SECURITY_LOGGERS:
            file_handler = _get_security_file_handler()
            if file_handler is not None:
                logger.addHandler(file_handler)

        logger.setLevel(logging.INFO)
    return logger
