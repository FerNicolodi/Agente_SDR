"""Motor de scoring BANT — funções puras, sem chamada de rede.

Regra de design não-negociável (ver Especificação Técnica, seção 7 e 10.1):
o LLM nunca escreve pontuação. Ele só classifica a resposta do lead em um
código de sinal deste módulo (ex.: "sistema_parou"); este módulo é o único
lugar que transforma um código em pontos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "scoring_weights.yaml"


def _load_weights() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


WEIGHTS = _load_weights()


@dataclass
class ScoreBreakdown:
    b: int = 0
    a: int = 0
    n1: int = 0
    n2: int = 0
    n3: int = 0
    t: int = 0
    bonus: int = 0
    ai_first: int = 0          # Pontos de AI First Receptiveness (0-5)
    ai_first_nivel: str = "media"  # 'alta' | 'media' | 'baixa'
    porte: str | None = None
    n1_oferta: str | None = None
    ofertas_sinalizadas: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        # ai_first NÃO entra no total BANT — é dimensão auxiliar para
        # orientação de oferta e briefing do Closer. O tier é determinado
        # exclusivamente pelo BANT para manter comparabilidade entre leads.
        return self.b + self.a + self.n1 + self.n2 + self.n3 + self.t + self.bonus


def score_budget(faturamento_anual: float, budget_aprovado: bool = False, lucro_real: bool = False) -> tuple[int, str, int]:
    """Retorna (pontos_base, porte, pontos_bonus) a partir do faturamento anual estimado em R$."""
    brackets = WEIGHTS["budget"]["brackets"]
    for bracket in brackets:
        if faturamento_anual >= bracket["min"]:
            pts, porte = bracket["pts"], bracket["porte"]
            break
    else:
        pts, porte = 0, "Abaixo do ICP"

    bonus = 0
    if budget_aprovado:
        bonus += WEIGHTS["budget"]["bonus"]["budget_aprovado"]
    if lucro_real:
        bonus += WEIGHTS["budget"]["bonus"]["lucro_real"]
    return pts, porte, bonus


def score_authority(cargo_categoria: str) -> int:
    """cargo_categoria deve ser uma das chaves em authority (ex.: 'cto_vp_head_ti')."""
    return WEIGHTS["authority"].get(cargo_categoria, WEIGHTS["authority"]["nao_identificado"])


_CARGOS_INTERMEDIARIOS = {"gerente_arquiteto", "tech_lead_dev_senior", "gerente_projetos_pmo"}


def adjust_authority_m4(score_a: int, ajuste: str | None, cargo_categoria: str | None = None) -> int:
    """Aplica o ajuste da Mensagem 4 (autonomia real confirmada em conversa).

    O código "autonomia_total" só classifica O QUE O LEAD DISSE (decide
    sozinho, sem mencionar mais ninguém) — o extrator de sinal não precisa
    (nem deve) saber o cargo pra escolher esse código, isso só confundia o
    modelo. A condição de negócio "bônus só se cargo for intermediário"
    (Score BANT DGS, seção 4) é aplicada aqui, com o cargo que o backend já
    tem do formulário, não pelo LLM.
    """
    if not ajuste:
        return score_a
    if ajuste == "autonomia_total":
        delta = WEIGHTS["authority"]["ajuste_m4"]["autonomia_total"] if cargo_categoria in _CARGOS_INTERMEDIARIOS else 0
    else:
        delta = WEIGHTS["authority"]["ajuste_m4"].get(ajuste, 0)
    return max(0, score_a + delta)


def score_n1(setor_categoria: str) -> tuple[int, str]:
    """Retorna (pontos, oferta_principal) a partir da categoria de setor/perfil da empresa."""
    entry = WEIGHTS["n1_setor"].get(setor_categoria)
    if entry is None:
        return 0, "Desqualificar"
    return entry["pts"], entry["oferta"]


def setor_label(setor_categoria: str) -> str:
    """Rótulo legível do setor (para uso em mensagens ao lead — nunca expor o
    código interno, ex.: 'finance_tradicional', diretamente na conversa)."""
    entry = WEIGHTS["n1_setor"].get(setor_categoria)
    return entry["label"] if entry else setor_categoria


def _score_signals_capped(signal_codes: list[str], table: dict, cap: int) -> tuple[int, list[str]]:
    total = 0
    ofertas = []
    for code in signal_codes:
        entry = table.get(code)
        if entry:
            total += entry["pts"]
            ofertas.append(entry["oferta"])
    return min(total, cap), ofertas


def score_n2(signal_codes: list[str]) -> tuple[int, list[str]]:
    """Sinais de dor ativos — acumulável, cap 15. signal_codes vem do campo Desafios do
    formulário e/ou da resposta do lead na Mensagem 2 (o extrator LLM pode retornar mais
    de um código por mensagem)."""
    table = {k: v for k, v in WEIGHTS["n2_sinais_dor"].items() if k != "cap"}
    return _score_signals_capped(signal_codes, table, WEIGHTS["n2_sinais_dor"]["cap"])


def score_n3(signal_codes: list[str]) -> tuple[int, list[str]]:
    """Sinais tecnográficos — acumulável, cap 10. Levantados pela pesquisa do SDR."""
    table = {k: v for k, v in WEIGHTS["n3_tecnografia"].items() if k != "cap"}
    return _score_signals_capped(signal_codes, table, WEIGHTS["n3_tecnografia"]["cap"])


def score_timeline(nivel: str) -> int:
    """nivel: 'critica' | 'alta' | 'media' | 'difusa' | 'indefinida'."""
    return WEIGHTS["timeline"].get(nivel, 0)


def score_ai_first(codigos: list[str]) -> tuple[int, str]:
    """Extrai receptividade AI First dos códigos retornados na M2.

    Retorna (pontos, nivel). O score NÃO é somado ao total BANT — é armazenado
    separadamente em score_ai_first / ai_first_nivel no HubSpot para orientar
    o Closer sobre qual oferta ressaltar (GenAI/Agentic Squad vs Core Up).

    Hierarquia:
      ia_interesse_explicito → alta (5 pts)
      ia_resistencia_explicita → baixa (0 pts)
      ausência de ambos → media (2 pts, default)
    """
    w = WEIGHTS["ai_first_receptiveness"]
    if "ia_interesse_explicito" in codigos:
        return w["ia_interesse_explicito"], "alta"
    if "ia_resistencia_explicita" in codigos:
        return w["ia_resistencia_explicita"], "baixa"
    return w["media_default"], "media"


def tier_from_score(score_total: int, desqualificado: bool = False) -> str:
    if desqualificado:
        return "DESQUALIFICADO"
    tiers = WEIGHTS["tiers"]
    if score_total >= tiers["hot"]:
        return "HOT"
    if score_total >= tiers["warm"]:
        return "WARM"
    if score_total >= tiers["tepid"]:
        return "TEPID"
    return "COLD"


def compute_score(
    *,
    faturamento_anual: float,
    cargo_categoria: str,
    setor_categoria: str,
    n2_signal_codes: list[str],
    n3_signal_codes: list[str],
    timeline_nivel: str,
    budget_aprovado: bool = False,
    lucro_real: bool = False,
    ajuste_autoridade_m4: str | None = None,
) -> ScoreBreakdown:
    """Agrega todas as dimensões e retorna o breakdown completo. Não decide desqualificação
    — isso é responsabilidade de scoring/disqualifiers.py, que deve rodar ANTES de aceitar
    um resultado HOT/WARM (ver Especificação Técnica, seção 2 do Score BANT)."""
    b_pts, porte, bonus = score_budget(faturamento_anual, budget_aprovado, lucro_real)
    a_pts = score_authority(cargo_categoria)
    a_pts = adjust_authority_m4(a_pts, ajuste_autoridade_m4, cargo_categoria)
    n1_pts, n1_oferta = score_n1(setor_categoria)
    n2_pts, n2_ofertas = score_n2(n2_signal_codes)
    n3_pts, n3_ofertas = score_n3(n3_signal_codes)
    t_pts = score_timeline(timeline_nivel)

    return ScoreBreakdown(
        b=b_pts,
        a=a_pts,
        n1=n1_pts,
        n2=n2_pts,
        n3=n3_pts,
        t=t_pts,
        bonus=bonus,
        porte=porte,
        n1_oferta=n1_oferta,
        ofertas_sinalizadas=[n1_oferta, *n2_ofertas, *n3_ofertas],
    )
