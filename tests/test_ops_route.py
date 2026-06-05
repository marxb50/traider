from fastapi.testclient import TestClient
from super_trader_quant.backend.app.main import app
from super_trader_quant.backend.app.models.asset import Asset
from super_trader_quant.backend.app.models.notification import Notification
from super_trader_quant.backend.app.models.signal import Signal
from super_trader_quant.backend.app.api import routes_ops
from super_trader_quant.backend.app.api import ops_auth
from super_trader_quant.backend.app.services import heartbeat_service


def test_ops_status_exposes_scheduler_heartbeat(monkeypatch, tmp_path):
    monkeypatch.setattr(heartbeat_service.settings, "log_dir", str(tmp_path))
    heartbeat_service.update_scheduler_heartbeat("startup_scan", {"startup_created": 2})

    client = TestClient(app)
    response = client.get("/ops/status")

    assert response.status_code == 200
    assert response.json()["scheduler_heartbeat"]["last_event"] == "startup_scan"
    assert response.json()["memory_consistency"]["is_consistent"] is True

    watchdog_response = client.get("/ops/watchdog")
    assert watchdog_response.status_code == 200
    assert "ok" in watchdog_response.json()
    assert "issues" in watchdog_response.json()


def test_ops_scan_now_endpoint_runs_operational_cycle(monkeypatch):
    monkeypatch.setattr(ops_auth.settings, "app_env", "local")
    monkeypatch.setattr(ops_auth.settings, "ops_admin_token", "")
    monkeypatch.setattr(
        routes_ops,
        "run_signal_cycle",
        lambda timeframe="D1", symbols=None: {
            "timeframe": timeframe,
            "symbols": symbols or [],
            "created_signals": 1,
            "resolved_signals": 0,
            "sent_notifications": 1,
            "simulation_only": True,
        },
    )
    client = TestClient(app)

    response = client.post("/ops/scan-now?timeframe=D1&symbol=AAPL")

    assert response.status_code == 200
    assert response.json()["created_signals"] == 1
    assert response.json()["symbols"] == ["AAPL"]


def test_ops_scan_now_requires_admin_token_when_configured(monkeypatch):
    monkeypatch.setattr(ops_auth.settings, "app_env", "production")
    monkeypatch.setattr(ops_auth.settings, "ops_admin_token", "very-secret-token")
    client = TestClient(app)

    response = client.post("/ops/scan-now?timeframe=D1")

    assert response.status_code == 401
    assert "inválido" in response.json()["detail"]


def test_ops_auth_check_requires_admin_token_when_configured(monkeypatch):
    monkeypatch.setattr(ops_auth.settings, "app_env", "production")
    monkeypatch.setattr(ops_auth.settings, "ops_admin_token", "very-secret-token")
    client = TestClient(app)

    response = client.post("/ops/auth-check")

    assert response.status_code == 401


def test_ops_auth_check_accepts_bearer_token(monkeypatch):
    monkeypatch.setattr(ops_auth.settings, "app_env", "production")
    monkeypatch.setattr(ops_auth.settings, "ops_admin_token", "very-secret-token")
    client = TestClient(app)

    response = client.post(
        "/ops/auth-check",
        headers={"Authorization": "Bearer very-secret-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "message": "ops_admin_access_granted"}


def test_ops_scan_now_accepts_admin_token_header(monkeypatch):
    monkeypatch.setattr(ops_auth.settings, "app_env", "production")
    monkeypatch.setattr(ops_auth.settings, "ops_admin_token", "very-secret-token")
    monkeypatch.setattr(
        routes_ops,
        "run_signal_cycle",
        lambda timeframe="D1", symbols=None: {
            "timeframe": timeframe,
            "symbols": symbols or [],
            "created_signals": 0,
            "resolved_signals": 0,
            "sent_notifications": 0,
            "simulation_only": True,
        },
    )
    client = TestClient(app)

    response = client.post(
        "/ops/scan-now?timeframe=D1",
        headers={"X-Ops-Admin-Token": "very-secret-token"},
    )

    assert response.status_code == 200
    assert response.json()["timeframe"] == "D1"


def test_ops_scan_now_blocks_mutation_in_production_without_configured_token(monkeypatch):
    monkeypatch.setattr(ops_auth.settings, "app_env", "production")
    monkeypatch.setattr(ops_auth.settings, "ops_admin_token", "")
    client = TestClient(app)

    response = client.post("/ops/scan-now?timeframe=D1")

    assert response.status_code == 503
    assert "OPS_ADMIN_TOKEN" in response.json()["detail"]
