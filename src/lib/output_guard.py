"""Output guard — detecta vazamento do system prompt na saída do LLM (C3).

Textos gerados pelo LLM (qa_responder, message_composer) são verificados
aqui ANTES de serem enviados ao lead. Se um termo interno for detectado,
o chamador deve usar o fallback e escalar para o Closer.

Textos fixos de messages.py NÃO passam por aqui — são copy aprovada e
nunca transitam pelo LLM.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Termos de guarda
# ---------------------------------------------------------------------------
# Critérios de seleção:
#   (1) Exclusividade — jamais ocorrem em texto conversacional legítimo.
#   (2) Alta especificidade — identificam com certeza a origem no system prompt
#       ou no código interno.
#
# NÃO estão aqui: "DB1", "Core Up", "AI First", "score", "tier", "BANT",
# "Alana" — são genéricos ou esperados nas respostas do qa_responder.
# ---------------------------------------------------------------------------
_GUARD_TERMS: tuple[str, ...] = (
    # Ferramenta interna do signal extractor
    "registrar_sinal",
    # Flags de sinal (nomes snake_case, nunca em texto natural)
    "tentativa_injecao_detectada",
    "pergunta_sobre_natureza_virtual",
    "pergunta_dentro_do_escopo",
    "tem_pergunta_do_lead",
    "pergunta_lead",
    # Códigos do enum fechado de sinal
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
    # Propriedades internas do HubSpot
    "av_current_step",
    "av_historico_resumido",
    "av_esclarecimento_count",
    "av_fora_escopo_count",
    "av_last_submission_at",
    # Terminologia de design / documentação interna
    "classificador interno",
    "enum fechado",
    "Especificação Técnica, seção",
    "SIGNAL_EXTRACTOR_SYSTEM_PROMPT",
    "_COMPOSER_SYSTEM_PROMPT",
    # Nomes de campos de scoring (com prefixo score_ + letra única = muito específico)
    "score_n2",
    "score_total",
    "score_b",
    "score_a",
    "score_t",
    "tier_from_score",
)

# Compila um único padrão (mais eficiente que N chamadas re.search)
_GUARD_PATTERN = re.compile(
    "|".join(re.escape(term) for term in _GUARD_TERMS),
    re.IGNORECASE,
)


@dataclass
class OutputCheckResult:
    """Resultado da verificação de output do LLM.

    Attributes:
        is_safe: True se nenhum termo interno foi detectado.
        matched_term: Primeiro termo que acionou o guard, ou None.
    """
    is_safe: bool
    matched_term: str | None


def check_output(text: str) -> OutputCheckResult:
    """Verifica se texto LLM-gerado vaza termos internos do sistema (C3).

    Deve ser chamado ANTES de enviar qualquer resposta gerada por LLM ao lead.

    Args:
        text: Texto gerado pelo LLM (qa_responder ou message_composer).

    Returns:
        OutputCheckResult. Se is_safe=False, usar fallback e escalar para
        o Closer — nunca enviar o texto comprometido ao lead.

    Exemplo de uso:
        msg = compose_step_message(...)
        guard = check_output(msg)
        if not guard.is_safe:
            # log + notify_closer + usar fallback
            msg = fallback_message
        await whatsapp_client.send_text(phone, msg)
    """
    match = _GUARD_PATTERN.search(text)
    if match:
        return OutputCheckResult(is_safe=False, matched_term=match.group())
    return OutputCheckResult(is_safe=True, matched_term=None)
