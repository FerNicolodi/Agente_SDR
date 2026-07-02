"""Tabela de transições da conversa (Especificação Técnica, seção 8).

`next_step` é a única função que decide qual mensagem vem a seguir. A rota
routes/whatsapp.py chama esta função depois que scoring/rules.py já pontuou
a resposta — este módulo não pontua nada, só decide fluxo.
"""
from __future__ import annotations

from .states import AVStep


def next_step_after_m1(codigos: list[str]) -> AVStep:
    if "pediu_ligacao_direta" in codigos:
        return AVStep.FECHAMENTO_HOT  # fechamento HOT direto, ver Script M1
    if "afirmativo" in codigos:
        return AVStep.M2_ENVIADA
    return AVStep.M1_ENVIADA  # aguarda reengajamento em 24h se não houver outra resposta


def next_step_after_m2(codigos: list[str]) -> AVStep:
    """Se o sinal de dor for o de maior severidade (sistema_parou), pula a M3
    e vai direto para a M4, conforme o Script do Atendente Virtual."""
    return AVStep.M4_ENVIADA if "sistema_parou" in codigos else AVStep.M3_ENVIADA


def next_step_after_m3() -> AVStep:
    return AVStep.M4_ENVIADA


def next_step_after_m4() -> AVStep:
    return AVStep.M5_ENVIADA


def next_step_after_m5(tier: str) -> AVStep:
    return {
        "HOT": AVStep.FECHAMENTO_HOT,
        "WARM": AVStep.FECHAMENTO_WARM,
        "TEPID": AVStep.FECHAMENTO_TEPID,
        "COLD": AVStep.FECHAMENTO_COLD,
        "DESQUALIFICADO": AVStep.FECHAMENTO_DESQUALIFICADO,
    }[tier]


def next_step_after_silencio(step_atual: AVStep, ja_reengajado: bool) -> AVStep:
    """Chamado pelo endpoint /webhook/timer-callback quando um HubSpot Workflow
    detecta silêncio do lead (24h ou 48h)."""
    if ja_reengajado:
        return AVStep.MOVIDO_NURTURE
    return AVStep.REENGAJAMENTO_ENVIADO
