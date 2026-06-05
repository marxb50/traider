from __future__ import annotations

import argparse
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from super_trader_quant.backend.app.config import settings
from scripts.receipt_utils import write_json_receipt


DEFAULT_RECEIPT_FILE = "ops_http_protection_last.json"


def _normalize_base_url(base_url: str | None) -> str:
    if base_url:
        return base_url.rstrip("/")
    return f"http://127.0.0.1:{settings.api_port}"


def _response_payload(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text[:500]


def _request_check(
    *,
    method: str,
    url: str,
    expected_status: int,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    try:
        response = requests.request(method, url, headers=headers, timeout=timeout_seconds)
    except requests.RequestException as exc:
        return {
            "ok": False,
            "status_code": None,
            "expected_status": expected_status,
            "payload": None,
            "error": str(exc),
        }
    return {
        "ok": response.status_code == expected_status,
        "status_code": response.status_code,
        "expected_status": expected_status,
        "payload": _response_payload(response),
        "error": None,
    }


def build_ops_http_protection_report(
    *,
    base_url: str | None = None,
    timeout_seconds: float = 15.0,
    run_id: str | None = None,
) -> dict[str, Any]:
    resolved_base_url = _normalize_base_url(base_url)
    token = settings.ops_admin_token.strip()
    auth_check_url = f"{resolved_base_url}/ops/auth-check"
    unauthorized = _request_check(
        method="POST",
        url=auth_check_url,
        expected_status=401,
        timeout_seconds=timeout_seconds,
    )
    header_auth = (
        _request_check(
            method="POST",
            url=auth_check_url,
            expected_status=200,
            headers={"X-Ops-Admin-Token": token},
            timeout_seconds=timeout_seconds,
        )
        if token
        else {
            "ok": False,
            "status_code": None,
            "expected_status": 200,
            "payload": None,
            "error": "OPS_ADMIN_TOKEN não configurado",
        }
    )
    bearer_auth = (
        _request_check(
            method="POST",
            url=auth_check_url,
            expected_status=200,
            headers={"Authorization": f"Bearer {token}"},
            timeout_seconds=timeout_seconds,
        )
        if token
        else {
            "ok": False,
            "status_code": None,
            "expected_status": 200,
            "payload": None,
            "error": "OPS_ADMIN_TOKEN não configurado",
        }
    )

    payload_ok = (
        header_auth["payload"] == {"ok": True, "message": "ops_admin_access_granted"}
        and bearer_auth["payload"] == {"ok": True, "message": "ops_admin_access_granted"}
    )
    report = {
        "ok": bool(token) and unauthorized["ok"] and header_auth["ok"] and bearer_auth["ok"] and payload_ok,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "hostname": socket.gethostname(),
        "app_env": settings.app_env,
        "base_url": resolved_base_url,
        "ops_admin_token_present": bool(token),
        "checks": {
            "unauthorized_request_rejected": unauthorized,
            "header_token_request_accepted": header_auth,
            "bearer_token_request_accepted": bearer_auth,
            "authorized_payload_ok": payload_ok,
        },
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Verifica se os endpoints /ops mutáveis estão protegidos por token.")
    parser.add_argument("--base-url", help="Base URL da API. Padrão: http://127.0.0.1:${API_PORT}.")
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--run-id", help="Identificador opcional da rodada de verificação.")
    parser.add_argument("--output", help="Salva o JSON completo em um arquivo.")
    args = parser.parse_args()

    report = build_ops_http_protection_report(
        base_url=args.base_url,
        timeout_seconds=args.timeout_seconds,
        run_id=args.run_id,
    )

    output_path = Path(args.output) if args.output else settings.resolved_log_dir / DEFAULT_RECEIPT_FILE
    write_json_receipt(output_path, report)

    print(f"ok: {report['ok']}")
    print(f"base_url: {report['base_url']}")
    print(f"ops_admin_token_present: {report['ops_admin_token_present']}")
    for name, check in report["checks"].items():
        print(f"- {name}: {check}")
    print(f"receipt: {output_path}")
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
