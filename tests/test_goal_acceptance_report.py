import json
from sqlmodel import create_engine

from scripts import goal_acceptance_report
from datetime import datetime, timedelta, timezone
from super_trader_quant.backend.app.demo_assets import EXPECTED_ASSET_COUNT, EXPECTED_ASSETS_BY_MARKET


def _healthy_readiness():
    return {
        "checks": {
            "active_asset_count_matches_expected": True,
            "active_asset_split_matches_expected": True,
            "memory_consistent": True,
            "scheduler_jobs_ok": True,
            "scheduler_heartbeat_present": True,
            "scheduler_heartbeat_not_starting": True,
            "scheduler_heartbeat_fresh": True,
            "no_stale_open_signals": True,
            "no_stale_pending_notifications": True,
            "deploy_artifacts_valid": True,
        },
        "active_asset_count": EXPECTED_ASSET_COUNT,
        "active_assets_by_market": EXPECTED_ASSETS_BY_MARKET,
        "expected_active_asset_count": EXPECTED_ASSET_COUNT,
        "expected_active_assets_by_market": EXPECTED_ASSETS_BY_MARKET,
        "memory_consistency": {"is_consistent": True},
        "scheduler_jobs": ["maintenance_job", "notification_job", "resolve_job", "scan_job"],
        "scheduler_heartbeat": {"last_event": "scan_job"},
        "scheduler_heartbeat_age_seconds": 1.0,
        "ops_metrics": {"stale_open_signals": 0, "stale_pending_notifications": 0},
    }


def _patch_healthy_dependencies(monkeypatch, tmp_path):
    monkeypatch.setattr(goal_acceptance_report, "init_db", lambda: None)
    monkeypatch.setattr(goal_acceptance_report, "engine", create_engine("sqlite://"))
    monkeypatch.setattr(goal_acceptance_report, "build_readiness_report", lambda strict=False, runtime=False: _healthy_readiness())
    monkeypatch.setattr(goal_acceptance_report, "validate_deploy_artifacts", lambda: {"ok": True, "issues": []})
    monkeypatch.setattr(goal_acceptance_report, "collect_watchdog_report", lambda session, strict=False: {"ok": True, "issues": []})
    monkeypatch.setattr(goal_acceptance_report.settings, "log_dir", str(tmp_path))
    monkeypatch.setattr(goal_acceptance_report.settings, "telegram_chat_ids", "111111111")
    monkeypatch.setattr(goal_acceptance_report.settings, "telegram_bot_token", "token-123")
    monkeypatch.setattr(goal_acceptance_report.settings, "ops_admin_token", "ops-token-123")
    monkeypatch.setattr(goal_acceptance_report.settings, "default_provider", "yfinance")
    monkeypatch.setattr(goal_acceptance_report.settings, "app_env", "production")


def test_acceptance_report_passes_when_runtime_is_healthy(monkeypatch, tmp_path):
    _patch_healthy_dependencies(monkeypatch, tmp_path)

    report = goal_acceptance_report.build_acceptance_report(strict=True, runtime=True)

    assert report["complete"] is True
    assert report["ready_for_local_handoff"] is True
    assert report["summary"]["blocked"] == 0


def test_acceptance_report_blocks_required_canary_without_receipt(monkeypatch, tmp_path):
    _patch_healthy_dependencies(monkeypatch, tmp_path)

    report = goal_acceptance_report.build_acceptance_report(
        strict=True,
        runtime=True,
        require_canary=True,
    )

    assert report["complete"] is False
    assert report["ready_for_local_handoff"] is False
    assert report["summary"]["blocked"] == 1
    blocked = [item for item in report["items"] if item["status"] == "blocked"]
    assert blocked[0]["requirement"] == "Canário Telegram via outbox quando exigido"


def test_acceptance_report_accepts_required_canary_receipt(monkeypatch, tmp_path):
    _patch_healthy_dependencies(monkeypatch, tmp_path)
    fresh_timestamp = datetime.now(timezone.utc).isoformat()
    canary_path = tmp_path / goal_acceptance_report.CANARY_RECEIPT_FILE
    canary_path.write_text(json.dumps({"ok": True, "sent": 1, "generated_at": fresh_timestamp, "run_id": "run-1", "hostname": "host-a", "app_env": "production"}), encoding="utf-8")

    report = goal_acceptance_report.build_acceptance_report(
        strict=True,
        runtime=True,
        require_canary=True,
        expected_run_id="run-1",
    )

    assert report["complete"] is True
    assert report["ready_for_local_handoff"] is True
    assert report["summary"]["blocked"] == 0
    canary_item = [item for item in report["items"] if item["requirement"] == "Canário Telegram via outbox quando exigido"][0]
    assert canary_item["evidence"]["latest_receipt"]["ok"] is True


def test_acceptance_report_blocks_required_preflight_without_receipt(monkeypatch, tmp_path):
    _patch_healthy_dependencies(monkeypatch, tmp_path)

    report = goal_acceptance_report.build_acceptance_report(
        strict=True,
        runtime=True,
        require_preflight=True,
    )

    assert report["complete"] is False
    assert report["ready_for_local_handoff"] is False
    blocked = [item for item in report["items"] if item["status"] == "blocked"]
    assert blocked[0]["requirement"] == "Preflight de produção quando exigido"


def test_acceptance_report_accepts_required_preflight_receipt(monkeypatch, tmp_path):
    _patch_healthy_dependencies(monkeypatch, tmp_path)
    fresh_timestamp = datetime.now(timezone.utc).isoformat()
    preflight_path = tmp_path / goal_acceptance_report.PREFLIGHT_RECEIPT_FILE
    preflight_path.write_text(json.dumps({"ok": True, "failures": [], "generated_at": fresh_timestamp, "run_id": "run-1", "hostname": "host-a", "app_env": "production", "strict": True, "app_dir": "/opt/super_trader_quant", "env_file": "/opt/super_trader_quant/.env"}), encoding="utf-8")

    report = goal_acceptance_report.build_acceptance_report(
        strict=True,
        runtime=True,
        require_preflight=True,
        expected_run_id="run-1",
    )

    assert report["complete"] is True
    assert report["ready_for_local_handoff"] is True
    preflight_item = [item for item in report["items"] if item["requirement"] == "Preflight de produção quando exigido"][0]
    assert preflight_item["evidence"]["latest_receipt"]["ok"] is True


def test_acceptance_report_blocks_required_ops_http_protection_without_receipt(monkeypatch, tmp_path):
    _patch_healthy_dependencies(monkeypatch, tmp_path)

    report = goal_acceptance_report.build_acceptance_report(
        strict=True,
        runtime=True,
        require_ops_protection=True,
    )

    assert report["complete"] is False
    assert report["ready_for_local_handoff"] is False
    blocked = [item for item in report["items"] if item["status"] == "blocked"]
    assert blocked[0]["requirement"] == "Proteção HTTP dos endpoints operacionais quando exigida"


def test_acceptance_report_accepts_required_ops_http_protection_receipt(monkeypatch, tmp_path):
    _patch_healthy_dependencies(monkeypatch, tmp_path)
    fresh_timestamp = datetime.now(timezone.utc).isoformat()
    ops_http_path = tmp_path / goal_acceptance_report.OPS_HTTP_PROTECTION_RECEIPT_FILE
    ops_http_path.write_text(json.dumps({"ok": True, "checks": {"authorized_payload_ok": True}, "generated_at": fresh_timestamp, "run_id": "run-1", "hostname": "host-a", "app_env": "production", "base_url": "http://127.0.0.1:8010"}), encoding="utf-8")

    report = goal_acceptance_report.build_acceptance_report(
        strict=True,
        runtime=True,
        require_ops_protection=True,
        expected_run_id="run-1",
    )

    assert report["complete"] is True
    assert report["ready_for_local_handoff"] is True
    ops_item = [item for item in report["items"] if item["requirement"] == "Proteção HTTP dos endpoints operacionais quando exigida"][0]
    assert ops_item["evidence"]["latest_receipt"]["ok"] is True


def test_acceptance_report_blocks_required_systemd_runtime_without_receipt(monkeypatch, tmp_path):
    _patch_healthy_dependencies(monkeypatch, tmp_path)

    report = goal_acceptance_report.build_acceptance_report(
        strict=True,
        runtime=True,
        require_systemd_runtime=True,
    )

    assert report["complete"] is False
    assert report["ready_for_local_handoff"] is False
    blocked = [item for item in report["items"] if item["status"] == "blocked"]
    assert blocked[0]["requirement"] == "Runtime systemd isolado no VPS quando exigido"


def test_acceptance_report_accepts_required_systemd_runtime_receipt(monkeypatch, tmp_path):
    _patch_healthy_dependencies(monkeypatch, tmp_path)
    fresh_timestamp = datetime.now(timezone.utc).isoformat()
    systemd_path = tmp_path / goal_acceptance_report.SYSTEMD_RUNTIME_RECEIPT_FILE
    systemd_path.write_text(json.dumps({"ok": True, "units": {"super-trader-quant-api.service": {"ok": True}}, "generated_at": fresh_timestamp, "run_id": "run-1", "hostname": "host-a", "app_env": "production"}), encoding="utf-8")

    report = goal_acceptance_report.build_acceptance_report(
        strict=True,
        runtime=True,
        require_systemd_runtime=True,
        expected_run_id="run-1",
    )

    assert report["complete"] is True
    assert report["ready_for_local_handoff"] is True
    systemd_item = [item for item in report["items"] if item["requirement"] == "Runtime systemd isolado no VPS quando exigido"][0]
    assert systemd_item["evidence"]["latest_receipt"]["ok"] is True


def test_acceptance_report_blocks_required_filesystem_isolation_without_receipt(monkeypatch, tmp_path):
    _patch_healthy_dependencies(monkeypatch, tmp_path)

    report = goal_acceptance_report.build_acceptance_report(
        strict=True,
        runtime=True,
        require_filesystem_isolation=True,
    )

    assert report["complete"] is False
    assert report["ready_for_local_handoff"] is False
    blocked = [item for item in report["items"] if item["status"] == "blocked"]
    assert blocked[0]["requirement"] == "Ownership e permissões do app no VPS quando exigidos"


def test_acceptance_report_accepts_required_filesystem_isolation_receipt(monkeypatch, tmp_path):
    _patch_healthy_dependencies(monkeypatch, tmp_path)
    fresh_timestamp = datetime.now(timezone.utc).isoformat()
    fs_path = tmp_path / goal_acceptance_report.FILESYSTEM_ISOLATION_RECEIPT_FILE
    fs_path.write_text(json.dumps({"ok": True, "checks": {"app_root": {"ok": True}}, "generated_at": fresh_timestamp, "run_id": "run-1", "hostname": "host-a", "app_env": "production", "app_dir": "/opt/super_trader_quant", "app_user": "supertrader"}), encoding="utf-8")

    report = goal_acceptance_report.build_acceptance_report(
        strict=True,
        runtime=True,
        require_filesystem_isolation=True,
        expected_run_id="run-1",
    )

    assert report["complete"] is True
    assert report["ready_for_local_handoff"] is True
    fs_item = [item for item in report["items"] if item["requirement"] == "Ownership e permissões do app no VPS quando exigidos"][0]
    assert fs_item["evidence"]["latest_receipt"]["ok"] is True


def test_acceptance_report_blocks_required_process_runtime_without_receipt(monkeypatch, tmp_path):
    _patch_healthy_dependencies(monkeypatch, tmp_path)

    report = goal_acceptance_report.build_acceptance_report(
        strict=True,
        runtime=True,
        require_process_runtime=True,
    )

    assert report["complete"] is False
    assert report["ready_for_local_handoff"] is False
    blocked = [item for item in report["items"] if item["status"] == "blocked"]
    assert blocked[0]["requirement"] == "Processos e bind de runtime do VPS quando exigidos"


def test_acceptance_report_accepts_required_process_runtime_receipt(monkeypatch, tmp_path):
    _patch_healthy_dependencies(monkeypatch, tmp_path)
    fresh_timestamp = datetime.now(timezone.utc).isoformat()
    process_path = tmp_path / goal_acceptance_report.PROCESS_RUNTIME_RECEIPT_FILE
    process_path.write_text(json.dumps({"ok": True, "listener_checks": {"all_loopback": True}, "generated_at": fresh_timestamp, "run_id": "run-1", "hostname": "host-a", "app_env": "production", "app_dir": "/opt/super_trader_quant", "app_user": "supertrader", "api_port": 8010}), encoding="utf-8")

    report = goal_acceptance_report.build_acceptance_report(
        strict=True,
        runtime=True,
        require_process_runtime=True,
        expected_run_id="run-1",
    )

    assert report["complete"] is True
    assert report["ready_for_local_handoff"] is True
    process_item = [item for item in report["items"] if item["requirement"] == "Processos e bind de runtime do VPS quando exigidos"][0]
    assert process_item["evidence"]["latest_receipt"]["ok"] is True


def test_acceptance_report_blocks_required_notification_drain_without_receipt(monkeypatch, tmp_path):
    _patch_healthy_dependencies(monkeypatch, tmp_path)

    report = goal_acceptance_report.build_acceptance_report(
        strict=True,
        runtime=True,
        require_notification_drain=True,
    )

    assert report["complete"] is False
    assert report["ready_for_local_handoff"] is False
    blocked = [item for item in report["items"] if item["status"] == "blocked"]
    assert blocked[0]["requirement"] == "Drenagem da outbox quando exigida"


def test_acceptance_report_accepts_required_notification_drain_receipt(monkeypatch, tmp_path):
    _patch_healthy_dependencies(monkeypatch, tmp_path)
    fresh_timestamp = datetime.now(timezone.utc).isoformat()
    drain_path = tmp_path / goal_acceptance_report.NOTIFICATION_DRAIN_RECEIPT_FILE
    drain_path.write_text(
        json.dumps(
            {
                "ok": True,
                "generated_at": fresh_timestamp,
                "run_id": "run-1",
                "hostname": "host-a",
                "app_env": "production",
                "pending_before": 3,
                "pending_after": 0,
                "stop_reason": "queue_empty",
            }
        ),
        encoding="utf-8",
    )

    report = goal_acceptance_report.build_acceptance_report(
        strict=True,
        runtime=True,
        require_notification_drain=True,
        expected_run_id="run-1",
    )

    assert report["complete"] is True
    assert report["ready_for_local_handoff"] is True
    drain_item = [item for item in report["items"] if item["requirement"] == "Drenagem da outbox quando exigida"][0]
    assert drain_item["evidence"]["latest_receipt"]["ok"] is True


def test_acceptance_report_accepts_required_verification_manifest(monkeypatch, tmp_path):
    _patch_healthy_dependencies(monkeypatch, tmp_path)
    fresh_timestamp = datetime.now(timezone.utc).isoformat()
    required = {
        goal_acceptance_report.CANARY_RECEIPT_FILE: {"ok": True, "generated_at": fresh_timestamp, "run_id": "run-1", "hostname": "host-a", "app_env": "production"},
        goal_acceptance_report.PREFLIGHT_RECEIPT_FILE: {"ok": True, "generated_at": fresh_timestamp, "run_id": "run-1", "hostname": "host-a", "app_env": "production", "strict": True, "app_dir": "/opt/super_trader_quant", "env_file": "/opt/super_trader_quant/.env"},
        goal_acceptance_report.NOTIFICATION_DRAIN_RECEIPT_FILE: {"ok": True, "generated_at": fresh_timestamp, "run_id": "run-1", "hostname": "host-a", "app_env": "production", "pending_before": 2, "pending_after": 0},
    }
    manifest_entries = {}
    from scripts.receipt_utils import hash_file_sha256
    for filename, payload in required.items():
        path = tmp_path / filename
        path.write_text(json.dumps(payload), encoding="utf-8")
        manifest_entries[filename] = {
            "ok": True,
            "reason": "ok",
            "sha256": hash_file_sha256(path),
        }
    manifest_path = tmp_path / goal_acceptance_report.VERIFICATION_MANIFEST_RECEIPT_FILE
    manifest_path.write_text(
        json.dumps(
            {
                "ok": True,
                "generated_at": fresh_timestamp,
                "run_id": "run-1",
                "hostname": "host-a",
                "app_env": "production",
                "receipts": manifest_entries,
            }
        ),
        encoding="utf-8",
    )

    report = goal_acceptance_report.build_acceptance_report(
        strict=True,
        runtime=True,
        require_canary=True,
        require_preflight=True,
        require_notification_drain=True,
        require_verification_manifest=True,
        expected_run_id="run-1",
    )

    assert report["complete"] is True
    manifest_item = [item for item in report["items"] if item["requirement"] == "Manifesto hashado da rodada de verificação quando exigido"][0]
    assert manifest_item["evidence"]["hash_coherence"]["reason"] == "ok"


def test_acceptance_report_blocks_stale_required_canary_receipt(monkeypatch, tmp_path):
    _patch_healthy_dependencies(monkeypatch, tmp_path)
    stale_timestamp = (datetime.now(timezone.utc) - timedelta(minutes=goal_acceptance_report.RECEIPT_MAX_AGE_MINUTES + 5)).isoformat()
    canary_path = tmp_path / goal_acceptance_report.CANARY_RECEIPT_FILE
    canary_path.write_text(json.dumps({"ok": True, "generated_at": stale_timestamp, "hostname": "host-a", "app_env": "production"}), encoding="utf-8")

    report = goal_acceptance_report.build_acceptance_report(
        strict=True,
        runtime=True,
        require_canary=True,
    )

    assert report["complete"] is False
    blocked = [item for item in report["items"] if item["status"] == "blocked"]
    assert blocked[0]["requirement"] == "Canário Telegram via outbox quando exigido"
    assert blocked[0]["evidence"]["freshness"]["reason"] == "stale_receipt"


def test_acceptance_report_blocks_required_receipt_with_mismatched_run_id(monkeypatch, tmp_path):
    _patch_healthy_dependencies(monkeypatch, tmp_path)
    fresh_timestamp = datetime.now(timezone.utc).isoformat()
    canary_path = tmp_path / goal_acceptance_report.CANARY_RECEIPT_FILE
    canary_path.write_text(json.dumps({"ok": True, "generated_at": fresh_timestamp, "run_id": "run-old", "hostname": "host-a", "app_env": "production"}), encoding="utf-8")

    report = goal_acceptance_report.build_acceptance_report(
        strict=True,
        runtime=True,
        require_canary=True,
        expected_run_id="run-new",
    )

    assert report["complete"] is False
    blocked = [item for item in report["items"] if item["status"] == "blocked"]
    assert blocked[0]["requirement"] == "Canário Telegram via outbox quando exigido"
    assert blocked[0]["evidence"]["run_id"]["reason"] == "mismatch"


def test_acceptance_report_blocks_required_receipts_from_different_hosts(monkeypatch, tmp_path):
    _patch_healthy_dependencies(monkeypatch, tmp_path)
    fresh_timestamp = datetime.now(timezone.utc).isoformat()
    preflight_path = tmp_path / goal_acceptance_report.PREFLIGHT_RECEIPT_FILE
    ops_http_path = tmp_path / goal_acceptance_report.OPS_HTTP_PROTECTION_RECEIPT_FILE
    preflight_path.write_text(json.dumps({"ok": True, "generated_at": fresh_timestamp, "run_id": "run-1", "hostname": "host-a", "app_env": "production", "strict": True, "app_dir": "/opt/super_trader_quant", "env_file": "/opt/super_trader_quant/.env"}), encoding="utf-8")
    ops_http_path.write_text(json.dumps({"ok": True, "generated_at": fresh_timestamp, "run_id": "run-1", "hostname": "host-b", "app_env": "production", "base_url": "http://127.0.0.1:8010"}), encoding="utf-8")

    report = goal_acceptance_report.build_acceptance_report(
        strict=True,
        runtime=True,
        require_preflight=True,
        require_ops_protection=True,
        expected_run_id="run-1",
    )

    assert report["complete"] is False
    blocked = [item for item in report["items"] if item["status"] == "blocked"]
    coherence_item = [item for item in blocked if item["requirement"] == "Recibos obrigatórios coerentes no mesmo host de produção"][0]
    assert coherence_item["evidence"]["coherence"]["reason"] == "host_or_env_mismatch"


def test_acceptance_report_blocks_required_receipt_with_wrong_expected_parameters(monkeypatch, tmp_path):
    _patch_healthy_dependencies(monkeypatch, tmp_path)
    fresh_timestamp = datetime.now(timezone.utc).isoformat()
    preflight_path = tmp_path / goal_acceptance_report.PREFLIGHT_RECEIPT_FILE
    process_path = tmp_path / goal_acceptance_report.PROCESS_RUNTIME_RECEIPT_FILE
    preflight_path.write_text(json.dumps({"ok": True, "generated_at": fresh_timestamp, "run_id": "run-1", "hostname": "host-a", "app_env": "production", "strict": True, "app_dir": "/srv/wrong", "env_file": "/srv/wrong/.env"}), encoding="utf-8")
    process_path.write_text(json.dumps({"ok": True, "generated_at": fresh_timestamp, "run_id": "run-1", "hostname": "host-a", "app_env": "production", "app_dir": "/srv/wrong", "app_user": "otheruser", "api_port": 9000}), encoding="utf-8")

    report = goal_acceptance_report.build_acceptance_report(
        strict=True,
        runtime=True,
        require_preflight=True,
        require_process_runtime=True,
        expected_run_id="run-1",
    )

    assert report["complete"] is False
    blocked = [item for item in report["items"] if item["status"] == "blocked"]
    parameter_item = [item for item in blocked if item["requirement"] == "Recibos obrigatórios refletem a configuração isolada esperada"][0]
    assert parameter_item["evidence"]["coherence"]["reason"] == "parameter_mismatch"


def test_acceptance_report_blocks_invalid_json_required_receipt(monkeypatch, tmp_path):
    _patch_healthy_dependencies(monkeypatch, tmp_path)
    canary_path = tmp_path / goal_acceptance_report.CANARY_RECEIPT_FILE
    canary_path.write_text('{"ok": true,', encoding="utf-8")

    report = goal_acceptance_report.build_acceptance_report(
        strict=True,
        runtime=True,
        require_canary=True,
    )

    assert report["complete"] is False
    blocked = [item for item in report["items"] if item["status"] == "blocked"]
    canary_item = [item for item in blocked if item["requirement"] == "Canário Telegram via outbox quando exigido"][0]
    assert canary_item["evidence"]["freshness"]["reason"] == "invalid_json"


def test_acceptance_report_blocks_verification_manifest_hash_mismatch(monkeypatch, tmp_path):
    _patch_healthy_dependencies(monkeypatch, tmp_path)
    fresh_timestamp = datetime.now(timezone.utc).isoformat()
    canary_path = tmp_path / goal_acceptance_report.CANARY_RECEIPT_FILE
    canary_path.write_text(
        json.dumps({"ok": True, "generated_at": fresh_timestamp, "run_id": "run-1", "hostname": "host-a", "app_env": "production"}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / goal_acceptance_report.VERIFICATION_MANIFEST_RECEIPT_FILE
    manifest_path.write_text(
        json.dumps(
            {
                "ok": True,
                "generated_at": fresh_timestamp,
                "run_id": "run-1",
                "hostname": "host-a",
                "app_env": "production",
                "receipts": {
                    goal_acceptance_report.CANARY_RECEIPT_FILE: {
                        "ok": True,
                        "reason": "ok",
                        "sha256": "bad-hash",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    report = goal_acceptance_report.build_acceptance_report(
        strict=True,
        runtime=True,
        require_canary=True,
        require_verification_manifest=True,
        expected_run_id="run-1",
    )

    assert report["complete"] is False
    blocked = [item for item in report["items"] if item["status"] == "blocked"]
    manifest_item = [item for item in blocked if item["requirement"] == "Manifesto hashado da rodada de verificação quando exigido"][0]
    assert manifest_item["evidence"]["hash_coherence"]["reason"] == "manifest_hash_mismatch"
