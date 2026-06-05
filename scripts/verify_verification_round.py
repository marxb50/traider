from __future__ import annotations

import argparse
import json
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from super_trader_quant.backend.app.config import settings
from scripts.goal_acceptance_report import RECEIPT_MAX_AGE_MINUTES
from scripts.receipt_utils import write_json_receipt


GOAL_ACCEPTANCE_RECEIPT_FILE = "goal_acceptance_last.json"
VERIFICATION_BUNDLE_RECEIPT_FILE = "verification_bundle_last.json"
VERIFICATION_BUNDLE_CHECK_RECEIPT_FILE = "verification_bundle_check_last.json"
DEFAULT_ROUND_RECEIPT_FILE = "verification_round_last.json"


def _load_json_receipt(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as exc:
        return None, str(exc)


def _parse_timestamp(payload: dict[str, Any] | None) -> datetime | None:
    if not payload:
        return None
    generated_at = payload.get("generated_at")
    if not isinstance(generated_at, str):
        return None
    try:
        parsed = datetime.fromisoformat(generated_at)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _freshness(payload: dict[str, Any] | None, *, max_age_minutes: int = RECEIPT_MAX_AGE_MINUTES) -> dict[str, Any]:
    if not payload:
        return {
            "ok": False,
            "timestamp": None,
            "age_minutes": None,
            "max_age_minutes": max_age_minutes,
            "reason": "missing_receipt",
        }
    timestamp = _parse_timestamp(payload)
    if timestamp is None:
        return {
            "ok": False,
            "timestamp": None,
            "age_minutes": None,
            "max_age_minutes": max_age_minutes,
            "reason": "missing_timestamp",
        }
    age_minutes = (datetime.now(timezone.utc) - timestamp).total_seconds() / 60
    return {
        "ok": age_minutes <= max_age_minutes,
        "timestamp": timestamp.isoformat(),
        "age_minutes": age_minutes,
        "max_age_minutes": max_age_minutes,
        "reason": "fresh" if age_minutes <= max_age_minutes else "stale_receipt",
    }


def _resolve_run_id(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    return payload.get("run_id") or payload.get("expected_run_id")


def verify_verification_round(
    *,
    expected_run_id: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = Path(log_dir).resolve() if log_dir else settings.resolved_log_dir
    paths = {
        "goal_acceptance": resolved_log_dir / GOAL_ACCEPTANCE_RECEIPT_FILE,
        "bundle": resolved_log_dir / VERIFICATION_BUNDLE_RECEIPT_FILE,
        "bundle_check": resolved_log_dir / VERIFICATION_BUNDLE_CHECK_RECEIPT_FILE,
    }
    issues: list[str] = []
    payloads: dict[str, dict[str, Any] | None] = {}
    checks: dict[str, bool] = {}
    evidence: dict[str, Any] = {}

    for key, path in paths.items():
        checks[f"{key}_exists"] = path.exists()
        if not path.exists():
            payloads[key] = None
            evidence[key] = {"path": str(path), "error": "missing_receipt"}
            issues.append(f"{key}: missing_receipt")
            checks[f"{key}_valid_json"] = False
            continue
        payload, error = _load_json_receipt(path)
        payloads[key] = payload
        evidence[key] = {"path": str(path), "payload": payload, "error": error}
        checks[f"{key}_valid_json"] = error is None
        if error:
            issues.append(f"{key}: invalid_json")

    goal_acceptance = payloads.get("goal_acceptance")
    bundle = payloads.get("bundle")
    bundle_check = payloads.get("bundle_check")

    goal_freshness = _freshness(goal_acceptance)
    bundle_freshness = _freshness(bundle)
    bundle_check_freshness = _freshness(bundle_check)
    evidence["freshness"] = {
        "goal_acceptance": goal_freshness,
        "bundle": bundle_freshness,
        "bundle_check": bundle_check_freshness,
    }
    checks["goal_acceptance_fresh"] = goal_freshness["ok"]
    checks["bundle_fresh"] = bundle_freshness["ok"]
    checks["bundle_check_fresh"] = bundle_check_freshness["ok"]
    for label, freshness in evidence["freshness"].items():
        if not freshness["ok"]:
            issues.append(f"{label}: {freshness['reason']}")

    checks["goal_acceptance_complete"] = bool(goal_acceptance and goal_acceptance.get("complete"))
    checks["bundle_ok"] = bool(bundle and bundle.get("ok"))
    checks["bundle_check_ok"] = bool(bundle_check and bundle_check.get("ok"))
    if not checks["goal_acceptance_complete"]:
        issues.append("goal_acceptance: incomplete")
    if not checks["bundle_ok"]:
        issues.append("bundle: not_ok")
    if not checks["bundle_check_ok"]:
        issues.append("bundle_check: not_ok")

    resolved_run_ids = {
        "goal_acceptance": _resolve_run_id(goal_acceptance),
        "bundle": _resolve_run_id(bundle),
        "bundle_check": _resolve_run_id(bundle_check),
    }
    evidence["run_ids"] = resolved_run_ids
    non_empty_run_ids = {value for value in resolved_run_ids.values() if value}
    checks["run_id_coherent"] = len(non_empty_run_ids) <= 1
    if not checks["run_id_coherent"]:
        issues.append("run_id: mismatch_between_receipts")
    if expected_run_id is not None:
        checks["expected_run_id_match"] = non_empty_run_ids == {expected_run_id}
        if not checks["expected_run_id_match"]:
            issues.append("run_id: expected_mismatch")
    else:
        checks["expected_run_id_match"] = True

    goal_identity = {
        "hostname": goal_acceptance.get("hostname") if goal_acceptance else None,
        "app_env": goal_acceptance.get("app_env") if goal_acceptance else None,
    }
    bundle_identity = {
        "hostname": bundle.get("hostname") if bundle else None,
        "app_env": bundle.get("app_env") if bundle else None,
    }
    bundle_check_identity = {
        "hostname": bundle_check.get("hostname") if bundle_check else None,
        "app_env": bundle_check.get("app_env") if bundle_check else None,
    }
    evidence["identities"] = {
        "goal_acceptance": goal_identity,
        "bundle": bundle_identity,
        "bundle_check": bundle_check_identity,
    }
    hostnames = {
        identity["hostname"]
        for identity in evidence["identities"].values()
        if identity["hostname"]
    }
    app_envs = {
        identity["app_env"]
        for identity in evidence["identities"].values()
        if identity["app_env"]
    }
    checks["identity_host_coherent"] = len(hostnames) <= 1
    checks["identity_app_env_coherent"] = len(app_envs) <= 1
    if not checks["identity_host_coherent"]:
        issues.append("identity: hostname_mismatch")
    if not checks["identity_app_env_coherent"]:
        issues.append("identity: app_env_mismatch")

    bundle_checks = bundle_check.get("checks") if bundle_check else {}
    checks["bundle_check_live_files_verified"] = bool(
        isinstance(bundle_checks, dict)
        and bundle_checks.get("live_files_match_summary_hash")
        and bundle_check.get("check_live_files") is True
    )
    if not checks["bundle_check_live_files_verified"]:
        issues.append("bundle_check: live_files_not_verified")

    report = {
        "ok": all(checks.values()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": next(iter(non_empty_run_ids), expected_run_id),
        "expected_run_id": expected_run_id,
        "hostname": socket.gethostname(),
        "app_env": settings.app_env,
        "log_dir": str(resolved_log_dir),
        "checks": checks,
        "evidence": evidence,
        "issues": issues,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Verifica o fechamento completo de uma rodada: aceite operacional + bundle + bundle check.")
    parser.add_argument("--expected-run-id")
    parser.add_argument("--log-dir")
    parser.add_argument("--output", help="Salva o relatório JSON completo.")
    args = parser.parse_args()

    report = verify_verification_round(
        expected_run_id=args.expected_run_id,
        log_dir=args.log_dir,
    )
    output_path = Path(args.output) if args.output else settings.resolved_log_dir / DEFAULT_ROUND_RECEIPT_FILE
    write_json_receipt(output_path, report)

    print(f"ok: {report['ok']}")
    print(f"run_id: {report['run_id']}")
    print(f"receipt: {output_path}")
    for issue in report["issues"]:
        print(f"- {issue}")
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
