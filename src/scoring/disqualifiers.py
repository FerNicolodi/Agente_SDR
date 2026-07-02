"""Checagem de desqualificadores automáticos D1-D7.

Deve rodar ANTES de qualquer roteamento HOT/WARM automático, independente do
score total (ver Especificação Técnica, seção 10.1 — "Desqualificadores
D1-D7 sempre verificados antes de qualquer ação HOT automática").

As flags de entrada vêm de pesquisa do SDR (LinkedIn, Receita Federal, notícias)
e/ou de sinais explícitos na conversa (ex.: D5 detectado na Mensagem 5). Este
módulo não faz a pesquisa — só decide o resultado a partir de flags booleanas
já levantadas por outra camada (humana ou de enriquecimento automatizado).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DisqualifierFlags:
    d1_tech_native_muitas_vagas: bool = False
    d2_startup_menor_100_func: bool = False
    d3_corte_orcamento_ti: bool = False
    d4_time_ti_menor_10: bool = False
    d5_decisao_por_preco: bool = False
    d6_squad_interno_especializado: bool = False
    d7_fintech_internalizando_time: bool = False


_LABELS = {
    "d1_tech_native_muitas_vagas": "D1",
    "d2_startup_menor_100_func": "D2",
    "d3_corte_orcamento_ti": "D3",
    "d4_time_ti_menor_10": "D4",
    "d5_decisao_por_preco": "D5",
    "d6_squad_interno_especializado": "D6",
    "d7_fintech_internalizando_time": "D7",
}


@dataclass
class DisqualificationResult:
    desqualificado: bool
    codigos: list[str] = field(default_factory=list)


def check_disqualifiers(flags: DisqualifierFlags) -> DisqualificationResult:
    codigos = [
        _LABELS[field_name]
        for field_name in _LABELS
        if getattr(flags, field_name)
    ]
    return DisqualificationResult(desqualificado=bool(codigos), codigos=codigos)
