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
| **#10** | ~~Submeter template M1 no Meta Business Manager~~ — **N/A**: migração para Z-API elimina necessidade de aprovação de template pela Meta. Z-API envia mensagens livres sem template. Número (44) 99180-9333 conectado em 2026-07-21. |

---

## Migração de Canal WhatsApp — Meta/Evolution API → Z-API

**Data:** 2026-07-21
**Aprovado por:** Fernando Nicolodi
**Status:** ✅ Implementado e em produção

**Decisão:**
Canal WhatsApp migrado de Meta Cloud API (planejado originalmente) e Evolution API (intermediário) para Z-API (z-api.io), SaaS gerenciado. Número conectado: **(44) 99180-9333** (número comercial DB1).

**Motivação:**
- Z-API não exige aprovação de template pela Meta para envio de mensagens
- Setup mais rápido (sem Meta Business Manager)
- Autenticação via `ZAPI_INSTANCE_ID` + `ZAPI_TOKEN` + `ZAPI_CLIENT_TOKEN`

**Impacto técnico:**
- `src/integrations/whatsapp_client.py` — reescrito para Z-API REST
- `src/routes/whatsapp.py` — auth aceita `client-token` (quando Security Token configurado no painel) e `z-api-token` como fallback
- `SITE_FORM_HMAC_SECRET` permanece para autenticação do formulário do site (independente do canal)

**Arquivos alterados:** `src/integrations/whatsapp_client.py`, `src/routes/whatsapp.py`, `.env.example`

---

## Decisões de Segurança — Revisão Pré-Produção 2026-07-27

**Data:** 2026-07-27
**Aprovado por:** Fernando Nicolodi (implícito — revisão conduzida e aceita em sessão)
**Status:** ✅ CRIT-01 e CRIT-02 implementados · P1 pendente (decisão de arquitetura)

### CRIT-01 — Gate de segredos em arquivos .zip
Arquivos `.zip` com `.env` real (segredos em texto puro) estavam soltos na raiz do projeto sem cobertura do `.gitignore` — risco de commit acidental permanente. Corrigido: `*.zip` e `*.tar.gz` adicionados ao `.gitignore`; arquivos removidos do disco.

### CRIT-02 — Gate `MEMORY_STORAGE_ACK` para modo memória
`STORAGE_BACKEND=memory` subia em produção com apenas um `logger.warning`. Corrigido: `src/main.py` agora exige `MEMORY_STORAGE_ACK=true` explícito para inicializar em modo memória. Sem o ack, servidor recusa subir.

**Decisão aceita:** `STORAGE_BACKEND=memory` com `MEMORY_STORAGE_ACK=true` em homologação enquanto `HUBSPOT_API_KEY` não for corrigida (token atual retorna 401). Em produção real: obrigatório `STORAGE_BACKEND=hubspot`.

### P1 — Sem try/except em chamadas a integrações externas (PENDENTE)
~32 chamadas a Z-API, HubSpot e Slack nas rotas de webhook sem tratamento de erro. Confirmado em homologação: falha no Z-API derruba requisição com 500, lead fica travado sem alerta. **Decisão de arquitetura pendente com Fernando antes de implementar.**

---

## Atualização de ICP — Faturamento Mínimo e Ideal

**Data:** 2026-07-29
**Aprovado por:** Fernando Nicolodi
**Status:** ✅ Implementado

**Mudança:**
| Critério | Antes | Depois |
|----------|-------|--------|
| Faturamento mínimo para considerar no ICP | R$ 50M/ano | R$ 100M/ano |
| Faturamento ideal (perfil preferencial) | R$ 500M/ano (Enterprise) | R$ 300M/ano |

**Novos brackets de pontuação budget:**
| Faturamento | Porte | Pontos |
|-------------|-------|--------|
| ≥ R$ 300M/ano | Empresa Ideal ICP | 25 pts |
| R$ 100M–299M/ano | Mid-Market ICP | 15 pts |
| < R$ 100M/ano | Abaixo do ICP | 0 pts |

**Arquivo alterado:** `config/scoring_weights.yaml`

> ⚠️ O documento `Score_Agente SDR DGS_Bant_2026.docx` precisa ser atualizado manualmente para refletir estes novos valores — é a fonte de verdade de negócio referenciada pelo YAML.

---
