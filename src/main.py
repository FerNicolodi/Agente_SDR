"""Ponto de entrada do backend do Agente SDR (Portal de Deploy DB1).

Roda 100% stateless — todo estado de negócio vive no HubSpot (Especificação
Técnica, seção 3). O Dockerfile na raiz do repositório sobe este app com
`uvicorn src.main:app --host 0.0.0.0 --port 8000`.

Kill switch (A2): defina ALANA_ENABLED=false no ambiente para desativar
todos os webhooks instantaneamente sem redeploy. O /healthz permanece
acessível para que o orquestrador de contêiner não reinicie o serviço.

HIGH-01: secrets obrigatórios são validados no startup via lifespan — se
ausentes ou com valor placeholder, o servidor não sobe e o erro aparece
nos logs antes do primeiro request.
"""
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response

# Carrega variáveis do .env (necessário quando o app roda via Docker com .env no filesystem)
load_dotenv()

from .lib.logger import get_logger
from .routes import site_form, timer_callback, whatsapp

logger = get_logger(__name__)

# Secrets obrigatórios para operação segura em produção.
# Valores placeholder (padrão do .env.example) são rejeitados
# da mesma forma que ausência total — ambos resultariam em HMAC
# inválido aceitando qualquer requisição.
_REQUIRED_SECRETS = [
    "ANTHROPIC_API_KEY",
    "ZAPI_INSTANCE_ID",
    "ZAPI_TOKEN",
    "ZAPI_CLIENT_TOKEN",
    "SITE_FORM_HMAC_SECRET",
    "HUBSPOT_WORKFLOW_HMAC_SECRET",
    "HUBSPOT_API_KEY",
]
_PLACEHOLDER_PREFIXES = ("fake_", "troque_por", "sk-ant-...")


def _validate_secrets() -> None:
    """Lança RuntimeError se algum secret obrigatório estiver ausente ou
    com valor placeholder. Chamado no lifespan antes de aceitar tráfego.

    Quando STORAGE_BACKEND=memory, HUBSPOT_API_KEY é dispensável — o app
    roda sem HubSpot usando armazenamento em memória (modo paliatvo).

    CRIT-02 (revisão de segurança pré-produção, 2026-07-27): STORAGE_BACKEND=memory
    quebra a premissa central da arquitetura (Especificação Técnica, seção 3 —
    "o backend é 100% stateless, o HubSpot é o armazenamento de estado") e
    fazia isso com só um logger.warning, fácil de não notar nos logs do
    container antes de ir pra produção de verdade. Agora exige reconhecimento
    explícito via MEMORY_STORAGE_ACK=true — sem isso, o servidor recusa subir.
    Isso não substitui corrigir a causa raiz (HUBSPOT_API_KEY inválida — ver
    scripts/hubspot_setup.py), só impede que o modo paliativo vá pra produção
    por descuido.
    """
    using_memory = os.environ.get("STORAGE_BACKEND", "hubspot").strip().lower() == "memory"

    if using_memory and os.environ.get("MEMORY_STORAGE_ACK", "").strip().lower() != "true":
        raise RuntimeError(
            "[CRIT-02] STORAGE_BACKEND=memory está ativo, mas MEMORY_STORAGE_ACK "
            "não foi definido como 'true'. Nesse modo, todo o estado das conversas "
            "em andamento é perdido a cada restart/redeploy e NADA é gravado no "
            "HubSpot — a equipe comercial não veria os leads no CRM. "
            "Se isso for intencional (ex.: ambiente de teste), defina "
            "MEMORY_STORAGE_ACK=true explicitamente. Para produção, corrija "
            "HUBSPOT_API_KEY e troque STORAGE_BACKEND para 'hubspot'."
        )

    required = [
        s for s in _REQUIRED_SECRETS
        if not (s == "HUBSPOT_API_KEY" and using_memory)
    ]
    missing: list[str] = []
    for key in required:
        val = os.environ.get(key, "")
        is_missing = not val
        is_placeholder = any(val.startswith(p) for p in _PLACEHOLDER_PREFIXES)
        if is_missing or is_placeholder:
            missing.append(key)
    if missing:
        raise RuntimeError(
            f"[HIGH-01] Secrets obrigatórios ausentes ou com valor placeholder: "
            f"{', '.join(missing)}. "
            f"Configure o .env com valores reais antes de subir em produção."
        )
    if using_memory:
        logger.warning(
            "STORAGE_BACKEND=memory (reconhecido via MEMORY_STORAGE_ACK) — estado do "
            "lead vive em memória. Dados zerados a cada restart. Troque para "
            "'hubspot' em produção assim que HUBSPOT_API_KEY for corrigida."
        )
    logger.info(
        "Secrets validados — todos os {n} secrets obrigatórios presentes".format(
            n=len(_REQUIRED_SECRETS)
        )
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Executado uma vez no startup e uma vez no shutdown.
    Valida secrets antes de aceitar qualquer tráfego."""
    _validate_secrets()
    yield
    # Cleanup no shutdown (nenhum por enquanto — app é stateless)


app = FastAPI(title="Agente SDR BANT DGS", lifespan=lifespan)


# ── Kill switch middleware (A2) ────────────────────────────────────────────────
# Verifica ALANA_ENABLED antes de cada requisição. Quando false:
#   - Retorna 200 {"status": "disabled"} para todos os webhooks.
#   - /healthz passa diretamente (Docker/k8s não deve reiniciar o contêiner).
#   - Registra a requisição descartada para auditoria.
@app.middleware("http")
async def kill_switch(request: Request, call_next: object):
    enabled = os.environ.get("ALANA_ENABLED", "true").strip().lower()
    if enabled != "true" and request.url.path != "/healthz":
        logger.warning(
            "Kill switch ativo: requisição descartada",
            extra={
                "context": {
                    "path": request.url.path,
                    "method": request.method,
                    "alana_enabled": enabled,
                }
            },
        )
        return Response(
            content='{"status":"disabled","detail":"Alana está desativada temporariamente."}',
            status_code=200,
            media_type="application/json",
        )
    return await call_next(request)


app.include_router(site_form.router)
app.include_router(whatsapp.router)
app.include_router(timer_callback.router)


@app.get("/healthz")
async def healthz():
    """Sempre retorna 200 — usado pelo orquestrador para liveness check.
    Retorna também o estado atual do kill switch para facilitar diagnóstico."""
    enabled = os.environ.get("ALANA_ENABLED", "true").strip().lower() == "true"
    return {"status": "ok", "alana_enabled": enabled}
