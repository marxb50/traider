from __future__ import annotations

import argparse
import os
import re
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from super_trader_quant.backend.app.config import settings
from scripts.receipt_utils import write_json_receipt


DEFAULT_RECEIPT_FILE = "process_runtime_last.json"
APP_DIR = Path("/opt/super_trader_quant")
API_PORT = 8010
API_UNIT = "super-trader-quant-api.service"
SCHEDULER_UNIT = "super-trader-quant-scheduler.service"


def _run_command(*args: str) -> str:
    result = subprocess.run(
        list(args),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or f"comando falhou: {' '.join(args)}"
        raise RuntimeError(stderr)
    return result.stdout


def _systemctl_show(unit: str, properties: list[str]) -> dict[str, str]:
    output = _run_command("systemctl", "show", unit, *(f"--property={name}" for name in properties), "--no-pager")
    values: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def _process_owner(pid: int) -> str:
    import pwd

    proc_stat = os.stat(f"/proc/{pid}")
    return pwd.getpwuid(proc_stat.st_uid).pw_name


def _read_proc_link(pid: int, name: str) -> str:
    return os.readlink(f"/proc/{pid}/{name}")


def _read_proc_cmdline(pid: int) -> list[str]:
    raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    return [item for item in raw.decode("utf-8", errors="replace").split("\x00") if item]


def _parse_ss_line(line: str) -> dict[str, Any] | None:
    stripped = line.strip()
    if not stripped.startswith("LISTEN"):
        return None
    parts = re.split(r"\s+", stripped)
    if len(parts) < 5:
        return None
    local_address = parts[3]
    process_info = " ".join(parts[5:]) if len(parts) > 5 else ""
    return {
        "raw": stripped,
        "local_address": local_address,
        "process_info": process_info,
    }


def _ss_listeners_for_port(port: int) -> list[dict[str, Any]]:
    output = _run_command("ss", "-ltnp")
    listeners: list[dict[str, Any]] = []
    suffix = f":{port}"
    for line in output.splitlines():
        parsed = _parse_ss_line(line)
        if not parsed:
            continue
        if parsed["local_address"].endswith(suffix):
            listeners.append(parsed)
    return listeners


def _expected_command_fragments(script_module: str) -> list[str]:
    return [str(APP_DIR / ".venv/bin/python"), "-m", script_module]


def _check_process(unit: str, expected_script_module: str, expected_user: str) -> dict[str, Any]:
    show = _systemctl_show(unit, ["MainPID", "ActiveState", "SubState"])
    pid = int(show.get("MainPID", "0") or "0")
    if pid <= 0:
        return {
            "ok": False,
            "unit": unit,
            "show": show,
            "error": "MainPID ausente ou zero",
        }

    owner = _process_owner(pid)
    cwd = _read_proc_link(pid, "cwd")
    exe = _read_proc_link(pid, "exe")
    cmdline = _read_proc_cmdline(pid)
    expected_fragments = _expected_command_fragments(expected_script_module)
    cmdline_joined = " ".join(cmdline)
    command_ok = all(fragment in cmdline_joined for fragment in expected_fragments)
    cwd_ok = cwd == str(APP_DIR)
    owner_ok = owner == expected_user
    active_ok = show.get("ActiveState") == "active"
    substate_ok = show.get("SubState") == "running"
    return {
        "ok": owner_ok and cwd_ok and command_ok and active_ok and substate_ok,
        "unit": unit,
        "pid": pid,
        "show": show,
        "owner": owner,
        "cwd": cwd,
        "exe": exe,
        "cmdline": cmdline,
        "checks": {
            "owner_ok": owner_ok,
            "cwd_ok": cwd_ok,
            "command_ok": command_ok,
            "active_ok": active_ok,
            "substate_ok": substate_ok,
        },
    }


def build_process_runtime_report(
    *,
    app_user: str = "supertrader",
    app_dir: str | Path = APP_DIR,
    api_port: int = API_PORT,
    run_id: str | None = None,
) -> dict[str, Any]:
    global APP_DIR
    APP_DIR = Path(app_dir).resolve()

    api_process = _check_process(API_UNIT, "scripts.run_api", app_user)
    scheduler_process = _check_process(SCHEDULER_UNIT, "scripts.run_scheduler", app_user)
    listeners = _ss_listeners_for_port(api_port)
    allowed_addresses = {f"127.0.0.1:{api_port}", f"[::1]:{api_port}"}
    listener_checks = {
        "has_listener": bool(listeners),
        "all_loopback": bool(listeners) and all(listener["local_address"] in allowed_addresses for listener in listeners),
        "listener_mentions_api_pid": bool(listeners) and any(
            api_process.get("pid") and f"pid={api_process['pid']}" in listener["process_info"]
            for listener in listeners
        ),
        "no_wildcard_listener": all(
            listener["local_address"] not in {f"0.0.0.0:{api_port}", f"*:{api_port}", f"[::]:{api_port}"}
            for listener in listeners
        ),
    }

    issues: list[str] = []
    if not api_process["ok"]:
        failed = [name for name, passed in api_process.get("checks", {}).items() if not passed]
        issues.append(f"{API_UNIT}: falhou em {', '.join(failed) or api_process.get('error', 'erro desconhecido')}")
    if not scheduler_process["ok"]:
        failed = [name for name, passed in scheduler_process.get("checks", {}).items() if not passed]
        issues.append(f"{SCHEDULER_UNIT}: falhou em {', '.join(failed) or scheduler_process.get('error', 'erro desconhecido')}")
    if not listener_checks["has_listener"]:
        issues.append(f"api_port_{api_port}: nenhum listener encontrado")
    if listener_checks["has_listener"] and not listener_checks["all_loopback"]:
        issues.append(f"api_port_{api_port}: listener fora do loopback detectado")
    if listener_checks["has_listener"] and not listener_checks["listener_mentions_api_pid"]:
        issues.append(f"api_port_{api_port}: listener não corresponde ao MainPID da API")
    if not listener_checks["no_wildcard_listener"]:
        issues.append(f"api_port_{api_port}: listener wildcard detectado")

    return {
        "ok": not issues,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "hostname": socket.gethostname(),
        "app_env": settings.app_env,
        "app_user": app_user,
        "app_dir": str(APP_DIR),
        "api_port": api_port,
        "api_process": api_process,
        "scheduler_process": scheduler_process,
        "listeners": listeners,
        "listener_checks": listener_checks,
        "issues": issues,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verifica em runtime se API/scheduler estão isolados por processo e bind.")
    parser.add_argument("--app-user", default="supertrader")
    parser.add_argument("--app-dir", default=str(APP_DIR))
    parser.add_argument("--api-port", type=int, default=API_PORT)
    parser.add_argument("--run-id", help="Identificador opcional da rodada de verificação.")
    parser.add_argument("--output", help="Salva o JSON completo em um arquivo.")
    args = parser.parse_args()

    report = build_process_runtime_report(
        app_user=args.app_user,
        app_dir=args.app_dir,
        api_port=args.api_port,
        run_id=args.run_id,
    )
    output_path = Path(args.output) if args.output else settings.resolved_log_dir / DEFAULT_RECEIPT_FILE
    write_json_receipt(output_path, report)

    print(f"ok: {report['ok']}")
    print(f"api_process_ok: {report['api_process']['ok']}")
    print(f"scheduler_process_ok: {report['scheduler_process']['ok']}")
    print(f"listener_checks: {report['listener_checks']}")
    for issue in report["issues"]:
        print(f"- issue: {issue}")
    print(f"receipt: {output_path}")
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
