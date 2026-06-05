from scripts import verify_filesystem_isolation


def _snapshot(owner: str, group: str, mode: int, *, is_dir: bool = False, is_file: bool = False, is_symlink: bool = False):
    return {
        "exists": True,
        "is_dir": is_dir,
        "is_file": is_file,
        "is_symlink": is_symlink,
        "owner": owner,
        "group": group,
        "mode": mode,
    }


def test_verify_filesystem_isolation_report_passes_with_expected_snapshots(monkeypatch):
    app_dir = verify_filesystem_isolation._resolve("/opt/super_trader_quant")
    systemd_dir = verify_filesystem_isolation.SYSTEMD_DIR
    snapshots = {
        str(app_dir): _snapshot("supertrader", "supertrader", 0o755, is_dir=True),
        str(app_dir / ".env"): _snapshot("supertrader", "supertrader", 0o600, is_file=True),
        str(app_dir / ".venv"): _snapshot("supertrader", "supertrader", 0o755, is_dir=True),
        str(app_dir / "data"): _snapshot("supertrader", "supertrader", 0o755, is_dir=True),
        str(app_dir / "logs"): _snapshot("supertrader", "supertrader", 0o755, is_dir=True),
        str(app_dir / "data/backups"): _snapshot("supertrader", "supertrader", 0o755, is_dir=True),
        str(app_dir / "data/super_trader_quant.db"): _snapshot("supertrader", "supertrader", 0o644, is_file=True),
        str(app_dir / "data/scheduler.lock"): _snapshot("supertrader", "supertrader", 0o644, is_file=True),
        str(systemd_dir / "super-trader-quant-api.service"): _snapshot("root", "root", 0o644, is_file=True),
        str(systemd_dir / "super-trader-quant-scheduler.service"): _snapshot("root", "root", 0o644, is_file=True),
        str(systemd_dir / "super-trader-quant-watchdog.service"): _snapshot("root", "root", 0o644, is_file=True),
        str(systemd_dir / "super-trader-quant-watchdog.timer"): _snapshot("root", "root", 0o644, is_file=True),
    }

    monkeypatch.setattr(
        verify_filesystem_isolation,
        "_snapshot_path",
        lambda path: snapshots.get(
            str(path),
            {"exists": False, "is_dir": False, "is_file": False, "is_symlink": False, "owner": None, "group": None, "mode": None},
        ),
    )

    report = verify_filesystem_isolation.build_filesystem_isolation_report(run_id="run-1")

    assert report["ok"] is True
    assert report["run_id"] == "run-1"
    assert "hostname" in report
    assert "app_env" in report
    assert report["issues"] == []
    assert all(check["ok"] for check in report["checks"].values())


def test_verify_filesystem_isolation_report_flags_loose_permissions_and_wrong_owner(monkeypatch):
    app_dir = verify_filesystem_isolation._resolve("/opt/super_trader_quant")
    systemd_dir = verify_filesystem_isolation.SYSTEMD_DIR
    snapshots = {
        str(app_dir): _snapshot("root", "root", 0o777, is_dir=True),
        str(app_dir / ".env"): _snapshot("supertrader", "supertrader", 0o644, is_file=True),
        str(app_dir / ".venv"): _snapshot("supertrader", "supertrader", 0o755, is_dir=True),
        str(app_dir / "data"): _snapshot("supertrader", "supertrader", 0o755, is_dir=True),
        str(app_dir / "logs"): _snapshot("supertrader", "supertrader", 0o755, is_dir=True),
        str(app_dir / "data/backups"): _snapshot("supertrader", "supertrader", 0o755, is_dir=True),
        str(app_dir / "data/super_trader_quant.db"): _snapshot("supertrader", "supertrader", 0o644, is_file=True),
        str(app_dir / "data/scheduler.lock"): {"exists": False, "is_dir": False, "is_file": False, "is_symlink": False, "owner": None, "group": None, "mode": None},
        str(systemd_dir / "super-trader-quant-api.service"): _snapshot("root", "root", 0o664, is_file=True),
        str(systemd_dir / "super-trader-quant-scheduler.service"): _snapshot("root", "root", 0o644, is_file=True),
        str(systemd_dir / "super-trader-quant-watchdog.service"): _snapshot("root", "root", 0o644, is_file=True),
        str(systemd_dir / "super-trader-quant-watchdog.timer"): _snapshot("root", "root", 0o644, is_file=True),
    }

    monkeypatch.setattr(
        verify_filesystem_isolation,
        "_snapshot_path",
        lambda path: snapshots.get(
            str(path),
            {"exists": False, "is_dir": False, "is_file": False, "is_symlink": False, "owner": None, "group": None, "mode": None},
        ),
    )

    report = verify_filesystem_isolation.build_filesystem_isolation_report(run_id="run-1")

    assert report["ok"] is False
    assert report["run_id"] == "run-1"
    assert "hostname" in report
    assert "app_env" in report
    assert any("app_root" in issue for issue in report["issues"])
    assert any("env_file" in issue for issue in report["issues"])
    assert any("api_unit_file" in issue for issue in report["issues"])
