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
    com valor placeholder. Chamado no lifespan antes de aceitar tráfego."""
    missing: list[str] = []
    for key in _REQUIRED_SECRETS:
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
