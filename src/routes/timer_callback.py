"""Endpoint chamado por um HubSpot Workflow (delay + branch) quando um lead
fica em silêncio — 24h para reengajamento, 48h (após o reengajamento) para
mover para nurture. Existe porque o backend é stateless e não pode confiar
em um timer em memória para sobreviver a um redeploy do container
(Especificação Técnica, seção 3).

O HubSpot Workflow é responsável por medir o tempo (comparando a hora atual
com av_last_message_at) e por não disparar de novo se o lead já respondeu
— este endpoint só executa a ação quando chamado.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, field_validator

from ..integrations import hubspot_client, whatsapp_client
from ..lib.logger import get_logger
from ..lib.security import verify_hmac_signature
from ..llm.prompts import messages
from ..state_machine import transitions
from ..state_machine.states import AVStep

router = APIRouter()
logger = get_logger(__name__)


class TimerCallbackPayload(BaseModel):
    """HIGH-04: Pydantic model para validação tipada do payload do HubSpot Workflow.

    Antes usávamos payload["email"] diretamente — sem validação de tipo,
    um campo malformado causaria KeyError ou TypeError sem log estruturado.
    Agora o FastAPI retorna 422 com detalhe do campo inválido antes de
    qualquer lógica de negócio ser executada.
    """

    email: EmailStr
    phone: str
    ja_reengajado: bool = False

    @field_validator("phone")
    @classmethod
    def phone_must_be_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("phone não pode ser vazio")
        return v


@router.post("/webhook/timer-callback")
async def handle_timer_callback(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("X-Signature")
    if not verify_hmac_signature(raw_body, signature, os.environ["HUBSPOT_WORKFLOW_HMAC_SECRET"]):
        raise HTTPException(status_code=401, detail="Assinatura inválida")

    # HIGH-04: validação tipada — lança 422 com detalhe se campo ausente ou malformado
    payload_raw = await request.json()
    try:
        payload = TimerCallbackPayload.model_validate(payload_raw)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    email = payload.email
    phone = payload.phone
    ja_reengajado = payload.ja_reengajado

    contact = await hubspot_client.find_contact_by_phone(phone)
    if contact is None:
        raise HTTPException(status_code=404, detail="Lead não encontrado")

    current_step = AVStep(contact["properties"]["av_current_step"])
    next_step = transitions.next_step_after_silencio(current_step, ja_reengajado)

    if next_step == AVStep.REENGAJAMENTO_ENVIADO:
        nome = contact["properties"].get("firstname", "")
        await whatsapp_client.send_text(phone, messages.REENGAJAMENTO_24H.format(nome=nome))

    await hubspot_client.upsert_contact(email=email, properties={"av_current_step": next_step.value})
    logger.info("Timer de silêncio processado", extra={"context": {"next_step": next_step.value}})
    return {"status": "ok", "next_step": next_step.value}
