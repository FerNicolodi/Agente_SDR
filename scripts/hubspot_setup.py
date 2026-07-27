"""Criação automatizada das propriedades customizadas do Agente SDR no HubSpot.

USO
---
  # Com .env configurado (HUBSPOT_API_KEY real):
  python3 scripts/hubspot_setup.py

  # Ou passando a chave diretamente:
  HUBSPOT_API_KEY=pat-na-xxx python3 scripts/hubspot_setup.py

  # Dry-run (não cria nada, só exibe o que seria feito):
  python3 scripts/hubspot_setup.py --dry-run

REQUISITOS
----------
  pip install requests python-dotenv

RESULTADO
---------
  Cria o grupo de propriedades "SDR Alana" e todas as 19 propriedades customizadas
  no objeto Contact. Propriedades já existentes são ignoradas (idempotente).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

try:
    import requests
    from dotenv import load_dotenv
except ImportError:
    sys.exit(
        "Instale as dependências: pip install requests python-dotenv"
    )

# Carrega .env do diretório raiz do projeto
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = "https://api.hubapi.com"
API_KEY = os.environ.get("HUBSPOT_API_KEY", "")
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

# ---------------------------------------------------------------------------
# Grupo de propriedades
# ---------------------------------------------------------------------------

SDR_GROUP = {
    "name": "sdr_alana",
    "label": "SDR Alana",
    "displayOrder": 99,
}

# ---------------------------------------------------------------------------
# Definição das propriedades
# ---------------------------------------------------------------------------
# Formato: (name, label, type, fieldType, description)
# type: string | number | enumeration | bool
# fieldType: text | textarea | number | select | booleancheckbox

PROPERTIES = [
    # ── Controle de fluxo ────────────────────────────────────────────────
    (
        "av_current_step",
        "SDR: Etapa Atual",
        "enumeration",
        "select",
        "Etapa atual do lead no fluxo do Agente SDR. Não editar manualmente.",
        [
            "m1_enviada", "m2_enviada", "m3_enviada", "m4_enviada", "m5_enviada",
            "aguardando_horario", "fechamento_hot", "fechamento_warm",
            "fechamento_tepid", "fechamento_cold", "fechamento_desqualificado",
            "reengajamento_enviado", "movido_nurture",
        ],
    ),
    (
        "av_historico_resumido",
        "SDR: Histórico Resumido",
        "string",
        "textarea",
        "JSON compacto dos últimos 10 turnos da conversa. Não editar manualmente.",
        [],
    ),
    (
        "av_esclarecimento_count",
        "SDR: Contador de Esclarecimentos",
        "number",
        "number",
        "Número de pedidos de esclarecimento na etapa atual. Resetado a cada avanço.",
        [],
    ),
    (
        "av_fora_escopo_count",
        "SDR: Contador Fora do Escopo",
        "number",
        "number",
        "Número de respostas fora do escopo consecutivas. Resetado ao responder dentro.",
        [],
    ),

    # ── Scoring BANT ─────────────────────────────────────────────────────
    (
        "score_b",
        "Score: Budget",
        "number",
        "number",
        "Pontos de Budget no BANT. 0–25 pts (+ bônus).",
        [],
    ),
    (
        "score_a",
        "Score: Autoridade",
        "number",
        "number",
        "Pontos de Autoridade no BANT. 0–15 pts (ajustável pela M4).",
        [],
    ),
    (
        "score_n1",
        "Score: Necessidade Setor",
        "number",
        "number",
        "Pontos de N1 (setor/perfil da empresa) no BANT. 0–15 pts.",
        [],
    ),
    (
        "score_n2",
        "Score: Sinais de Dor",
        "number",
        "number",
        "Pontos de N2 (sinais de dor ativos) no BANT. 0–15 pts (cap aplicado).",
        [],
    ),
    (
        "score_n3",
        "Score: Tecnografia",
        "number",
        "number",
        "Pontos de N3 (sinais tecnográficos) no BANT. 0–10 pts (cap aplicado).",
        [],
    ),
    (
        "score_t",
        "Score: Timeline",
        "number",
        "number",
        "Pontos de Timeline no BANT. 0–20 pts.",
        [],
    ),
    (
        "score_bonus",
        "Score: Bônus",
        "number",
        "number",
        "Bônus BANT: budget aprovado (+5), lucro real (+3).",
        [],
    ),
    (
        "score_total",
        "Score: Total BANT",
        "number",
        "number",
        "Soma de B+A+N1+N2+N3+T+Bônus. Calculado ao final da qualificação (M5).",
        [],
    ),

    # ── AI First Receptiveness ────────────────────────────────────────────
    (
        "score_ai_first",
        "SDR: Score AI First",
        "number",
        "number",
        "Receptividade a IA: 5=alta, 2=media, 0=baixa. Não compõe o score_total BANT.",
        [],
    ),
    (
        "ai_first_nivel",
        "SDR: Receptividade AI First",
        "enumeration",
        "select",
        "Nível de receptividade a iniciativas de IA: alta | media | baixa.",
        ["alta", "media", "baixa"],
    ),

    # ── Qualificação ─────────────────────────────────────────────────────
    (
        "n2_signal",
        "SDR: Sinais de Dor (códigos)",
        "string",
        "text",
        "Códigos de dor separados por vírgula. Ex: backlog_represado,vaga_senior_aberta",
        [],
    ),
    (
        "tier",
        "SDR: Tier",
        "enumeration",
        "select",
        "Classificação final do lead: HOT | WARM | TEPID | COLD | DESQUALIFICADO.",
        ["HOT", "WARM", "TEPID", "COLD", "DESQUALIFICADO"],
    ),
    (
        "oferta_recomendada",
        "SDR: Oferta Recomendada",
        "string",
        "text",
        "Oferta DB1 recomendada com base no scoring. Ex: Core Up + Tech Talent.",
        [],
    ),
    (
        "setor_categoria",
        "SDR: Categoria de Setor",
        "string",
        "text",
        "Código interno de setor. Ex: finance_tradicional, varejo_core_proprietario.",
        [],
    ),
    (
        "cargo_categoria",
        "SDR: Categoria de Cargo",
        "string",
        "text",
        "Código interno de cargo. Ex: cto_vp_head_ti, ceo_coo_cfo.",
        [],
    ),
    (
        "faturamento_estimado",
        "SDR: Faturamento Estimado",
        "string",
        "text",
        "Faixa de faturamento estimada. Ex: R$ 100M–500M.",
        [],
    ),
]


# ---------------------------------------------------------------------------
# Funções de API
# ---------------------------------------------------------------------------

def _get(path: str) -> requests.Response:
    return requests.get(f"{BASE_URL}{path}", headers=HEADERS, timeout=10)


def _post(path: str, body: dict) -> requests.Response:
    return requests.post(f"{BASE_URL}{path}", headers=HEADERS, json=body, timeout=10)


def group_exists() -> bool:
    r = _get(f"/crm/v3/properties/contacts/groups")
    if r.status_code != 200:
        return False
    groups = r.json().get("results", [])
    return any(g["name"] == SDR_GROUP["name"] for g in groups)


def create_group(dry_run: bool) -> bool:
    if dry_run:
        print(f"  [DRY-RUN] Criaria grupo '{SDR_GROUP['label']}'")
        return True
    r = _post("/crm/v3/properties/contacts/groups", SDR_GROUP)
    if r.status_code in (200, 201):
        print(f"  ✅ Grupo '{SDR_GROUP['label']}' criado.")
        return True
    if r.status_code == 409:
        print(f"  ⏩ Grupo '{SDR_GROUP['label']}' já existe.")
        return True
    print(f"  ❌ Erro ao criar grupo: {r.status_code} — {r.text}")
    return False


def property_exists(name: str) -> bool:
    r = _get(f"/crm/v3/properties/contacts/{name}")
    return r.status_code == 200


def create_property(prop: tuple, dry_run: bool) -> bool:
    name, label, type_, field_type, description, options = prop

    body: dict = {
        "name": name,
        "label": label,
        "type": type_,
        "fieldType": field_type,
        "groupName": SDR_GROUP["name"],
        "description": description,
        "formField": False,
    }

    if options:
        body["options"] = [
            {"label": o, "value": o, "displayOrder": i, "hidden": False}
            for i, o in enumerate(options)
        ]

    if dry_run:
        print(f"  [DRY-RUN] Criaria: {name} ({type_}/{field_type})")
        return True

    r = _post("/crm/v3/properties/contacts", body)
    if r.status_code in (200, 201):
        print(f"  ✅ {name}")
        return True
    if r.status_code == 409:
        print(f"  ⏩ {name} — já existe (ignorado).")
        return True

    print(f"  ❌ {name} — {r.status_code}: {r.text[:120]}")
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Exibe o que seria feito sem chamar a API.")
    args = parser.parse_args()

    if not API_KEY or API_KEY == "fake_hubspot_key":
        sys.exit(
            "❌ HUBSPOT_API_KEY não configurada.\n"
            "   Edite o .env (HUBSPOT_API_KEY=pat-na-...) e rode novamente."
        )

    print(f"\n{'='*60}")
    print(f"  HubSpot Setup — Agente SDR Alana")
    print(f"  Modo: {'DRY-RUN' if args.dry_run else 'PRODUÇÃO'}")
    print(f"{'='*60}\n")

    # Grupo
    print("→ Grupo de propriedades:")
    if not args.dry_run and group_exists():
        print(f"  ⏩ Grupo '{SDR_GROUP['label']}' já existe.")
    else:
        if not create_group(args.dry_run):
            sys.exit("Abortado — não foi possível criar o grupo.")

    # Propriedades
    print(f"\n→ Propriedades ({len(PROPERTIES)} total):")
    created = skipped = errors = 0
    for prop in PROPERTIES:
        name = prop[0]
        if not args.dry_run and property_exists(name):
            print(f"  ⏩ {name} — já existe.")
            skipped += 1
            time.sleep(0.15)  # rate limit HubSpot: ~10 req/s
            continue

        ok = create_property(prop, args.dry_run)
        if ok:
            created += 1
        else:
            errors += 1
        time.sleep(0.15)

    print(f"\n{'='*60}")
    if args.dry_run:
        print(f"  DRY-RUN: {len(PROPERTIES)} propriedades seriam criadas.")
    else:
        print(f"  Criadas: {created}  |  Já existiam: {skipped}  |  Erros: {errors}")
    print(f"{'='*60}\n")

    if errors:
        sys.exit(f"Concluído com {errors} erro(s). Verifique acima.")


if __name__ == "__main__":
    main()
