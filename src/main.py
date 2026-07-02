"""Ponto de entrada do backend do Agente SDR (Portal de Deploy DB1).

Roda 100% stateless — todo estado de negócio vive no HubSpot (Especificação
Técnica, seção 3). O Dockerfile na raiz do repositório sobe este app com
`uvicorn src.main:app --host 0.0.0.0 --port 8000`.
"""
from fastapi import FastAPI

from .routes import site_form, timer_callback, whatsapp

app = FastAPI(title="Agente SDR BANT DGS")

app.include_router(site_form.router)
app.include_router(whatsapp.router)
app.include_router(timer_callback.router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
