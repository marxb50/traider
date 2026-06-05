from __future__ import annotations

import argparse
import json
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from super_trader_quant.backend.app.config import settings
from scripts.receipt_utils import hash_file_sha256, write_json_receipt


DEFAULT_RECEIPT_FILE = "verification_manifest_last.json"
DEFAULT_RECEIPT_FILENAMES = [
    "production_preflight_last.json",
    "filesystem_isolation_last.json",
    "systemd_runtime_last.json",
    "process_runtime_last.json",
    "notification_drain_last.json",
    "ops_http_protection_last.json",
    "telegram_canary_last.json",
]


def _load_receipt(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as exc:
        return None, str(exc)


def build_verification_manifest(
    *,
    run_id: str | None,
    log_dir: str | Path | None = None,
    receipt_filenames: list[str] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = Path(log_dir).resolve() if log_dir else settings.resolved_log_dir
    filenames = receipt_filenames or list(DEFAULT_RECEIPT_FILENAMES)
    receipts: dict[str, Any] = {}
    issues: list[str] = []

    for filename in filenames:
        path = resolved_log_dir / filename
        entry: dict[str, Any] = {
            "path": str(path),
            "exists": path.exists(),
        }
        if not path.exists():
            entry["ok"] = False
            entry["reason"] = "missing_receipt"
            receipts[filename] = entry
            issues.append(f"{filename}: missing_receipt")
            continue

        entry["sha256"] = hash_file_sha256(path)
        entry["mtime"] = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        receipt_json, error = _load_receipt(path)
        if error:
            entry["ok"] = False
            entry["reason"] = "invalid_json"
            entry["json_error"] = error
            receipts[filename] = entry
            issues.append(f"{filename}: invalid_json")
            continue

        entry["generated_at"] = receipt_json.get("generated_at")
        entry["run_id"] = receipt_json.get("run_id")
        entry["hostname"] = receipt_json.get("hostname")
        entry["app_env"] = receipt_json.get("app_env")
        entry["receipt_ok"] = receipt_json.get("ok")
        run_id_ok = (not run_id) or entry["run_id"] == run_id
        entry["ok"] = bool(receipt_json.get("ok")) and run_id_ok
        entry["reason"] = "ok" if entry["ok"] else ("run_id_mismatch" if not run_id_ok else "receipt_not_ok")
        receipts[filename] = entry
        if not entry["ok"]:
            issues.append(f"{filename}: {entry['reason']}")

    return {
        "ok": not issues,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "hostname": socket.gethostname(),
        "app_env": settings.app_env,
        "log_dir": str(resolved_log_dir),
        "receipt_filenames": filenames,
        "receipts": receipts,
        "issues": issues,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera um manifest com hashes dos recibos obrigatórios de uma rodada de verificação.")
    parser.add_argument("--run-id", help="Identificador esperado da rodada de verificação.")
    parser.add_argument("--log-dir")
    parser.add_argument("--receipt", action="append", dest="receipts", help="Nome de recibo adicional/específico.")
    parser.add_argument("--output", help="Salva o JSON completo em um arquivo.")
    args = parser.parse_args()

    report = build_verification_manifest(
        run_id=args.run_id,
        log_dir=args.log_dir,
        receipt_filenames=args.receipts,
    )
    output_path = Path(args.output) if args.output else settings.resolved_log_dir / DEFAULT_RECEIPT_FILE
    write_json_receipt(output_path, report)

    print(f"ok: {report['ok']}")
    print(f"run_id: {report['run_id']}")
    for filename, entry in report["receipts"].items():
        print(f"- {filename}: {entry['ok']} ({entry.get('reason')})")
    print(f"receipt: {output_path}")
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
