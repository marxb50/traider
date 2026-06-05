from __future__ import annotations

import argparse
import hashlib
import json
import socket
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from super_trader_quant.backend.app.config import settings
from scripts.build_verification_bundle import DEFAULT_BUNDLE_RECEIPT_FILE, DEFAULT_BUNDLE_ZIP_FILE
from scripts.receipt_utils import hash_file_sha256, write_json_receipt


DEFAULT_BUNDLE_CHECK_RECEIPT_FILE = "verification_bundle_check_last.json"
SUMMARY_JSON_PATH = "summary/bundle_summary.json"
SUMMARY_MARKDOWN_PATH = "summary/bundle_summary.md"


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load_json_file(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as exc:
        return None, str(exc)


def _load_json_from_zip(archive: zipfile.ZipFile, name: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        raw = archive.read(name)
    except KeyError:
        return None, "missing_entry"
    try:
        return json.loads(raw.decode("utf-8")), None
    except json.JSONDecodeError as exc:
        return None, str(exc)


def verify_verification_bundle(
    *,
    expected_run_id: str | None = None,
    log_dir: str | Path | None = None,
    bundle_zip: str | Path | None = None,
    bundle_receipt: str | Path | None = None,
    check_live_files: bool = False,
) -> dict[str, Any]:
    resolved_log_dir = Path(log_dir).resolve() if log_dir else settings.resolved_log_dir
    bundle_zip_path = Path(bundle_zip).resolve() if bundle_zip else resolved_log_dir / DEFAULT_BUNDLE_ZIP_FILE
    bundle_receipt_path = Path(bundle_receipt).resolve() if bundle_receipt else resolved_log_dir / DEFAULT_BUNDLE_RECEIPT_FILE

    issues: list[str] = []
    file_checks: dict[str, Any] = {}
    checks = {
        "bundle_zip_exists": bundle_zip_path.exists(),
        "bundle_receipt_exists": bundle_receipt_path.exists(),
        "bundle_receipt_valid_json": False,
        "bundle_zip_sha256_matches_receipt": False,
        "bundle_summary_json_present": False,
        "bundle_summary_markdown_present": False,
        "bundle_summary_matches_receipt": False,
        "bundle_run_id_matches_expected": expected_run_id is None,
        "archived_files_match_summary_hash": False,
        "live_files_match_summary_hash": (not check_live_files),
    }

    receipt_payload: dict[str, Any] | None = None
    if bundle_receipt_path.exists():
        receipt_payload, receipt_error = _load_json_file(bundle_receipt_path)
        if receipt_error:
            issues.append(f"bundle_receipt: invalid_json ({receipt_error})")
        else:
            checks["bundle_receipt_valid_json"] = True
    else:
        receipt_error = None
        issues.append("bundle_receipt: missing_file")

    summary_payload: dict[str, Any] | None = None
    if bundle_zip_path.exists():
        actual_zip_hash = hash_file_sha256(bundle_zip_path)
    else:
        actual_zip_hash = None
        issues.append("bundle_zip: missing_file")

    if receipt_payload and actual_zip_hash:
        checks["bundle_zip_sha256_matches_receipt"] = actual_zip_hash == receipt_payload.get("output_zip_sha256")
        if not checks["bundle_zip_sha256_matches_receipt"]:
            issues.append("bundle_zip: sha256_mismatch")

    archived_file_mismatch = False
    live_file_mismatch = False
    bundle_run_id = receipt_payload.get("run_id") if receipt_payload else None

    if bundle_zip_path.exists():
        with zipfile.ZipFile(bundle_zip_path, "r") as archive:
            archive_names = set(archive.namelist())
            checks["bundle_summary_json_present"] = SUMMARY_JSON_PATH in archive_names
            checks["bundle_summary_markdown_present"] = SUMMARY_MARKDOWN_PATH in archive_names
            if not checks["bundle_summary_json_present"]:
                issues.append("bundle_zip: missing_summary_json")
            if not checks["bundle_summary_markdown_present"]:
                issues.append("bundle_zip: missing_summary_markdown")

            if checks["bundle_summary_json_present"]:
                summary_payload, summary_error = _load_json_from_zip(archive, SUMMARY_JSON_PATH)
                if summary_error:
                    issues.append(f"bundle_zip: invalid_summary_json ({summary_error})")
                else:
                    if bundle_run_id is None:
                        bundle_run_id = summary_payload.get("run_id")
                    if expected_run_id is not None:
                        checks["bundle_run_id_matches_expected"] = summary_payload.get("run_id") == expected_run_id
                        if not checks["bundle_run_id_matches_expected"]:
                            issues.append("bundle_zip: run_id_mismatch")

                    if receipt_payload:
                        comparable_keys = [
                            "ok",
                            "generated_at",
                            "run_id",
                            "hostname",
                            "app_env",
                            "log_dir",
                            "included_filenames",
                            "files",
                            "acceptance_summary",
                            "issues",
                        ]
                        expected_summary = {key: receipt_payload.get(key) for key in comparable_keys}
                        checks["bundle_summary_matches_receipt"] = summary_payload == expected_summary
                        if not checks["bundle_summary_matches_receipt"]:
                            issues.append("bundle_zip: summary_receipt_mismatch")

                    summary_files = summary_payload.get("files", {})
                    if not isinstance(summary_files, dict):
                        archived_file_mismatch = True
                        issues.append("bundle_zip: invalid_files_section")
                    else:
                        for filename, entry in summary_files.items():
                            archive_path = entry.get("archive_path") or f"receipts/{filename}"
                            file_report = {
                                "archive_path": archive_path,
                                "present_in_zip": archive_path in archive_names,
                                "expected_sha256": entry.get("sha256"),
                                "summary_ok": entry.get("ok"),
                            }
                            if not file_report["present_in_zip"]:
                                file_report["ok"] = False
                                file_report["reason"] = "missing_archive_entry"
                                archived_file_mismatch = True
                                issues.append(f"{filename}: missing_archive_entry")
                                file_checks[filename] = file_report
                                continue

                            archived_bytes = archive.read(archive_path)
                            archived_sha256 = _hash_bytes(archived_bytes)
                            file_report["archived_sha256"] = archived_sha256
                            hash_ok = archived_sha256 == entry.get("sha256")
                            file_report["archive_hash_ok"] = hash_ok
                            if not hash_ok:
                                file_report["ok"] = False
                                file_report["reason"] = "archive_hash_mismatch"
                                archived_file_mismatch = True
                                issues.append(f"{filename}: archive_hash_mismatch")
                            elif check_live_files:
                                live_path = resolved_log_dir / filename
                                file_report["live_path"] = str(live_path)
                                file_report["live_exists"] = live_path.exists()
                                if not live_path.exists():
                                    file_report["ok"] = False
                                    file_report["reason"] = "missing_live_file"
                                    live_file_mismatch = True
                                    issues.append(f"{filename}: missing_live_file")
                                else:
                                    live_sha256 = hash_file_sha256(live_path)
                                    file_report["live_sha256"] = live_sha256
                                    live_ok = live_sha256 == entry.get("sha256")
                                    file_report["live_hash_ok"] = live_ok
                                    file_report["ok"] = live_ok
                                    file_report["reason"] = "ok" if live_ok else "live_hash_mismatch"
                                    if not live_ok:
                                        live_file_mismatch = True
                                        issues.append(f"{filename}: live_hash_mismatch")
                            else:
                                file_report["ok"] = True
                                file_report["reason"] = "ok"
                            file_checks[filename] = file_report

    if bundle_zip_path.exists() and summary_payload is not None and file_checks:
        checks["archived_files_match_summary_hash"] = not archived_file_mismatch
        checks["live_files_match_summary_hash"] = (not check_live_files) or (not live_file_mismatch)

    report = {
        "ok": all(checks.values()) and not issues,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "expected_run_id": expected_run_id,
        "run_id": bundle_run_id,
        "hostname": socket.gethostname(),
        "app_env": settings.app_env,
        "log_dir": str(resolved_log_dir),
        "bundle_zip": str(bundle_zip_path),
        "bundle_receipt": str(bundle_receipt_path),
        "bundle_zip_sha256": actual_zip_hash,
        "check_live_files": check_live_files,
        "checks": checks,
        "files": file_checks,
        "issues": issues,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Verifica a integridade do verification bundle e sua coerência com os recibos/live files.")
    parser.add_argument("--expected-run-id", help="Exige que o bundle pertença à rodada informada.")
    parser.add_argument("--log-dir")
    parser.add_argument("--bundle-zip")
    parser.add_argument("--bundle-receipt")
    parser.add_argument("--check-live-files", action="store_true", help="Também exige que os arquivos live atuais batam com os hashes embalados.")
    parser.add_argument("--output", help="Salva o relatório JSON completo.")
    args = parser.parse_args()

    report = verify_verification_bundle(
        expected_run_id=args.expected_run_id,
        log_dir=args.log_dir,
        bundle_zip=args.bundle_zip,
        bundle_receipt=args.bundle_receipt,
        check_live_files=args.check_live_files,
    )
    output_path = Path(args.output) if args.output else settings.resolved_log_dir / DEFAULT_BUNDLE_CHECK_RECEIPT_FILE
    write_json_receipt(output_path, report)

    print(f"ok: {report['ok']}")
    print(f"run_id: {report['run_id']}")
    print(f"bundle_zip: {report['bundle_zip']}")
    print(f"receipt: {output_path}")
    for issue in report["issues"]:
        print(f"- {issue}")
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
