# Registro de Aprovações — Agente SDR DGS

Documento que registra aprovações formais de copy, regras de negócio e decisões de produto feitas por Fernando Nicolodi (Head de Novos Negócios, DB1 Global Software) antes de cada item ir a produção ou submissão externa.

---

## Template M1 WhatsApp — `abertura_qualificacao_v1`

**Data de aprovação:** 2026-07-08
**Aprovado por:** Fernando Nicolodi
**Status:** ✅ Aprovado — pronto para submissão à Meta

**Texto aprovado:**

> Olá, {{1}}! Aqui é a Alana, analista comercial da DGS. Vi que você entrou em contato com a gente pela DB1 e quero entender melhor o seu contexto antes de te conectar com o especialista certo. Leva menos de 5 minutos, posso te fazer algumas perguntas rápidas?

**Parâmetro:** `{{1}}` = primeiro nome do lead

**Alterações em relação ao rascunho anterior:**
- Travessão `—` substituído por vírgula `,` antes de "posso te fazer algumas perguntas rápidas?" para tom mais humanizado.

**Arquivo de implementação:** `src/llm/prompts/messages.py` → constante `M1_ABERTURA`

**Próximo passo:** Submeter via Meta Business Manager com categoria `UTILITY`, nome `abertura_qualificacao_v1`, um parâmetro de corpo `{{1}}`.

---

## Mensagem M6 TEPID — `M6_FECHAMENTO_TEPID`

**Data de aprovação:** 2026-07-08
**Aprovado por:** Fernando Nicolodi
**Status:** ✅ Aprovado

**Texto aprovado:**

> {nome}, faz sentido! Temos um Assessment de 3 etapas — Técnica, Negócios e Gestão — que costuma ser o ponto de partida ideal para empresas do setor de {setor} que estão avaliando por onde começar. Nosso especialista pode te explicar como funciona. Tem algum horário que funciona essa semana?

**Motivação da alteração:**
Versão anterior prometia "conteúdos" sem CTA concreto. Nova versão oferece o Assessment como próximo passo de baixo risco — TEPID é o perfil ideal (interesse confirmado, budget/timing indefinidos). Alinhado à skill `dgs-assessment-pitch` do plugin Sales DGS AI First.

**Arquivo de implementação:** `src/llm/prompts/messages.py` → constante `M6_FECHAMENTO_TEPID`

---

## G2 — AI First Receptiveness Scoring

**Data de implementação:** 2026-07-08
**Aprovado por:** Fernando Nicolodi
**Status:** ✅ Implementado

**O que foi adicionado:**
- Dois novos códigos no extrator de sinal M2: `ia_interesse_explicito` e `ia_resistencia_explicita`, retornados oportunisticamente quando o lead expressa posição explícita sobre IA (sem pergunta dedicada).
- Função `score_ai_first()` em `rules.py` — retorna pontos e nível (`alta` / `media` / `baixa`).
- Dimensão `ai_first` / `ai_first_nivel` no `ScoreBreakdown` — **não soma ao total BANT** para não inflar tier; é dimensão auxiliar de orientação de oferta.
- Propriedades `score_ai_first` e `ai_first_nivel` persistidas no HubSpot a partir da M2.
- Briefing do Closer atualizado: exibe receptividade + hint de oferta (`→ priorizar GenAI/Agentic Squad` ou `→ evitar pitch AI First como abertura`).
- Regra 11 adicionada ao `system_prompt.py` com exemplos reais de uso.

**Arquivos alterados:**
- `config/scoring_weights.yaml`
- `src/scoring/rules.py`
- `src/llm/prompts/system_prompt.py`
- `src/routes/whatsapp.py`

---

## G3 — Processo de Sync do knowledge_base.py

**Data de implementação:** 2026-07-08
**Aprovado por:** Fernando Nicolodi
**Status:** ✅ Implementado

**O que foi adicionado:**
Cabeçalho expandido em `knowledge_base.py` com: data da última sync, lista de skills de referência, lista de gatilhos que obrigam revisão, checklist de itens a verificar e responsável.

**Arquivo alterado:** `src/llm/prompts/knowledge_base.py`

**Próxima revisão obrigatória:** sempre que uma das skills `db1-fundacao`, `db1-global-software-perfil-estrategico` ou `dgs-contexto-knowledge` for atualizada no plugin.

---

## Validação Técnica — Sessão 2026-07-08

**Validado por:** Agente + aprovação Fernando Nicolodi  
**Escopo:** todos os arquivos alterados nesta sessão

### Resultado: ✅ Sem inconsistências críticas

| Arquivo | Alteração | Status |
|---|---|---|
| `src/llm/prompts/messages.py` | M1 vírgula + M6 TEPID → Assessment CTA | ✅ |
| `config/scoring_weights.yaml` | Seção `ai_first_receptiveness` adicionada | ✅ |
| `src/scoring/rules.py` | `score_ai_first()` + campos em `ScoreBreakdown` | ✅ |
| `src/llm/prompts/system_prompt.py` | Regra 11 (AI First Receptiveness) | ✅ |
| `src/routes/whatsapp.py` | Import, STEP_VALID_CODES M2, `_handle_m2`, briefing | ✅ |
| `src/llm/prompts/knowledge_base.py` | Cabeçalho de sync process | ✅ |
| `HUBSPOT_SETUP.md` | Criado — guia completo de propriedades customizadas | ✅ |

### Pontos verificados

- `ai_first` **não** é somado ao `score_total` BANT — tier preservado comparável entre leads.
- Separação de `codigos_dor` vs `codigos_ai` em `_handle_m2` garante que `score_n2`, `transitions` e `n2_signal` nunca recebem os códigos de AI First.
- `score_ai_first` e `ai_first_nivel` precisam ser criados como propriedades customizadas no HubSpot — documentado em `HUBSPOT_SETUP.md`.
- `knowledge_base.py` sincronizado em 2026-07-08; próxima revisão obrigatória na próxima atualização das skills de referência.

### Pendências antes do go-live

| Task | Descrição |
|---|---|
| **#9** | Criar propriedades customizadas no HubSpot (ver `HUBSPOT_SETUP.md`) |
| **#10** | Submeter template M1 `abertura_qualificacao_v1` no Meta Business Manager |

---
