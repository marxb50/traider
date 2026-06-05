from __future__ import annotations

import argparse
import socket
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from super_trader_quant.backend.app.config import settings
from scripts.receipt_utils import write_json_receipt


DEFAULT_RECEIPT_FILE = "filesystem_isolation_last.json"
SYSTEMD_DIR = Path("/etc/systemd/system")


def _resolve(path_value: str | Path) -> Path:
    return Path(path_value).resolve()


def _owner_name(uid: int) -> str | None:
    try:
        import pwd
    except ImportError:
        return None
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return None


def _group_name(gid: int) -> str | None:
    try:
        import grp
    except ImportError:
        return None
    try:
        return grp.getgrgid(gid).gr_name
    except KeyError:
        return None


def _snapshot_path(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "is_dir": False,
            "is_file": False,
            "is_symlink": False,
            "owner": None,
            "group": None,
            "mode": None,
        }
    path_stat = path.stat()
    mode = stat.S_IMODE(path_stat.st_mode)
    return {
        "exists": True,
        "is_dir": path.is_dir(),
        "is_file": path.is_file(),
        "is_symlink": path.is_symlink(),
        "owner": _owner_name(path_stat.st_uid),
        "group": _group_name(path_stat.st_gid),
        "mode": mode,
    }


def _octal_mode(mode: int | None) -> str | None:
    if mode is None:
        return None
    return f"{mode:04o}"


def _is_private_mode(mode: int | None) -> bool:
    return mode is not None and (mode & 0o077) == 0


def _is_not_group_other_writable(mode: int | None) -> bool:
    return mode is not None and (mode & 0o022) == 0


def _check_path(
    *,
    path: Path,
    expected_type: str,
    expected_owner: str,
    expected_group: str,
    mode_policy: str,
    allow_missing: bool = False,
) -> dict[str, Any]:
    snapshot = _snapshot_path(path)
    mode = snapshot["mode"]
    type_ok = (
        snapshot["is_dir"] if expected_type == "dir" else snapshot["is_file"]
    )
    mode_ok = (
        _is_private_mode(mode)
        if mode_policy == "private"
        else _is_not_group_other_writable(mode)
    )
    exists_ok = snapshot["exists"] or allow_missing
    owner_ok = snapshot["owner"] == expected_owner if snapshot["exists"] else allow_missing
    group_ok = snapshot["group"] == expected_group if snapshot["exists"] else allow_missing
    symlink_ok = (not snapshot["is_symlink"]) if snapshot["exists"] else allow_missing
    kind_ok = type_ok if snapshot["exists"] else allow_missing
    overall_ok = exists_ok and owner_ok and group_ok and symlink_ok and kind_ok and (mode_ok if snapshot["exists"] else allow_missing)
    return {
        "ok": overall_ok,
        "path": str(path),
        "expected_type": expected_type,
        "expected_owner": expected_owner,
        "expected_group": expected_group,
        "mode_policy": mode_policy,
        "allow_missing": allow_missing,
        "snapshot": {
            **snapshot,
            "mode": _octal_mode(snapshot["mode"]),
        },
        "checks": {
            "exists_ok": exists_ok,
            "owner_ok": owner_ok,
            "group_ok": group_ok,
            "symlink_ok": symlink_ok,
            "kind_ok": kind_ok,
            "mode_ok": mode_ok if snapshot["exists"] else allow_missing,
        },
    }


def build_filesystem_isolation_report(
    *,
    app_dir: str | Path = "/opt/super_trader_quant",
    app_user: str = "supertrader",
    run_id: str | None = None,
) -> dict[str, Any]:
    app_root = _resolve(app_dir)
    data_dir = app_root / "data"
    logs_dir = app_root / "logs"
    backup_dir = data_dir / "backups"
    env_file = app_root / ".env"
    venv_dir = app_root / ".venv"
    database_file = data_dir / "super_trader_quant.db"
    scheduler_lock = data_dir / "scheduler.lock"

    checks = {
        "app_root": _check_path(
            path=app_root,
            expected_type="dir",
            expected_owner=app_user,
            expected_group=app_user,
            mode_policy="no_group_other_write",
        ),
        "env_file": _check_path(
            path=env_file,
            expected_type="file",
            expected_owner=app_user,
            expected_group=app_user,
            mode_policy="private",
        ),
        "venv_dir": _check_path(
            path=venv_dir,
            expected_type="dir",
            expected_owner=app_user,
            expected_group=app_user,
            mode_policy="no_group_other_write",
        ),
        "data_dir": _check_path(
            path=data_dir,
            expected_type="dir",
            expected_owner=app_user,
            expected_group=app_user,
            mode_policy="no_group_other_write",
        ),
        "logs_dir": _check_path(
            path=logs_dir,
            expected_type="dir",
            expected_owner=app_user,
            expected_group=app_user,
            mode_policy="no_group_other_write",
        ),
        "backup_dir": _check_path(
            path=backup_dir,
            expected_type="dir",
            expected_owner=app_user,
            expected_group=app_user,
            mode_policy="no_group_other_write",
        ),
        "database_file": _check_path(
            path=database_file,
            expected_type="file",
            expected_owner=app_user,
            expected_group=app_user,
            mode_policy="no_group_other_write",
        ),
        "scheduler_lock": _check_path(
            path=scheduler_lock,
            expected_type="file",
            expected_owner=app_user,
            expected_group=app_user,
            mode_policy="no_group_other_write",
            allow_missing=True,
        ),
        "api_unit_file": _check_path(
            path=SYSTEMD_DIR / "super-trader-quant-api.service",
            expected_type="file",
            expected_owner="root",
            expected_group="root",
            mode_policy="no_group_other_write",
        ),
        "scheduler_unit_file": _check_path(
            path=SYSTEMD_DIR / "super-trader-quant-scheduler.service",
            expected_type="file",
            expected_owner="root",
            expected_group="root",
            mode_policy="no_group_other_write",
        ),
        "watchdog_unit_file": _check_path(
            path=SYSTEMD_DIR / "super-trader-quant-watchdog.service",
            expected_type="file",
            expected_owner="root",
            expected_group="root",
            mode_policy="no_group_other_write",
        ),
        "watchdog_timer_file": _check_path(
            path=SYSTEMD_DIR / "super-trader-quant-watchdog.timer",
            expected_type="file",
            expected_owner="root",
            expected_group="root",
            mode_policy="no_group_other_write",
        ),
    }

    issues = []
    for check_name, check in checks.items():
        if check["ok"]:
            continue
        failing_bits = [name for name, passed in check["checks"].items() if not passed]
        issues.append(f"{check_name}: falhou em {', '.join(failing_bits)} ({check['path']})")

    return {
        "ok": not issues,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "hostname": socket.gethostname(),
        "app_env": settings.app_env,
        "app_dir": str(app_root),
        "app_user": app_user,
        "checks": checks,
        "issues": issues,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verifica ownership e permissões de isolamento do app no VPS.")
    parser.add_argument("--app-dir", default="/opt/super_trader_quant")
    parser.add_argument("--app-user", default="supertrader")
    parser.add_argument("--run-id", help="Identificador opcional da rodada de verificação.")
    parser.add_argument("--output", help="Salva o JSON completo em um arquivo.")
    args = parser.parse_args()

    report = build_filesystem_isolation_report(app_dir=args.app_dir, app_user=args.app_user, run_id=args.run_id)
    output_path = Path(args.output) if args.output else settings.resolved_log_dir / DEFAULT_RECEIPT_FILE
    write_json_receipt(output_path, report)

    print(f"ok: {report['ok']}")
    for check_name, check in report["checks"].items():
        print(f"- {check_name}: {check['ok']} -> {check['snapshot']}")
    print(f"receipt: {output_path}")
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
