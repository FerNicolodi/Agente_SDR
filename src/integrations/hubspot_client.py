"""Cliente HubSpot — fonte de verdade do lead e do estado da conversa
(Especificação Técnica, seções 3 e 6). Requer HUBSPOT_API_KEY no ambiente.

Objeto alvo (Contact vs. Deal) ainda em aberto — ver seção 12 da
Especificação Técnica. Este cliente assume Contact até essa decisão ser
fechada; ajustar CRM_OBJECT_TYPE quando definido.

STORAGE_BACKEND
---------------
Defina `STORAGE_BACKEND=memory` no .env para usar armazenamento em memória
(dict Python) sem depender do HubSpot. Útil enquanto o Private App e as
propriedades customizadas ainda não estão configurados em produção.

  STORAGE_BACKEND=memory  → estado vive no processo; zerado a cada restart
  STORAGE_BACKEND=hubspot → comportamento padrão de produção (default)

Quando mudar para hubspot, basta remover/alterar a variável e fazer redeploy.
"""
from __future__ import annotations

import os
import time
import uuid

import httpx

from ..lib.logger import get_logger, mask_phone

logger = get_logger(__name__)

BASE_URL = "https://api.hubapi.com"
CRM_OBJECT_TYPE = "contacts"

# ── Backend em memória (paliatvo enquanto HubSpot não está configurado) ────────
# Dois índices para suportar lookup por e-mail (upsert) e por telefone (find).
_mem_by_email: dict[str, dict] = {}   # email → contact_record
_mem_by_phone: dict[str, str] = {}    # phone → email


def _use_memory() -> bool:
    return os.environ.get("STORAGE_BACKEND", "hubspot").strip().lower() == "memory"


def _mem_find_by_phone(phone: str) -> dict | None:
    email = _mem_by_phone.get(phone)
    return _mem_by_email.get(email) if email else None


def _mem_upsert(email: str, properties: dict) -> dict:
    existing = _mem_by_email.get(email)
    if existing:
        existing["properties"].update(properties)
        existing["properties"]["email"] = email
    else:
        existing = {
            "id": f"mem-{uuid.uuid4().hex[:8]}",
            "properties": {"email": email, **properties},
        }
        _mem_by_email[email] = existing

    # Mantém índice por telefone atualizado
    phone = existing["properties"].get("phone")
    if phone:
        _mem_by_phone[phone] = email

    return existing


def _mem_create_task(contact_id: str, title: str, body: str, priority: str) -> dict:
    task = {"id": f"task-{uuid.uuid4().hex[:8]}", "title": title, "priority": priority}
    logger.info(
        "memory_store:create_task",
        extra={"context": {"contact_id": contact_id, "title": title, "priority": priority, "body_preview": body[:120]}},
    )
    return task

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
    if _use_memory():
        result = _mem_find_by_phone(phone)
        logger.info(
            "memory_store:find_contact_by_phone",
            extra={"context": {"phone": mask_phone(phone), "found": result is not None}},
        )
        return result

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
    if _use_memory():
        result = _mem_upsert(email, properties)
        logger.info(
            "memory_store:upsert_contact",
            extra={
                "context": {
                    "contact_id": result["id"],
                    "props_updated": list(properties.keys()),
                    "step": properties.get("av_current_step"),
                    "tier": properties.get("tier"),
                }
            },
        )
        return result

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
    if _use_memory():
        return _mem_create_task(contact_id, title, body, priority)

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
