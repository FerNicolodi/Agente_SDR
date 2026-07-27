"""Testes unitários para o kill switch da Alana (A2).

Cobre:
- ALANA_ENABLED=true → requisições processadas normalmente
- ALANA_ENABLED=false → webhooks retornam 200 {"status":"disabled"}
- ALANA_ENABLED ausente → padrão é true (sistema ativo)
- /healthz sempre acessível, independentemente do kill switch
- /healthz expõe estado correto de alana_enabled
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _set_required_secrets(monkeypatch):
    """Secrets exigidos por _validate_secrets() no lifespan (src/main.py) —
    manter em sincronia com _REQUIRED_SECRETS. Ver revisão de segurança
    2026-07-27: sem isso e sem `with TestClient(...)`, o lifespan nunca
    dispara e este arquivo não testa a validação de startup de verdade."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "valor-de-teste-nao-placeholder")
    monkeypatch.setenv("ZAPI_INSTANCE_ID", "valor-de-teste-nao-placeholder")
    monkeypatch.setenv("ZAPI_TOKEN", "valor-de-teste-nao-placeholder")
    monkeypatch.setenv("ZAPI_CLIENT_TOKEN", "valor-de-teste-nao-placeholder")
    monkeypatch.setenv("SITE_FORM_HMAC_SECRET", "valor-de-teste-nao-placeholder")
    monkeypatch.setenv("HUBSPOT_WORKFLOW_HMAC_SECRET", "valor-de-teste-nao-placeholder")
    monkeypatch.setenv("HUBSPOT_API_KEY", "valor-de-teste-nao-placeholder")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "valor-de-teste-nao-placeholder")
    monkeypatch.setenv("SLACK_CLOSER_CHANNEL", "fake-channel")
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("MEMORY_STORAGE_ACK", raising=False)


@pytest.fixture()
def client_enabled(monkeypatch):
    monkeypatch.setenv("ALANA_ENABLED", "true")
    _set_required_secrets(monkeypatch)
    from src.main import app
    # `with` dispara o lifespan de verdade (_validate_secrets) — sem isso,
    # o startup nunca é exercitado pelo teste (achado da revisão de segurança).
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture()
def client_disabled(monkeypatch):
    monkeypatch.setenv("ALANA_ENABLED", "false")
    _set_required_secrets(monkeypatch)
    from src.main import app
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


# ── /healthz sempre acessível ────────────────────────────────────────────────


def test_healthz_accessible_when_enabled(client_enabled):
    resp = client_enabled.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["alana_enabled"] is True


def test_healthz_accessible_when_disabled(client_disabled):
    resp = client_disabled.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["alana_enabled"] is False


# ── Kill switch bloqueia webhooks ─────────────────────────────────────────────


def test_whatsapp_webhook_blocked_when_disabled(client_disabled):
    resp = client_disabled.post("/webhook/whatsapp", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "disabled"


def test_site_form_webhook_blocked_when_disabled(client_disabled):
    resp = client_disabled.post("/webhook/site-form", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "disabled"


# ── Sistema ativo quando ALANA_ENABLED=true ──────────────────────────────────


def test_whatsapp_get_not_allowed(client_enabled):
    """Não há handshake GET no webhook Z-API (isso era coisa do Meta Cloud
    API, removido na migração — ver commit 744f840). O método correto
    retorna 405, roteado pelo FastAPI antes até de chegar no kill switch."""
    resp = client_enabled.get("/webhook/whatsapp")
    assert resp.status_code == 405


def test_whatsapp_post_passes_through_when_enabled(client_enabled):
    """Com o kill switch ligado, um POST sem autenticação Z-API válida
    chega até a lógica da rota (401), em vez de ser bloqueado antes com
    o "disabled" do kill switch — confirma que o middleware deixa passar."""
    resp = client_enabled.post("/webhook/whatsapp", json={})
    assert resp.status_code == 401
    assert "disabled" not in resp.text
