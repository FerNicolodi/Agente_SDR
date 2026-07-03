"""Submete o template da Mensagem 1 para aprovação da Meta.

A M1 é enviada pela empresa (o lead preencheu o formulário no site, não
escreveu no WhatsApp primeiro) — por regra da própria Meta, toda mensagem que
abre uma conversa assim precisa ser um template pré-aprovado (Especificação
Técnica, seção 5, passo 4, e seção 12 - pendências).

Pré-requisitos (fora do escopo deste script — precisam existir antes de rodar):
  1. Um WhatsApp Business Account (WABA) já criado no Meta Business Manager,
     com o número de telefone cadastrado e verificado.
  2. Um token de acesso (idealmente de um System User) com a permissão
     whatsapp_business_management, associado a esse WABA.

Uso:
    export META_WA_TOKEN=...
    export META_WABA_ID=...
    python scripts/submit_whatsapp_template.py

O resultado normalmente entra em status PENDING e a Meta revisa em minutos a
~24h. Consultar o status depois em WhatsApp Manager > Modelos de mensagem, ou
via GET /{WABA_ID}/message_templates.
"""
from __future__ import annotations

import os
import sys

import httpx

GRAPH_API_VERSION = "v20.0"

TEMPLATE_NAME = os.environ.get("META_WA_M1_TEMPLATE_NAME", "abertura_qualificacao_v1")

# Categoria recomendada: UTILITY, porque a mensagem é uma resposta direta a
# uma ação do próprio lead (ele preencheu o formulário pedindo contato), não
# uma comunicação promocional não solicitada. A Meta pode reclassificar como
# MARKETING na revisão — isso muda o custo por conversa, mas não quebra o
# fluxo. Se a Meta rejeitar como UTILITY, submeter de novo como MARKETING.
TEMPLATE_PAYLOAD = {
    "name": TEMPLATE_NAME,
    "language": "pt_BR",
    "category": "UTILITY",
    "components": [
        {
            "type": "BODY",
            "text": (
                "Olá, {{1}}! Aqui é a Alana, analista comercial da DGS. Vi que você "
                "entrou em contato com a gente pela DB1 e quero entender melhor o seu "
                "contexto antes de te conectar com o especialista certo. Leva menos de "
                "5 minutos — posso te fazer algumas perguntas rápidas?"
            ),
            "example": {"body_text": [["Ana"]]},
        }
    ],
}


def submit_template() -> dict:
    waba_id = os.environ["META_WABA_ID"]
    token = os.environ["META_WA_TOKEN"]
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{waba_id}/message_templates"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    response = httpx.post(url, headers=headers, json=TEMPLATE_PAYLOAD, timeout=15)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    try:
        result = submit_template()
    except KeyError as exc:
        print(f"Variável de ambiente ausente: {exc}. Defina META_WABA_ID e META_WA_TOKEN.", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as exc:
        print(f"Meta rejeitou a submissão: {exc.response.status_code} {exc.response.text}", file=sys.stderr)
        sys.exit(1)

    print("Template submetido. Status inicial:", result)
