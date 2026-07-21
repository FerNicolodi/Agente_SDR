# HubSpot — Setup Manual (Task #9)

Guia de configuração das propriedades customizadas do contato que o Agente SDR lê e escreve.
Todas devem ser criadas em **Configurações → Propriedades → Contato → Criar propriedade**.

---

## Propriedades de Controle do Fluxo

| Nome interno           | Rótulo                       | Tipo         | Valores / Notas                                                 |
|------------------------|------------------------------|--------------|-----------------------------------------------------------------|
| `av_current_step`      | SDR: Etapa Atual             | Texto        | Enum gerenciado pelo agente. Ver lista de valores abaixo.       |
| `av_historico_resumido`| SDR: Histórico Resumido      | Texto longo  | JSON compacto dos últimos 10 turnos. Não editar manualmente.    |
| `av_esclarecimento_count` | SDR: Contador de Esclarecimentos | Número  | Resetado a 0 a cada avanço de etapa.                            |
| `av_fora_escopo_count` | SDR: Contador Fora do Escopo | Número       | Resetado a 0 ao responder dentro do escopo.                     |

**Valores válidos de `av_current_step`:**
`m1_enviada`, `m2_enviada`, `m3_enviada`, `m4_enviada`, `m5_enviada`,
`aguardando_horario`, `fechamento_hot`, `fechamento_warm`, `fechamento_tepid`,
`fechamento_cold`, `fechamento_desqualificado`, `reengajamento_enviado`, `movido_nurture`

---

## Propriedades de Scoring BANT

| Nome interno         | Rótulo                   | Tipo    | Notas                                                       |
|----------------------|--------------------------|---------|-------------------------------------------------------------|
| `score_b`            | Score: Budget            | Número  | 0–25 pts + bônus                                            |
| `score_a`            | Score: Autoridade        | Número  | 0–15 pts (ajustável pela M4)                                |
| `score_n1`           | Score: Necessidade Setor | Número  | 0–15 pts                                                    |
| `score_n2`           | Score: Sinais de Dor     | Número  | 0–15 pts (cap aplicado)                                     |
| `score_n3`           | Score: Tecnografia       | Número  | 0–10 pts (cap aplicado)                                     |
| `score_t`            | Score: Timeline          | Número  | 0–20 pts                                                    |
| `score_bonus`        | Score: Bônus             | Número  | Budget aprovado (+5), Lucro Real (+3)                       |
| `score_total`        | Score: Total BANT        | Número  | Soma de B+A+N1+N2+N3+T+Bônus. Calculado em M5.             |

---

## Propriedade de AI First Receptiveness (adicionada em 2026-07-08 — G2)

| Nome interno      | Rótulo                        | Tipo         | Valores                                      |
|-------------------|-------------------------------|--------------|----------------------------------------------|
| `score_ai_first`  | SDR: Score AI First           | Número       | 0 (baixa), 2 (media), 5 (alta)               |
| `ai_first_nivel`  | SDR: Receptividade AI First   | Texto        | `alta` \| `media` \| `baixa`                 |

> Capturada oportunisticamente na M2, sem pergunta dedicada. Não compõe o `score_total` BANT — é dimensão auxiliar para orientação de oferta no briefing do Closer.

---

## Propriedades de Qualificação (preenchidas pelo formulário + agente)

| Nome interno          | Rótulo                    | Tipo    | Origem                                           |
|-----------------------|---------------------------|---------|--------------------------------------------------|
| `n2_signal`           | SDR: Sinais de Dor (códigos) | Texto | Códigos separados por vírgula. Ex: `backlog_represado,vaga_senior_aberta` |
| `tier`                | SDR: Tier                 | Texto   | `HOT` \| `WARM` \| `TEPID` \| `COLD` \| `DESQUALIFICADO` |
| `oferta_recomendada`  | SDR: Oferta Recomendada   | Texto   | Ex: `Core Up + Tech Talent`                      |
| `setor_categoria`     | SDR: Categoria de Setor   | Texto   | Código interno. Ex: `finance_tradicional`        |
| `cargo_categoria`     | SDR: Categoria de Cargo   | Texto   | Código interno. Ex: `cto_vp_head_ti`             |
| `faturamento_estimado`| SDR: Faturamento Estimado | Texto   | Faixa. Ex: `R$ 100M–500M`                       |
| `desafios`            | Desafios (formulário)     | Texto longo | Campo do formulário do site. Já deve existir. |
| `cargo`               | Cargo (formulário)        | Texto   | Campo do formulário do site. Já deve existir.    |

---

## Workflows a Configurar

### 1. Reengajamento por silêncio (24h)
- **Gatilho:** `av_current_step` = qualquer etapa ativa (M1–M5) **E** nenhuma atividade de mensagem em 24h
- **Ação:** Chamar endpoint `POST /webhook/timer-callback` com `contact_id`

### 2. Reengajamento por silêncio (48h — segunda tentativa)
- **Gatilho:** `av_current_step` = `reengajamento_enviado` **E** nenhuma atividade em 48h
- **Ação:** Chamar endpoint `POST /webhook/timer-callback` com `contact_id` e `ja_reengajado=true`

---

## Observações

- Todas as propriedades prefixadas com `av_` são exclusivas do agente SDR e **não devem ser editadas manualmente** durante o fluxo ativo.
- `score_total` e `tier` podem ser consultados no CRM para filtros e relatórios de pipeline.
- Sempre que uma nova propriedade for adicionada ao código, atualizar este arquivo antes de fazer deploy.
