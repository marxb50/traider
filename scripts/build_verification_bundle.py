from __future__ import annotations

import argparse
import json
import os
import socket
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from super_trader_quant.backend.app.config import settings
from scripts.receipt_utils import hash_file_sha256, write_json_receipt


DEFAULT_BUNDLE_ZIP_FILE = "verification_bundle_last.zip"
DEFAULT_BUNDLE_RECEIPT_FILE = "verification_bundle_last.json"
DEFAULT_INCLUDED_FILENAMES = [
    "production_preflight_last.json",
    "filesystem_isolation_last.json",
    "systemd_runtime_last.json",
    "process_runtime_last.json",
    "notification_drain_last.json",
    "ops_http_protection_last.json",
    "telegram_canary_last.json",
    "verification_manifest_last.json",
    "goal_acceptance_last.json",
]


def _load_json_payload(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as exc:
        return None, str(exc)


def _infer_run_id(filename: str, payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    if filename == "goal_acceptance_last.json":
        return payload.get("expected_run_id") or payload.get("run_id")
    return payload.get("run_id") or payload.get("expected_run_id")


def _infer_content_status(filename: str, payload: dict[str, Any] | None) -> tuple[bool, str]:
    if not payload:
        return False, "missing_payload"
    if filename == "goal_acceptance_last.json":
        return bool(payload.get("complete")), "acceptance_complete" if payload.get("complete") else "acceptance_incomplete"
    if "ok" in payload:
        return bool(payload.get("ok")), "ok" if payload.get("ok") else "content_not_ok"
    return True, "status_not_declared"


def _build_summary_markdown(report: dict[str, Any]) -> str:
    acceptance = report.get("acceptance_summary") or {}
    lines = [
        "# Verification bundle",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Run ID: `{report.get('run_id')}`",
        f"- Hostname: `{report.get('hostname')}`",
        f"- App env: `{report.get('app_env')}`",
        f"- Source log dir: `{report.get('log_dir')}`",
        f"- Bundle status: `{'ok' if report.get('ok') else 'blocked'}`",
        "",
        "## Goal acceptance snapshot",
        "",
        f"- Complete: `{acceptance.get('complete')}`",
        f"- Ready for local handoff: `{acceptance.get('ready_for_local_handoff')}`",
        f"- Summary: `{acceptance.get('summary')}`",
        "",
        "## Included files",
        "",
        "| File | Included | Content status | SHA-256 | Notes |",
        "|---|---:|---|---|---|",
    ]
    for filename, entry in report["files"].items():
        notes = []
        if entry.get("reason"):
            notes.append(entry["reason"])
        if entry.get("json_error"):
            notes.append("invalid_json")
        if entry.get("detected_run_id"):
            notes.append(f"run_id={entry['detected_run_id']}")
        lines.append(
            f"| `{filename}` | `{'yes' if entry.get('included_in_zip') else 'no'}` | "
            f"`{entry.get('content_reason')}` | `{entry.get('sha256')}` | {'; '.join(notes) or '-'} |"
        )
    if report["issues"]:
        lines.extend(["", "## Issues", ""])
        lines.extend([f"- {issue}" for issue in report["issues"]])
    else:
        lines.extend(["", "## Issues", "", "- none"])
    return "\n".join(lines) + "\n"


def _write_zip_atomically(
    *,
    output_path: Path,
    summary_json: dict[str, Any],
    summary_markdown: str,
    included_files: dict[str, Path],
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("summary/bundle_summary.json", json.dumps(summary_json, ensure_ascii=False, indent=2) + "\n")
            archive.writestr("summary/bundle_summary.md", summary_markdown)
            for filename, source_path in included_files.items():
                archive.write(source_path, arcname=f"receipts/{filename}")
        os.replace(temp_path, output_path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
    return output_path


def build_verification_bundle(
    *,
    run_id: str | None,
    log_dir: str | Path | None = None,
    included_filenames: list[str] | None = None,
    output_zip: str | Path | None = None,
    output_receipt: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = Path(log_dir).resolve() if log_dir else settings.resolved_log_dir
    filenames = included_filenames or list(DEFAULT_INCLUDED_FILENAMES)
    output_zip_path = Path(output_zip).resolve() if output_zip else resolved_log_dir / DEFAULT_BUNDLE_ZIP_FILE
    output_receipt_path = Path(output_receipt).resolve() if output_receipt else resolved_log_dir / DEFAULT_BUNDLE_RECEIPT_FILE

    files: dict[str, Any] = {}
    issues: list[str] = []
    included_sources: dict[str, Path] = {}
    acceptance_summary: dict[str, Any] | None = None

    for filename in filenames:
        path = resolved_log_dir / filename
        entry: dict[str, Any] = {
            "source_path": str(path),
            "archive_path": f"receipts/{filename}",
            "exists": path.exists(),
            "included_in_zip": path.exists(),
        }
        if not path.exists():
            entry["ok"] = False
            entry["reason"] = "missing_file"
            entry["content_reason"] = "missing_file"
            files[filename] = entry
            issues.append(f"{filename}: missing_file")
            continue

        entry["size_bytes"] = path.stat().st_size
        entry["mtime"] = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        entry["sha256"] = hash_file_sha256(path)
        included_sources[filename] = path

        payload, json_error = _load_json_payload(path)
        if json_error:
            entry["ok"] = False
            entry["reason"] = "invalid_json"
            entry["content_reason"] = "invalid_json"
            entry["json_error"] = json_error
            files[filename] = entry
            issues.append(f"{filename}: invalid_json")
            continue

        detected_run_id = _infer_run_id(filename, payload)
        content_ok, content_reason = _infer_content_status(filename, payload)
        entry["detected_run_id"] = detected_run_id
        entry["detected_hostname"] = payload.get("hostname")
        entry["detected_app_env"] = payload.get("app_env")
        entry["generated_at"] = payload.get("generated_at")
        entry["content_ok"] = content_ok
        entry["content_reason"] = content_reason

        run_id_ok = True
        reason = content_reason
        if run_id:
            if not detected_run_id:
                run_id_ok = False
                reason = "missing_run_id"
            elif detected_run_id != run_id:
                run_id_ok = False
                reason = "run_id_mismatch"

        entry["run_id_ok"] = run_id_ok
        entry["ok"] = content_ok and run_id_ok
        entry["reason"] = "ok" if entry["ok"] else reason
        files[filename] = entry
        if not entry["ok"]:
            issues.append(f"{filename}: {entry['reason']}")

        if filename == "goal_acceptance_last.json":
            acceptance_summary = {
                "complete": payload.get("complete"),
                "ready_for_local_handoff": payload.get("ready_for_local_handoff"),
                "summary": payload.get("summary"),
                "next_required_actions": payload.get("next_required_actions"),
            }

    base_report: dict[str, Any] = {
        "ok": not issues,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "hostname": socket.gethostname(),
        "app_env": settings.app_env,
        "log_dir": str(resolved_log_dir),
        "included_filenames": filenames,
        "files": files,
        "acceptance_summary": acceptance_summary,
        "issues": issues,
    }
    summary_markdown = _build_summary_markdown(base_report)
    _write_zip_atomically(
        output_path=output_zip_path,
        summary_json=base_report,
        summary_markdown=summary_markdown,
        included_files=included_sources,
    )

    report = {
        **base_report,
        "output_zip": str(output_zip_path),
        "output_zip_sha256": hash_file_sha256(output_zip_path),
        "output_zip_size_bytes": output_zip_path.stat().st_size,
        "output_receipt": str(output_receipt_path),
    }
    write_json_receipt(output_receipt_path, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera um bundle final com os recibos e o relatório de aceite da rodada de verificação.")
    parser.add_argument("--run-id", help="Identificador esperado da rodada de verificação.")
    parser.add_argument("--log-dir")
    parser.add_argument("--include", action="append", dest="included_files", help="Nome de recibo/arquivo para incluir no bundle.")
    parser.add_argument("--output-zip", help="Caminho do ZIP final.")
    parser.add_argument("--output-receipt", help="Caminho do recibo JSON do bundle.")
    args = parser.parse_args()

    report = build_verification_bundle(
        run_id=args.run_id,
        log_dir=args.log_dir,
        included_filenames=args.included_files,
        output_zip=args.output_zip,
        output_receipt=args.output_receipt,
    )
    print(f"ok: {report['ok']}")
    print(f"run_id: {report['run_id']}")
    print(f"zip: {report['output_zip']}")
    print(f"zip_sha256: {report['output_zip_sha256']}")
    print(f"receipt: {report['output_receipt']}")
    for issue in report["issues"]:
        print(f"- {issue}")
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
