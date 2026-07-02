"""Valida o motor de scoring contra o exemplo prático documentado no
Score_Agente SDR DGS_Bant_2026.docx, seção 8:

    CTO de banco regional do Sul, faturamento R$ 300M. Campo Desafios
    descreve sistema legado de crédito sem suporte (profissional-chave saiu)
    e prazo Open Finance em 4 meses. TI 20-200 pessoas, ERP sem API,
    infraestrutura on-premise.

    Resultado esperado no documento: B=18, A=15, N1=15, N2=15 (cap), N3=10
    (cap), T=15 -> total 88 pts (sem bônus) -> tier HOT.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.scoring.rules import compute_score, tier_from_score
from src.scoring.disqualifiers import DisqualifierFlags, check_disqualifiers


def test_exemplo_pratico_banco_regional():
    breakdown = compute_score(
        faturamento_anual=300_000_000,
        cargo_categoria="cto_vp_head_ti",
        setor_categoria="finance_tradicional",
        n2_signal_codes=["profissional_chave_saiu", "prazo_regulatorio"],
        n3_signal_codes=["time_ti_20_200", "erp_sem_api", "on_premise"],
        timeline_nivel="alta",
    )

    assert breakdown.b == 18
    assert breakdown.a == 15
    assert breakdown.n1 == 15
    assert breakdown.n2 == 15  # 14 + 13 = 27, cap 15
    assert breakdown.n3 == 10  # 5 + 3 + 3 = 11, cap 10
    assert breakdown.t == 15
    assert breakdown.total == 88

    assert tier_from_score(breakdown.total) == "HOT"


def test_bonus_budget_aprovado_e_lucro_real():
    breakdown = compute_score(
        faturamento_anual=300_000_000,
        cargo_categoria="cto_vp_head_ti",
        setor_categoria="finance_tradicional",
        n2_signal_codes=["profissional_chave_saiu", "prazo_regulatorio"],
        n3_signal_codes=["time_ti_20_200", "erp_sem_api", "on_premise"],
        timeline_nivel="alta",
        budget_aprovado=True,
        lucro_real=True,
    )
    assert breakdown.bonus == 8
    assert breakdown.total == 96


def test_desqualificador_d5_bloqueia_independente_do_score():
    flags = DisqualifierFlags(d5_decisao_por_preco=True)
    resultado = check_disqualifiers(flags)
    assert resultado.desqualificado is True
    assert resultado.codigos == ["D5"]
    assert tier_from_score(96, desqualificado=resultado.desqualificado) == "DESQUALIFICADO"


def test_lead_abaixo_do_icp_sem_sinais():
    breakdown = compute_score(
        faturamento_anual=10_000_000,
        cargo_categoria="nao_identificado",
        setor_categoria="tech_native_sem_projeto",
        n2_signal_codes=[],
        n3_signal_codes=[],
        timeline_nivel="indefinida",
    )
    assert breakdown.total == 0
    assert tier_from_score(breakdown.total) == "COLD"
