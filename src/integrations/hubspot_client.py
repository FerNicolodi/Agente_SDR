"""Cliente HubSpot — fonte de verdade do lead e do estado da conversa
(Especificação Técnica, seções 3 e 6). Requer HUBSPOT_API_KEY no ambiente.

Objeto alvo (Contact vs. Deal) ainda em aberto — ver seção 12 da
Especificação Técnica. Este cliente assume Contact até essa decisão ser
fechada; ajustar CRM_OBJECT_TYPE quando definido.
"""
from __future__ import annotations

import os
import time

import httpx

from ..lib.logger import get_logger, mask_phone

logger = get_logger(__name__)

BASE_URL = "https://api.hubapi.com"
CRM_OBJECT_TYPE = "contacts"

# Propriedades buscadas em toda chamada a find_contact_by_phone.
# Mantidas aqui para facilitar sync com a seção 6 da Especificação Técnica
# quando novas propriedades forem criadas no HubSpot.
_CONTACT_PROPERTIES = [
    # Identificação
    "email", "firstname", "lastname", "phone",
    # Dados do formulário (contexto para personalização das mensagens)
    "desafios", "cargo_categoria", "cargo", "setor_categoria", "faturamento_estimado",
    # Estado da conversa (backend stateless — HubSpot é a única memória)
    "av_current_step",
    "av_esclarecimento_count",
    "av_fora_escopo_count",       # Contador de respostas fora do escopo na etapa atual
    "av_historico_resumido",      # JSON compacto das últimas trocas (para qa_responder)
    # Scores acumulados por dimensão
    "score_b", "score_a", "score_n1", "score_n2", "score_n3", "score_t",
    "score_bonus", "score_total",
    # Sinais e oferta recomendada
    "n2_signal", "oferta_recomendada",
    # Classificação final
    "tier",
    # Rate limiting
    "av_last_submission_at",
    # Receptividade AI First
    "score_ai_first", "ai_first_nivel",
]


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['HUBSPOT_API_KEY']}",
        "Content-Type": "application/json",
    }


async def find_contact_by_phone(phone: str) -> dict | None:
    t0 = time.monotonic()
    try:
        payload = {
            "filterGroups": [{"filters": [{"propertyName": "phone", "operator": "EQ", "value": phone}]}],
            "properties": _CONTACT_PROPERTIES,
            "limit": 1,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{BASE_URL}/crm/v3/objects/{CRM_OBJECT_TYPE}/search",
                headers=_headers(),
                json=payload,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            found = results[0] if results else None
        logger.info(
            "hubspot:find_contact_by_phone",
            extra={
                "context": {
                    "tool": "hubspot.find_contact_by_phone",
                    "phone": mask_phone(phone),
                    "found": found is not None,
                    "status_code": resp.status_code,
                    "duration_ms": round((time.monotonic() - t0) * 1000),
                }
            },
        )
        return found
    except Exception as exc:
        logger.error(
            "hubspot:find_contact_by_phone:error",
            extra={
                "context": {
                    "tool": "hubspot.find_contact_by_phone",
                    "phone": mask_phone(phone),
                    "error": str(exc),
                    "duration_ms": round((time.monotonic() - t0) * 1000),
                }
            },
        )
        raise


async def upsert_contact(email: str, properties: dict) -> dict:
    """Upsert por e-mail (identificador único padrão do HubSpot para Contacts).
    `properties` deve usar exatamente os nomes internos definidos na
    Especificação Técnica, seção 6 (score_b, score_a, ..., tier, av_current_step, ...).
    """
    t0 = time.monotonic()
    # Campos de log seguro: não inclui scores ou dados sensíveis, só estado da conversa.
    safe_props = {
        k: v for k, v in properties.items()
        if k in ("av_current_step", "tier")
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{BASE_URL}/crm/v3/objects/{CRM_OBJECT_TYPE}?idProperty=email",
                headers=_headers(),
                json={"properties": {**properties, "email": email}},
            )
            resp.raise_for_status()
            result = resp.json()
        logger.info(
            "hubspot:upsert_contact",
            extra={
                "context": {
                    "tool": "hubspot.upsert_contact",
                    "contact_id": result.get("id"),
                    "props_updated": list(properties.keys()),
                    "step": safe_props.get("av_current_step"),
                    "tier": safe_props.get("tier"),
                    "status_code": resp.status_code,
                    "duration_ms": round((time.monotonic() - t0) * 1000),
                }
            },
        )
        return result
    except Exception as exc:
        logger.error(
            "hubspot:upsert_contact:error",
            extra={
                "context": {
                    "tool": "hubspot.upsert_contact",
                    "props_attempted": list(properties.keys()),
                    "error": str(exc),
                    "duration_ms": round((time.monotonic() - t0) * 1000),
                }
            },
        )
        raise


async def create_task(contact_id: str, title: str, body: str, priority: str, due_in_hours: int) -> dict:
    """Cria a Task de handoff para o Closer, conforme o protocolo de briefing
    do Script da Alana (Script_Atendente_Virtual_DGS.docx, seção 5)."""
    t0 = time.monotonic()
    payload = {
        "properties": {
            "hs_task_subject": title,
            "hs_task_body": body,
            "hs_task_priority": priority,
            "hs_task_type": "CALL",
        },
        "associations": [
            {
                "to": {"id": contact_id},
                "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 204}],
            }
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{BASE_URL}/crm/v3/objects/tasks",
                headers=_headers(),
                json=payload,
            )
            resp.raise_for_status()
            result = resp.json()
        logger.info(
            "hubspot:create_task",
            extra={
                "context": {
                    "tool": "hubspot.create_task",
                    "contact_id": contact_id,
                    "task_id": result.get("id"),
                    "priority": priority,
                    "due_in_hours": due_in_hours,
                    "status_code": resp.status_code,
                    "duration_ms": round((time.monotonic() - t0) * 1000),
                }
            },
        )
        return result
    except Exception as exc:
        logger.error(
            "hubspot:create_task:error",
            extra={
                "context": {
                    "tool": "hubspot.create_task",
                    "contact_id": contact_id,
                    "priority": priority,
                    "error": str(exc),
                    "duration_ms": round((time.monotonic() - t0) * 1000),
                }
            },
        )
        raise
