from scripts import verify_systemd_runtime


def _show_values(unit: str) -> dict[str, str]:
    data = {
        "super-trader-quant-api.service": {
            "LoadState": "loaded",
            "ActiveState": "active",
            "SubState": "running",
            "UnitFileState": "enabled",
            "FragmentPath": "/etc/systemd/system/super-trader-quant-api.service",
        },
        "super-trader-quant-scheduler.service": {
            "LoadState": "loaded",
            "ActiveState": "active",
            "SubState": "running",
            "UnitFileState": "enabled",
            "FragmentPath": "/etc/systemd/system/super-trader-quant-scheduler.service",
        },
        "super-trader-quant-watchdog.service": {
            "LoadState": "loaded",
            "UnitFileState": "static",
            "FragmentPath": "/etc/systemd/system/super-trader-quant-watchdog.service",
        },
        "super-trader-quant-watchdog.timer": {
            "LoadState": "loaded",
            "ActiveState": "active",
            "SubState": "waiting",
            "UnitFileState": "enabled",
            "FragmentPath": "/etc/systemd/system/super-trader-quant-watchdog.timer",
        },
    }
    return data[unit]


def _cat_values(unit: str) -> str:
    snippets = verify_systemd_runtime.SERVICE_EXPECTATIONS[unit]["snippets"]
    return "\n".join(snippets)


def test_verify_systemd_runtime_report_passes_with_expected_units(monkeypatch):
    monkeypatch.setattr(verify_systemd_runtime, "_systemctl_show", lambda unit, properties: _show_values(unit))
    monkeypatch.setattr(verify_systemd_runtime, "_systemctl_cat", _cat_values)

    report = verify_systemd_runtime.build_systemd_runtime_report(run_id="run-1")

    assert report["ok"] is True
    assert report["run_id"] == "run-1"
    assert "hostname" in report
    assert "app_env" in report
    assert report["issues"] == []
    assert all(unit_report["ok"] for unit_report in report["units"].values())


def test_verify_systemd_runtime_report_flags_property_and_snippet_failures(monkeypatch):
    def fake_show(unit, properties):
        values = _show_values(unit).copy()
        if unit == "super-trader-quant-scheduler.service":
            values["ActiveState"] = "failed"
        return values

    def fake_cat(unit):
        if unit == "super-trader-quant-watchdog.timer":
            return "OnBootSec=2min\nUnit=super-trader-quant-watchdog.service"
        return _cat_values(unit)

    monkeypatch.setattr(verify_systemd_runtime, "_systemctl_show", fake_show)
    monkeypatch.setattr(verify_systemd_runtime, "_systemctl_cat", fake_cat)

    report = verify_systemd_runtime.build_systemd_runtime_report(run_id="run-1")

    assert report["ok"] is False
    assert report["run_id"] == "run-1"
    assert "hostname" in report
    assert "app_env" in report
    assert any("super-trader-quant-scheduler.service" in issue for issue in report["issues"])
    assert any("super-trader-quant-watchdog.timer" in issue for issue in report["issues"])
