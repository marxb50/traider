import json
from datetime import datetime, timezone

from scripts import verify_verification_round


def test_verify_verification_round_accepts_complete_round(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_verification_round.settings, "app_env", "production")
    run_id = "run-1"
    hostname = "host-a"
    app_env = "production"
    fresh_timestamp = datetime.now(timezone.utc).isoformat()

    (tmp_path / "goal_acceptance_last.json").write_text(
        json.dumps(
            {
                "complete": True,
                "run_id": run_id,
                "hostname": hostname,
                "app_env": app_env,
                "generated_at": fresh_timestamp,
                "summary": {"passed": 10, "blocked": 0, "total": 10},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "verification_bundle_last.json").write_text(
        json.dumps(
            {
                "ok": True,
                "run_id": run_id,
                "hostname": hostname,
                "app_env": app_env,
                "generated_at": fresh_timestamp,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "verification_bundle_check_last.json").write_text(
        json.dumps(
            {
                "ok": True,
                "run_id": run_id,
                "hostname": hostname,
                "app_env": app_env,
                "generated_at": fresh_timestamp,
                "check_live_files": True,
                "checks": {"live_files_match_summary_hash": True},
            }
        ),
        encoding="utf-8",
    )

    report = verify_verification_round.verify_verification_round(
        expected_run_id=run_id,
        log_dir=tmp_path,
    )

    assert report["ok"] is True
    assert report["checks"]["goal_acceptance_complete"] is True
    assert report["checks"]["bundle_ok"] is True
    assert report["checks"]["bundle_check_ok"] is True
    assert report["checks"]["bundle_check_live_files_verified"] is True


def test_verify_verification_round_blocks_on_mismatch_or_incomplete_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_verification_round.settings, "app_env", "production")
    (tmp_path / "goal_acceptance_last.json").write_text(
        json.dumps(
            {
                "complete": False,
                "run_id": "run-old",
                "hostname": "host-a",
                "app_env": "production",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "verification_bundle_last.json").write_text(
        json.dumps(
            {
                "ok": True,
                "run_id": "run-new",
                "hostname": "host-a",
                "app_env": "production",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "verification_bundle_check_last.json").write_text(
        json.dumps(
            {
                "ok": False,
                "run_id": "run-new",
                "hostname": "host-b",
                "app_env": "production",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "check_live_files": False,
                "checks": {"live_files_match_summary_hash": False},
            }
        ),
        encoding="utf-8",
    )

    report = verify_verification_round.verify_verification_round(
        expected_run_id="run-new",
        log_dir=tmp_path,
    )

    assert report["ok"] is False
    assert "goal_acceptance: incomplete" in report["issues"]
    assert "run_id: mismatch_between_receipts" in report["issues"]
    assert "identity: hostname_mismatch" in report["issues"]
    assert "bundle_check: live_files_not_verified" in report["issues"]
