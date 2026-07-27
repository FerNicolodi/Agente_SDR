"""Testes unitários para validação de output do qa_responder (A3).

Cobre:
- Textos dentro do limite (sem alteração)
- Truncamento suave no último ponto final
- Truncamento duro com reticências
- URLs de domínios DB1 permitidos (não removidas)
- URLs de domínios externos removidas
- Múltiplas URLs misturadas
- Texto vazio
"""
from __future__ import annotations

import pytest

from src.llm.qa_responder import _validate_qa_output, MAX_QA_RESPONSE_LENGTH, _extract_domain


# ── _extract_domain ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("url, expected", [
    ("https://www.db1.com.br/sobre", "www.db1.com.br"),
    ("https://db1group.com/cases", "db1group.com"),
    ("https://apps.db1group.com/deploy", "apps.db1group.com"),
    ("https://evil.com/steal?data=abc", "evil.com"),
    ("https://phishing.db1.com.br.evil.com/page", "phishing.db1.com.br.evil.com"),
    ("https://db1.com.br:8080/path", "db1.com.br"),
    ("https://sub.db1group.com/page", "sub.db1group.com"),
])
def test_extract_domain(url, expected):
    assert _extract_domain(url) == expected


# ── Comprimento: dentro do limite ────────────────────────────────────────────


def test_short_text_unchanged():
    text = "A DB1 tem 26 anos de mercado. Posso seguir?"
    result = _validate_qa_output(text)
    assert result == text


def test_text_at_exact_limit_unchanged():
    text = "a" * MAX_QA_RESPONSE_LENGTH
    result = _validate_qa_output(text)
    assert len(result) <= MAX_QA_RESPONSE_LENGTH


# ── Truncamento suave (último ponto final) ────────────────────────────────────


def test_truncation_at_sentence_boundary():
    # Cria texto longo com ponto final bem antes do limite
    base = "Primeira frase com ponto. " * 10  # ~260 chars, repetida para ultrapassar 500
    long_text = base * 3  # ~780 chars
    result = _validate_qa_output(long_text)
    assert len(result) <= MAX_QA_RESPONSE_LENGTH
    assert result.endswith(".")


def test_truncation_hard_with_ellipsis():
    # Texto longo sem ponto final suficientemente próximo do limite
    # (uma única palavra muito longa sem pontuação)
    long_text = "a" * (MAX_QA_RESPONSE_LENGTH + 200)
    result = _validate_qa_output(long_text)
    assert len(result) <= MAX_QA_RESPONSE_LENGTH + 1  # +1 para o "…"
    assert result.endswith("…")


# ── URLs: domínios DB1 permitidos ─────────────────────────────────────────────


@pytest.mark.parametrize("url", [
    "https://db1.com.br/sobre",
    "https://www.db1.com.br/cases",
    "https://db1group.com",
    "https://www.db1group.com/blog",
    "https://apps.db1group.com",
])
def test_db1_urls_preserved(url):
    text = f"Veja mais em {url} para detalhes."
    result = _validate_qa_output(text)
    assert url in result
    assert "[link removido]" not in result


@pytest.mark.parametrize("url", [
    "https://evil.com/steal",
    "https://phishing.com/db1",
    "https://notdb1.com.br/page",
    "http://attacker.io/exfil?data=xyz",
    # Subdomínio malicioso tentando parecer DB1
    "https://db1.com.br.evil.com/page",
])
def test_external_urls_removed(url):
    text = f"Acesse {url} para mais informações."
    result = _validate_qa_output(text)
    assert url not in result
    assert "[link removido]" in result


def test_subdomains_of_db1_allowed():
    url = "https://sub.db1group.com/page"
    text = f"Confira em {url}."
    result = _validate_qa_output(text)
    assert url in result


def test_multiple_urls_mixed():
    safe_url = "https://db1.com.br/sobre"
    bad_url = "https://evil.com/steal"
    text = f"Veja {safe_url} e também {bad_url} para comparar."
    result = _validate_qa_output(text)
    assert safe_url in result
    assert bad_url not in result
    assert "[link removido]" in result


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_empty_string_unchanged():
    assert _validate_qa_output("") == ""


def test_no_urls_unchanged():
    text = "A DB1 tem mais de 26 anos de mercado. Posso continuar?"
    assert _validate_qa_output(text) == text
