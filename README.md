# Alana — Agente SDR · DB1 Global Software

Agente de qualificação de leads inbound via WhatsApp. Recebe contatos do formulário do site da DGS, conduz a qualificação BANT em 5 etapas (M1–M5), classifica o lead em HOT/WARM/TEPID/COLD e notifica o Closer via Slack com o briefing completo.

**Stack:** Python 3.12 · FastAPI · Anthropic Claude · HubSpot · Z-API (WhatsApp SaaS)

---

## Arquitetura

```
Site DGS → POST /webhook/site-form → Alana envia M1 via WhatsApp
Lead responde M1-M5 → POST /webhook/whatsapp → scoring BANT
Score ≥ 75 (HOT) → task HubSpot + briefing Slack (SLA 2h)
Score 55-74 (WARM) → captura horário → agenda reunião
Score 35-54 (TEPID) → CTA Assessment
Score < 35 (COLD) → encerramento educado
```

Diagrama completo: `arquitetura_alana_sdr.svg`

**Design stateless:** todo estado de negócio vive no HubSpot (propriedades `av_*`). O backend pode ser reiniciado a qualquer momento sem perder dados de leads em andamento.

---

## Pré-requisitos

- Python 3.12+
- Conta HubSpot com Private App token (escopos abaixo)
- Conta Z-API (z-api.io) com instância WhatsApp conectada
- API key Anthropic (Claude Sonnet)
- SMTP configurado (Office 365 ou equivalente)

---

## Configuração do Ambiente

### 1. Clonar e instalar dependências

```bash
git clone <repo-url>
cd Agente_SDR
pip3 install -r requirements.txt
```

### 2. Configurar variáveis de ambiente

Copie o `.env.example` e preencha com valores reais:

```bash
cp .env.example .env
```

| Variável | Descrição | Obrigatório |
|----------|-----------|-------------|
| `ANTHROPIC_API_KEY` | API key Anthropic | ✅ |
| `ZAPI_INSTANCE_ID` | ID da instância Z-API | ✅ |
| `ZAPI_TOKEN` | Token da instância Z-API | ✅ |
| `ZAPI_CLIENT_TOKEN` | Client token de segurança do webhook Z-API | ✅ |
| `SITE_FORM_HMAC_SECRET` | Secret compartilhado com o formulário do site (HMAC) | ✅ |
| `HUBSPOT_API_KEY` | Private App token HubSpot (`pat-na-...`) | ✅ |
| `HUBSPOT_WORKFLOW_HMAC_SECRET` | Secret do Workflow HubSpot que dispara timer-callback | ✅ |
| `SLACK_BOT_TOKEN` | Token do bot Slack (`xoxb-...`) | ✅ |
| `SLACK_CLOSER_CHANNEL` | ID do canal Slack para briefings do Closer | ✅ |
| `STORAGE_BACKEND` | `memory` (padrão, paliativo) ou `hubspot` (produção) | — |
| `ANTHROPIC_MODEL` | Modelo Claude (padrão: `claude-sonnet-5`) | — |
| `ALANA_ENABLED` | Kill switch: `true` para operar, `false` para pausar (padrão: `true`) | — |
| `MAX_QA_RESPONSE_LENGTH` | Tamanho máximo da resposta do qa_responder (padrão: `500`) | — |

> **Segurança:** nunca commite o `.env`. Ele está no `.gitignore`.

### 3. Criar propriedades customizadas no HubSpot

```bash
# Modo dry-run primeiro (não cria nada, só lista o que seria criado):
python3 scripts/hubspot_setup.py --dry-run

# Criar as propriedades:
python3 scripts/hubspot_setup.py
```

Escopos necessários no Private App HubSpot:
- `crm.objects.contacts.read`
- `crm.objects.contacts.write`
- `crm.schemas.contacts.write`

Documentação detalhada: `HUBSPOT_SETUP.md`

---

## Rodando Localmente

```bash
# Subir o servidor em modo desenvolvimento:
python3 -m uvicorn src.main:app --reload --port 8000

# Verificar health:
curl http://localhost:8000/healthz
# → {"status": "ok", "alana_enabled": true}
```

Para expor o webhook localmente para a Z-API, use ngrok ou similar:
```bash
ngrok http 8000
# Use a URL gerada (https://<id>.ngrok.io/webhook/whatsapp) como webhook URL na instância Z-API
```

---

## Testes

### Testes automatizados

```bash
# Rodar todos os testes:
python3 -m pytest tests/ -v

# Testes de segurança isolados:
python3 -m pytest tests/test_security.py -v
python3 -m pytest tests/test_output_guard.py -v
python3 -m pytest tests/test_kill_switch.py -v
```

### Dry-run de conversa completa (sem Z-API, sem HubSpot)

Simula o fluxo M1–M6 com LLM real, scoring real e máquina de estados real. Requer apenas `ANTHROPIC_API_KEY`.

```bash
# Listar personas disponíveis:
python3 scripts/dry_run.py --list

# Modo automático (respostas pré-scriptadas — ideal para regressão):
python3 scripts/dry_run.py --persona banco_hot --auto
python3 scripts/dry_run.py --persona varejo_warm --auto
python3 scripts/dry_run.py --persona d5_preco_real --auto
python3 scripts/dry_run.py --persona curioso_cold --auto

# Modo interativo (você digita as respostas):
python3 scripts/dry_run.py --persona banco_hot
```

**Personas disponíveis:**

| Persona | Resultado esperado |
|---------|-------------------|
| `banco_hot` | HOT direto · score 83 · task imediata |
| `varejo_warm` | WARM · captura horário |
| `budget_aprovado` | HOT · score 88 · bonus budget aprovado |
| `pergunta_se_e_bot` | WARM · disclosure robô + continua |
| `d5_preco_real` | DESQUALIFICADO · D5 (price-driven) |
| `curioso_cold` | COLD · score < 35 |
| `adversario_injecao` | Escalonamento · injeção detectada |
| `fora_escopo_3x` | Escalonamento · 3× fora de escopo |
| `pergunta_aberta` | WARM · qa_responder com histórico |

---

## Deploy (Portal DB1)

Consulte a skill `apps-db1` no Cowork para o passo a passo completo de empacotamento e publicação em `apps.db1group.com`.

Resumo:
1. Build Docker local para validar: `docker build -t alana-sdr .`
2. Empacotar projeto como `.zip` (sem `.env`, sem `__pycache__`)
3. Upload no Portal de Deploy DB1
4. Configurar variáveis de ambiente no painel do portal
5. Verificar: `curl https://<subdominio>.apps.db1group.com/healthz`

---

## Estrutura do Projeto

```
src/
├── main.py                    # Entrypoint FastAPI + kill switch + startup validation
├── routes/
│   ├── site_form.py           # POST /webhook/site-form (entrada do lead)
│   ├── whatsapp.py            # POST /webhook/whatsapp (conversa M1-M5)
│   └── timer_callback.py      # POST /webhook/timer-callback (silêncio HubSpot)
├── llm/
│   ├── signal_extractor.py    # Classifica resposta do lead (enum fechado)
│   ├── qa_responder.py        # Responde perguntas abertas do lead
│   ├── message_composer.py    # Personaliza perguntas M3-M5 com contexto
│   └── prompts/
│       ├── system_prompt.py   # System prompt do extrator de sinal
│       ├── messages.py        # Copy fixa aprovada (M1-M6, fallbacks)
│       └── knowledge_base.py  # Base de conhecimento DB1/DGS para qa_responder
├── scoring/
│   ├── rules.py               # Funções de score BANT + AI First Receptiveness
│   └── disqualifiers.py       # Checagem de desqualificadores D1-D7
├── state_machine/
│   ├── states.py              # Enum AVStep (estados M1-M6)
│   └── transitions.py        # Funções de transição de estado
├── integrations/
│   ├── hubspot_client.py      # Upsert, find, create task no HubSpot
│   ├── whatsapp_client.py     # Envio de mensagem via Z-API
│   ├── slack_client.py        # Notificação do Closer
│   └── email_client.py        # Notificação interna SMTP
└── lib/
    ├── logger.py              # Logger estruturado com PII masking
    ├── security.py            # HMAC verification + input sanitization
    └── output_guard.py        # Scan de output LLM contra vazamento de internals

config/
└── scoring_weights.yaml       # Pesos BANT, thresholds HOT/WARM/TEPID/COLD

scripts/
├── dry_run.py                 # Harness de teste local sem dependências externas
└── hubspot_setup.py           # Setup inicial de propriedades customizadas HubSpot

tests/
├── test_security.py
├── test_output_guard.py
├── test_kill_switch.py
└── test_qa_output_validation.py
```

---

## Documentação Complementar

| Arquivo | Conteúdo |
|---------|----------|
| `SECURITY.md` | Runbook de segurança: kill switch, resposta a incidentes, checklist pré go-live |
| `APROVACOES.md` | Registro de aprovações formais de copy e regras de negócio |
| `HUBSPOT_SETUP.md` | Guia detalhado de configuração do HubSpot |
| `arquitetura_alana_sdr.svg` | Diagrama de arquitetura completo |
| `c4_system_prompts.html` | Diagrama C4 dos system prompts |

---

## Responsável

Fernando Nicolodi — Head de Novos Negócios · DB1 Global Software  
fernando.nicolodi@db1.com.br
