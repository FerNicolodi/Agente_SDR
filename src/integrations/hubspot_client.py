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
]


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['HUBSPOT_API_KEY']}",
        "Content-Type": "application/json",
    }


async def find_contact_by_phone(phone: str) -> dict | None:
    payload = {
        "filterGroups": [{"filters": [{"propertyName": "phone", "operator": "EQ", "value": phone}]}],
        "properties": _CONTACT_PROPERTIES,
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
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{BASE_URL}/crm/v3/objects/{CRM_OBJECT_TYPE}?idProperty=email",
            headers=_headers(),
            json={"properties": {**properties, "email": email}},
        )
        resp.raise_for_status()
        return resp.json()


async def create_task(contact_id: str, title: str, body: str, priority: str, due_in_hours: int) -> dict:
    """Cria a Task de handoff para o Closer, conforme o protocolo de briefing
    do Script da Alana (Script_Atendente_Virtual_DGS.docx, seção 5)."""
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
