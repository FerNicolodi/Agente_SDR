"""Testes unitários para src/lib/output_guard.py — check_output (C3).

Cobre:
- Outputs limpos (sem falso positivo)
- Termos do enum interno
- Flags internas do signal extractor
- Nomes de propriedades HubSpot
- Terminologia de design interno
- Case-insensitivity
- String vazia
"""
from __future__ import annotations

import pytest

from src.lib.output_guard import check_output


# ── Outputs legítimos — sem falso positivo ────────────────────────────────────


@pytest.mark.parametrize(
    "msg",
    [
        # Respostas típicas do qa_responder
        "A DB1 tem mais de 20 anos de mercado e atende empresas de médio e grande porte.",
        "O Core Up é nossa metodologia de modernização de sistemas legados com IA.",
        "Não trabalhamos com valores fechados antes de entender o escopo — o especialista vai detalhar.",
        "Sim, temos cases no setor financeiro e industrial. Posso seguir com as perguntas?",
        "AI First é nossa premissa: todos os projetos são pensados com agentes de IA desde o início.",
        # Respostas típicas do message_composer (M3-M5)
        "Considerando o que você mencionou sobre o sistema legado, qual é a urgência disso pra você?",
        "Pra garantir que nosso especialista venha preparado: além de você, quem mais decide?",
        "Você busca um parceiro técnico de ponta a ponta, ou está cotando preço entre fornecedores?",
        # Palavras que poderiam confundir mas são legítimas
        "temos score de NPS muito alto com nossos clientes",
        "o tier enterprise tem SLA diferenciado",
        "nossa equipe tem autonomia para decidir",
        "o sistema está parado desde ontem",
    ],
)
def test_clean_outputs_no_guard_triggered(msg):
    result = check_output(msg)
    assert result.is_safe, (
        f"Falso positivo para output legítimo: {msg!r}\n"
        f"Termo que acionou: {result.matched_term}"
    )
    assert result.matched_term is None


# ── Termos do enum interno ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "term",
    [
        "cotacao_exclusiva_preco",
        "parceiro_tecnico_budget_aprovado",
        "ia_interesse_explicito",
        "ia_resistencia_explicita",
        "autonomia_total",
        "tecnico_sem_cto_no_cargo",
        "multiplos_decisores",
        "nao_confirmado",
        "sistema_parou",
        "prazo_regulatorio",
    ],
)
def test_enum_codes_detected(term):
    msg = f"Sua avaliação foi classificada como {term} no sistema."
    result = check_output(msg)
    assert not result.is_safe
    assert result.matched_term is not None


# ── Flags do signal extractor ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "fragment",
    [
        "registrar_sinal",
        "tentativa_injecao_detectada",
        "pergunta_sobre_natureza_virtual",
        "pergunta_dentro_do_escopo",
        "tem_pergunta_do_lead",
    ],
)
def test_signal_extractor_flags_detected(fragment):
    result = check_output(f"O sistema retornou {fragment}=true para sua mensagem.")
    assert not result.is_safe


# ── Propriedades internas do HubSpot ─────────────────────────────────────────


@pytest.mark.parametrize(
    "prop",
    [
        "av_current_step",
        "av_historico_resumido",
        "av_esclarecimento_count",
        "av_fora_escopo_count",
        "av_last_submission_at",
    ],
)
def test_hubspot_internal_properties_detected(prop):
    result = check_output(f"Seu registro foi atualizado: {prop} = novo_valor.")
    assert not result.is_safe


# ── Scoring interno ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "term",
    [
        "score_n2",
        "score_total",
        "score_b",
        "score_a",
        "score_t",
        "tier_from_score",
    ],
)
def test_internal_scoring_terms_detected(term):
    result = check_output(f"Calculamos seu {term} como 85 pontos.")
    assert not result.is_safe


# ── Terminologia de design ────────────────────────────────────────────────────


def test_classificador_interno_detected():
    result = check_output("Sou um classificador interno de qualificação de leads.")
    assert not result.is_safe


def test_enum_fechado_detected():
    result = check_output("Uso um enum fechado para categorizar respostas.")
    assert not result.is_safe


def test_especificacao_tecnica_detected():
    result = check_output("Conforme Especificação Técnica, seção 9, o comportamento é esse.")
    assert not result.is_safe


# ── Case-insensitivity ────────────────────────────────────────────────────────


def test_uppercase_term_detected():
    result = check_output("Seu código é COTACAO_EXCLUSIVA_PRECO.")
    assert not result.is_safe


def test_mixed_case_term_detected():
    result = check_output("Classificado como Tentativa_Injecao_Detectada.")
    assert not result.is_safe


# ── Matched_term retorna o termo correto ──────────────────────────────────────


def test_matched_term_is_populated():
    result = check_output("O sistema usa registrar_sinal para classificar.")
    assert not result.is_safe
    assert "registrar_sinal" in result.matched_term.lower()


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_empty_string_is_safe():
    result = check_output("")
    assert result.is_safe
    assert result.matched_term is None


def test_whitespace_only_is_safe():
    result = check_output("   \n\t  ")
    assert result.is_safe


def test_only_legitimate_terms():
    result = check_output("DB1, Core Up, AI First, BANT, Alana, Open Finance, Staff Augmentation")
    assert result.is_safe
