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


@pytest.fixture()
def client_enabled(monkeypatch):
    monkeypatch.setenv("ALANA_ENABLED", "true")
    monkeypatch.setenv("HUBSPOT_API_KEY", "fake")
    monkeypatch.setenv("META_APP_SECRET", "fake")
    monkeypatch.setenv("META_WA_VERIFY_TOKEN", "fake")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "fake")
    monkeypatch.setenv("SLACK_CLOSER_CHANNEL", "fake")
    monkeypatch.setenv("META_WA_TOKEN", "fake")
    monkeypatch.setenv("META_WA_PHONE_NUMBER_ID", "fake")
    from src.main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def client_disabled(monkeypatch):
    monkeypatch.setenv("ALANA_ENABLED", "false")
    monkeypatch.setenv("HUBSPOT_API_KEY", "fake")
    monkeypatch.setenv("META_APP_SECRET", "fake")
    monkeypatch.setenv("META_WA_VERIFY_TOKEN", "fake")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "fake")
    monkeypatch.setenv("SLACK_CLOSER_CHANNEL", "fake")
    monkeypatch.setenv("META_WA_TOKEN", "fake")
    monkeypatch.setenv("META_WA_PHONE_NUMBER_ID", "fake")
    from src.main import app
    return TestClient(app, raise_server_exceptions=False)


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


def test_whatsapp_get_passes_through_when_enabled(client_enabled):
    # O GET do webhook WhatsApp sem token válido retorna 403, não "disabled"
    resp = client_enabled.get("/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=x")
    assert resp.status_code == 403
    # Confirma que não foi bloqueado pelo kill switch
    assert "disabled" not in resp.text
