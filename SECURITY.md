# SECURITY — Alana SDR · DB1 Global Software

> Runbook de resposta a incidentes de segurança do Agente SDR (Alana).  
> Responsável: Fernando Nicolodi · fernando.nicolodi@db1.com.br  
> Última revisão: 2026-07-17

---

## 1. Classificação de Severidade

| Nível | Critério | Tempo de resposta |
|-------|----------|-------------------|
| **P0 — Crítico** | Vazamento confirmado de dados de lead (PII), system prompt exposto ao lead, acesso indevido ao HubSpot/Slack | Imediato — acionar kill switch e escalar em até 15 min |
| **P1 — Alto** | Ataque de injeção bem-sucedido (tentativa_injecao_detectada não bloqueou a ação), output guard falhou e texto interno vazou | Acionar kill switch em até 1h, investigar logs |
| **P2 — Médio** | Volume anormal de tentativas de injeção (> 10 em 1h de um mesmo número), taxa de `confianca=baixa` acima de 30% | Investigar logs, notificar equipe técnica em até 4h |
| **P3 — Baixo** | Falso positivo de injeção bloqueando lead legítimo, output truncado incorretamente | Investigar e corrigir no próximo ciclo |

---

## 2. Kill Switch — Procedimento Imediato

Para desativar a Alana instantaneamente **sem redeploy**:

```bash
# No ambiente de produção (Portal de Deploy DB1):
# 1. Acesse as variáveis de ambiente do app
# 2. Altere ALANA_ENABLED de "true" para "false"
# 3. Salve — o middleware bloqueia todas as rotas em <1s

# Verificar se o kill switch está ativo:
curl https://<seu-dominio>.apps.db1group.com/healthz
# Resposta esperada com kill switch ativo:
# {"status": "ok", "alana_enabled": false}
```

**O que acontece quando desativada:**
- Todos os webhooks (`/webhook/whatsapp`, `/webhook/site-form`) retornam `200 {"status":"disabled"}`
- O Meta/WhatsApp não recebe erro — não tenta reenviar o webhook
- `/healthz` permanece acessível para o orquestrador de contêiner não reiniciar o serviço
- Leads em andamento ficam pausados no estado atual do HubSpot — nenhum dado é perdido

**Para reativar:**
```bash
# Reverter ALANA_ENABLED para "true" nas variáveis de ambiente
# Verificar: curl .../healthz → {"alana_enabled": true}
```

---

## 3. Localização dos Logs

| Tipo de log | Onde encontrar | O que buscar |
|-------------|----------------|--------------|
| Tentativas de injeção (input) | Stdout do container / arquivo `logs/security.log` | `"tentativa_injecao_detectada"`, `"attack_vector"` |
| Output guard disparado | Stdout / `logs/security.log` | `"output_guard_triggered"` |
| Kill switch acionado | Stdout / `logs/security.log` | `"Kill switch ativo"` |
| Tool calls (HubSpot/Slack/WhatsApp) | Stdout / `logs/app.log` | `"tool_call"` |
| Rate limit atingido | Stdout / `logs/app.log` | `429` |

**Filtrar eventos de segurança em produção:**
```bash
# Injeções detectadas (últimas 24h):
docker logs <container> 2>&1 | grep "tentativa_injecao_detectada"

# Output guard disparado:
docker logs <container> 2>&1 | grep "output_guard_triggered"

# Via arquivo de log (se M2 configurado):
tail -f logs/security.log | grep -E "injection|guard|kill_switch"
```

---

## 4. Resposta por Cenário

### 4.1 Injeção de Prompt Detectada (P1/P2)
```
1. Verificar log: qual attack_vector? (role_indicator_direct / url_encoded / base64 / post_llm_signal_extractor)
2. Verificar contact_id no HubSpot — o lead foi avançado indevidamente?
3. Se sim → reverter manualmente o av_current_step no HubSpot para o estado anterior
4. Se volume alto (> 10 em 1h) → acionar kill switch e investigar origem
5. Registrar em: https://github.com/<repo>/issues com label "security"
```

### 4.2 Output Guard Disparado (P1)
```
1. Verificar matched_term no log — qual termo interno vazou?
2. Verificar se o fallback foi enviado corretamente ao lead
3. Revisar o prompt do LLM que gerou o termo — possível regressão ou ataque indireto
4. Se o matched_term é legítimo (falso positivo) → remover de _GUARD_TERMS em output_guard.py
5. Se é ataque real → investigar o contexto injetado pelo lead
```

### 4.3 Vazamento de PII (P0)
```
1. Acionar kill switch IMEDIATAMENTE
2. Notificar: fernando.nicolodi@db1.com.br + equipe de segurança DB1
3. Identificar quais dados vazaram e para onde (log de tool calls)
4. Seguir protocolo LGPD da DB1 Group (prazo: 72h para notificação ao titular)
5. Não reativar sem revisão completa dos logs e correção do vetor
```

### 4.4 Falso Positivo Bloqueando Lead (P3)
```
1. Identificar a mensagem que foi bloqueada (log: raw_length, attack_vector)
2. Testar em tests/test_security.py com a mensagem como novo caso
3. Ajustar _ROLE_INDICATOR_RE ou threshold de base64 em security.py
4. Garantir que o novo teste passe antes de fazer deploy
5. Contatar o lead manualmente via Slack se necessário
```

---

## 5. Contatos de Escalada

| Situação | Contato | Canal |
|----------|---------|-------|
| Incidente de segurança (qualquer severidade) | Fernando Nicolodi | fernando.nicolodi@db1.com.br |
| Infra / Portal de Deploy | Time DevOps DB1 | Canal Slack #devops-db1 |
| Vazamento de dados (P0) | DPO DB1 Group | dpo@db1.com.br |
| Problema na API Meta/WhatsApp | Suporte Meta Business | business.facebook.com/support |

---

## 6. Checklist Pré Go-Live

- [ ] Variável `ALANA_ENABLED=true` definida no ambiente de produção
- [ ] `SITE_FORM_HMAC_SECRET` configurado e testado
- [ ] `META_APP_SECRET` e `META_WA_VERIFY_TOKEN` configurados
- [ ] `/healthz` retornando `{"status":"ok","alana_enabled":true}`
- [ ] Kill switch testado: set `ALANA_ENABLED=false` → verificar bloqueio → reverter
- [ ] Logs de segurança visíveis no painel do Portal de Deploy
- [ ] Pelo menos um número de teste executou o fluxo completo M1→M6
- [ ] Closer configurado no Slack (`SLACK_CLOSER_CHANNEL`)
- [ ] Scans C4 (breakmyagent.ai) com score ≥ 75 para os 3 prompts
- [ ] Este SECURITY.md revisado e aprovado por Fernando Nicolodi

---

## 7. Itens de Segurança Implementados (Referência)

| ID | Camada | Arquivo | Status |
|----|--------|---------|--------|
| C1 | Input sanitization (zero-width + role indicators) | `src/lib/security.py` | ✅ |
| C2 | Detecção URL/Base64 encoded + attack_vector logging | `src/lib/security.py` | ✅ |
| C3 | Output guard (vazamento de internals LLM) | `src/lib/output_guard.py` | ✅ |
| C4 | System prompt hardening (identidade, hierarquia, confidencialidade) | `src/llm/prompts/` | ✅ |
| A1 | Tool call logging com PII masking | `src/integrations/` | ✅ |
| A2 | Kill switch `ALANA_ENABLED` + `/healthz` | `src/main.py` | ✅ |
| A3 | Validação output qa_responder (truncamento + URL allowlist) | `src/llm/qa_responder.py` | ✅ |
| A4 | External content labeling nos prompts LLM | `src/llm/qa_responder.py`, `src/llm/message_composer.py` | ✅ |
| M1 | Este documento | `SECURITY.md` | ✅ |
| M2 | Log storage separado (arquivo rotativo) | `src/lib/logger.py` | ✅ |
| M3 | Monitoramento de dependências (pip-audit CI) | `.github/workflows/security-audit.yml` | ✅ |
| M4 | Sanitização campo desafios (site_form) | `src/routes/site_form.py` | ✅ |
