from scripts import verify_ops_http_protection


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def test_verify_ops_http_protection_report_passes_with_expected_http_responses(monkeypatch):
    monkeypatch.setattr(verify_ops_http_protection.settings, "ops_admin_token", "ops-secret")

    def fake_request(method, url, headers=None, timeout=15.0):
        assert method == "POST"
        assert url.endswith("/ops/auth-check")
        if not headers:
            return _FakeResponse(401, {"detail": "Token administrativo ausente ou inválido para endpoint operacional."})
        if headers.get("X-Ops-Admin-Token") == "ops-secret":
            return _FakeResponse(200, {"ok": True, "message": "ops_admin_access_granted"})
        if headers.get("Authorization") == "Bearer ops-secret":
            return _FakeResponse(200, {"ok": True, "message": "ops_admin_access_granted"})
        return _FakeResponse(401, {"detail": "denied"})

    monkeypatch.setattr(verify_ops_http_protection.requests, "request", fake_request)

    report = verify_ops_http_protection.build_ops_http_protection_report(base_url="http://127.0.0.1:8010", run_id="run-1")

    assert report["ok"] is True
    assert report["run_id"] == "run-1"
    assert "hostname" in report
    assert "app_env" in report
    assert report["checks"]["unauthorized_request_rejected"]["status_code"] == 401
    assert report["checks"]["header_token_request_accepted"]["status_code"] == 200
    assert report["checks"]["bearer_token_request_accepted"]["status_code"] == 200
    assert report["checks"]["authorized_payload_ok"] is True


def test_verify_ops_http_protection_report_fails_when_token_missing(monkeypatch):
    monkeypatch.setattr(verify_ops_http_protection.settings, "ops_admin_token", "")

    def fake_request(method, url, headers=None, timeout=15.0):
        return _FakeResponse(503, {"detail": "OPS_ADMIN_TOKEN é obrigatório"})

    monkeypatch.setattr(verify_ops_http_protection.requests, "request", fake_request)

    report = verify_ops_http_protection.build_ops_http_protection_report(base_url="http://127.0.0.1:8010", run_id="run-1")

    assert report["ok"] is False
    assert report["run_id"] == "run-1"
    assert "hostname" in report
    assert "app_env" in report
    assert report["ops_admin_token_present"] is False
    assert report["checks"]["header_token_request_accepted"]["error"] == "OPS_ADMIN_TOKEN não configurado"
