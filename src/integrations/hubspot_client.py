"""Cliente HubSpot — fonte de verdade do lead e do estado da conversa
(Especificação Técnica, seções 3 e 6). Requer HUBSPOT_API_KEY no ambiente.

Objeto alvo (Contact vs. Deal) ainda em aberto — ver seção 12 da
Especificação Técnica. Este cliente assume Contact até essa decisão ser
fechada; ajustar CRM_OBJECT_TYPE quando definido.
"""
from __future__ import annotations

import os

import httpx

BASE_URL = "https://api.hubapi.com"
CRM_OBJECT_TYPE = "contacts"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['HUBSPOT_API_KEY']}",
        "Content-Type": "application/json",
    }


async def find_contact_by_phone(phone: str) -> dict | None:
    payload = {
        "filterGroups": [{"filters": [{"propertyName": "phone", "operator": "EQ", "value": phone}]}],
        "properties": ["email", "firstname", "lastname", "av_current_step", "score_total", "tier"],
        "limit": 1,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{BASE_URL}/crm/v3/objects/{CRM_OBJECT_TYPE}/search", headers=_headers(), json=payload)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[0] if results else None


async def upsert_contact(email: str, properties: dict) -> dict:
    """Upsert por e-mail (identificador único padrão do HubSpot para Contacts).
    `properties` deve usar exatamente os nomes internos definidos na
    Especificação Técnica, seção 6 (score_b, score_a, ..., tier, av_current_step, ...).
    """
    payload = {"properties": properties}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{BASE_URL}/crm/v3/objects/{CRM_OBJECT_TYPE}?idProperty=email",
            headers=_headers(),
            json={**payload, "properties": {**properties, "email": email}},
        )
        resp.raise_for_status()
        return resp.json()


async def create_task(contact_id: str, title: str, body: str, priority: str, due_in_hours: int) -> dict:
    """Cria a Task de handoff para o Closer, conforme o protocolo de briefing
    do Script do Atendente Virtual (seção 5 do documento de negócio)."""
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
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{BASE_URL}/crm/v3/objects/tasks", headers=_headers(), json=payload)
        resp.raise_for_status()
        return resp.json()
