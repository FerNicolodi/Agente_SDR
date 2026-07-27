"""Estados da conversa (propriedade av_current_step no HubSpot).

O HubSpot é o único armazenamento de estado — o backend é stateless entre
requisições (ver Especificação Técnica, seção 3: container sem persistência
no Portal de Deploy DB1).
"""
from enum import Enum


class AVStep(str, Enum):
    AGUARDANDO_M1 = "aguardando_m1"
    M1_ENVIADA = "m1_enviada"
    M2_ENVIADA = "m2_enviada"
    M3_ENVIADA = "m3_enviada"
    M4_ENVIADA = "m4_enviada"
    M5_ENVIADA = "m5_enviada"
    # Estado intermediário: M6 WARM/HOT_DIRETO foi enviado e aguardamos o
    # lead informar o horário preferencial. Não é terminal — o backend ainda
    # precisa processar a resposta para confirmar o agendamento e criar a Task
    # no HubSpot com o horário correto.
    AGUARDANDO_HORARIO = "aguardando_horario"
    FECHAMENTO_HOT = "fechamento_hot"
    FECHAMENTO_WARM = "fechamento_warm"
    FECHAMENTO_TEPID = "fechamento_tepid"
    FECHAMENTO_COLD = "fechamento_cold"
    FECHAMENTO_DESQUALIFICADO = "fechamento_desqualificado"
    REENGAJAMENTO_ENVIADO = "reengajamento_enviado"
    MOVIDO_NURTURE = "movido_nurture"


TERMINAL_STEPS = {
    AVStep.FECHAMENTO_HOT,
    AVStep.FECHAMENTO_WARM,
    AVStep.FECHAMENTO_TEPID,
    AVStep.FECHAMENTO_COLD,
    AVStep.FECHAMENTO_DESQUALIFICADO,
    AVStep.MOVIDO_NURTURE,
}
