"""Log estruturado com mascaramento de PII (Especificação Técnica, seção 10.3).

Telefone e nome nunca devem aparecer em texto claro fora do HubSpot.
"""
from __future__ import annotations

import json
import logging
import sys


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
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
