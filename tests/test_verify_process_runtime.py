from scripts import verify_process_runtime


def test_verify_process_runtime_report_passes_with_expected_processes(monkeypatch):
    resolved_app_dir = str(verify_process_runtime.Path("/opt/super_trader_quant").resolve())
    python_path = str(verify_process_runtime.Path(resolved_app_dir) / ".venv" / "bin" / "python")
    show_map = {
        verify_process_runtime.API_UNIT: {"MainPID": "123", "ActiveState": "active", "SubState": "running"},
        verify_process_runtime.SCHEDULER_UNIT: {"MainPID": "456", "ActiveState": "active", "SubState": "running"},
    }
    monkeypatch.setattr(verify_process_runtime, "_systemctl_show", lambda unit, properties: show_map[unit])
    monkeypatch.setattr(verify_process_runtime, "_process_owner", lambda pid: "supertrader")
    monkeypatch.setattr(
        verify_process_runtime,
        "_read_proc_link",
        lambda pid, name: resolved_app_dir if name == "cwd" else python_path,
    )

    def fake_cmdline(pid):
        if pid == 123:
            return [python_path, "-m", "scripts.run_api"]
        return [python_path, "-m", "scripts.run_scheduler"]

    monkeypatch.setattr(verify_process_runtime, "_read_proc_cmdline", fake_cmdline)
    monkeypatch.setattr(
        verify_process_runtime,
        "_ss_listeners_for_port",
        lambda port: [
            {
                "raw": 'LISTEN 0 4096 127.0.0.1:8010 0.0.0.0:* users:(("python",pid=123,fd=3))',
                "local_address": "127.0.0.1:8010",
                "process_info": 'users:(("python",pid=123,fd=3))',
            }
        ],
    )

    report = verify_process_runtime.build_process_runtime_report(app_dir=resolved_app_dir, run_id="run-1")

    assert report["ok"] is True
    assert report["run_id"] == "run-1"
    assert "hostname" in report
    assert "app_env" in report
    assert report["api_process"]["ok"] is True
    assert report["scheduler_process"]["ok"] is True
    assert report["listener_checks"]["all_loopback"] is True


def test_verify_process_runtime_report_flags_bad_bind_and_process_identity(monkeypatch):
    resolved_app_dir = str(verify_process_runtime.Path("/opt/super_trader_quant").resolve())
    python_path = str(verify_process_runtime.Path(resolved_app_dir) / ".venv" / "bin" / "python")
    show_map = {
        verify_process_runtime.API_UNIT: {"MainPID": "123", "ActiveState": "active", "SubState": "running"},
        verify_process_runtime.SCHEDULER_UNIT: {"MainPID": "456", "ActiveState": "failed", "SubState": "dead"},
    }
    monkeypatch.setattr(verify_process_runtime, "_systemctl_show", lambda unit, properties: show_map[unit])
    monkeypatch.setattr(verify_process_runtime, "_process_owner", lambda pid: "root" if pid == 123 else "supertrader")
    monkeypatch.setattr(
        verify_process_runtime,
        "_read_proc_link",
        lambda pid, name: "/tmp" if name == "cwd" and pid == 123 else python_path,
    )

    def fake_cmdline(pid):
        if pid == 123:
            return ["/usr/bin/python3", "-m", "scripts.run_api"]
        return [python_path, "-m", "wrong.module"]

    monkeypatch.setattr(verify_process_runtime, "_read_proc_cmdline", fake_cmdline)
    monkeypatch.setattr(
        verify_process_runtime,
        "_ss_listeners_for_port",
        lambda port: [
            {
                "raw": 'LISTEN 0 4096 0.0.0.0:8010 0.0.0.0:* users:(("python",pid=999,fd=3))',
                "local_address": "0.0.0.0:8010",
                "process_info": 'users:(("python",pid=999,fd=3))',
            }
        ],
    )

    report = verify_process_runtime.build_process_runtime_report(app_dir=resolved_app_dir, run_id="run-1")

    assert report["ok"] is False
    assert report["run_id"] == "run-1"
    assert "hostname" in report
    assert "app_env" in report
    assert any("super-trader-quant-api.service" in issue for issue in report["issues"])
    assert any("super-trader-quant-scheduler.service" in issue for issue in report["issues"])
    assert any("api_port_8010" in issue for issue in report["issues"])
