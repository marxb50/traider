from scripts import production_preflight


def test_production_preflight_passes_with_safe_vps_config(monkeypatch, tmp_path):
    app_dir = tmp_path / "app"
    env_file = app_dir / ".env"
    env_file.parent.mkdir(parents=True)
    env_file.write_text("PAPER_BROKER=internal\nALLOW_EXTERNAL_PAPER=false\n", encoding="utf-8")
    env_file.chmod(0o600)

    monkeypatch.setattr(production_preflight.settings, "app_env", "production")
    monkeypatch.setattr(production_preflight.settings, "api_host", "127.0.0.1")
    monkeypatch.setattr(production_preflight.settings, "api_port", 8010)
    monkeypatch.setattr(
        production_preflight.settings,
        "database_url",
        f"sqlite:///{(app_dir / 'data/super_trader_quant.db').as_posix()}",
    )
    monkeypatch.setattr(production_preflight.settings, "log_dir", str(app_dir / "logs"))
    monkeypatch.setattr(production_preflight.settings, "backup_dir", str(app_dir / "data/backups"))
    monkeypatch.setattr(production_preflight.settings, "scheduler_lock_path", str(app_dir / "data/scheduler.lock"))
    monkeypatch.setattr(production_preflight.settings, "default_provider", "yfinance")
    monkeypatch.setattr(production_preflight.settings, "telegram_bot_token", "123456:real-token")
    monkeypatch.setattr(production_preflight.settings, "telegram_chat_ids", "111111111,123")
    monkeypatch.setattr(production_preflight.settings, "ops_admin_token", "ops-admin-real-token")
    monkeypatch.setattr(
        production_preflight,
        "collect_resource_metrics",
        lambda: {"resource_guard_ok": True},
    )

    report = production_preflight.build_preflight_report(strict=True, app_dir=app_dir, env_file=env_file)

    assert report["ok"] is True
    assert "generated_at" in report
    assert report["failures"] == []


def test_production_preflight_blocks_dangerous_vps_config(monkeypatch, tmp_path):
    app_dir = tmp_path / "app"
    env_file = app_dir / ".env"
    env_file.parent.mkdir(parents=True)
    env_file.write_text("PAPER_BROKER=alpaca\nALLOW_EXTERNAL_PAPER=true\n", encoding="utf-8")

    monkeypatch.setattr(production_preflight.settings, "app_env", "local")
    monkeypatch.setattr(production_preflight.settings, "api_host", "0.0.0.0")
    monkeypatch.setattr(production_preflight.settings, "api_port", 8000)
    monkeypatch.setattr(production_preflight.settings, "database_url", "sqlite:///./shared.db")
    monkeypatch.setattr(production_preflight.settings, "log_dir", str(tmp_path / "other_logs"))
    monkeypatch.setattr(production_preflight.settings, "backup_dir", str(tmp_path / "other_backups"))
    monkeypatch.setattr(production_preflight.settings, "scheduler_lock_path", str(tmp_path / "scheduler.lock"))
    monkeypatch.setattr(production_preflight.settings, "default_provider", "simulated")
    monkeypatch.setattr(production_preflight.settings, "telegram_bot_token", "dummy-token")
    monkeypatch.setattr(production_preflight.settings, "telegram_chat_ids", "123")
    monkeypatch.setattr(production_preflight.settings, "ops_admin_token", "dummy-token")
    monkeypatch.setattr(
        production_preflight,
        "collect_resource_metrics",
        lambda: {"resource_guard_ok": False, "low_disk_paths": ["log_dir"]},
    )

    report = production_preflight.build_preflight_report(strict=True, app_dir=app_dir, env_file=env_file)
    failed_names = {failure["name"] for failure in report["failures"]}

    assert report["ok"] is False
    assert "generated_at" in report
    assert "app_env_production_when_strict" in failed_names
    assert "api_host_loopback" in failed_names
    assert "provider_not_simulated_when_strict" in failed_names
    assert "telegram_token_real_when_strict" in failed_names
    assert "ops_admin_token_real_when_strict" in failed_names
    assert "resource_guard_ok" in failed_names
    assert "external_broker_disabled" in failed_names
