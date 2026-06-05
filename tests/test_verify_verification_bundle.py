import json

from scripts import build_verification_bundle, verify_verification_bundle


def _write_bundle_inputs(tmp_path):
    payloads = {
        "telegram_canary_last.json": {
            "ok": True,
            "generated_at": "2026-05-18T00:00:00+00:00",
            "run_id": "run-1",
            "hostname": "host-a",
            "app_env": "production",
        },
        "verification_manifest_last.json": {
            "ok": True,
            "generated_at": "2026-05-18T00:00:01+00:00",
            "run_id": "run-1",
            "hostname": "host-a",
            "app_env": "production",
            "receipts": {},
        },
        "goal_acceptance_last.json": {
            "complete": True,
            "ready_for_local_handoff": True,
            "generated_at": "2026-05-18T00:00:02+00:00",
            "expected_run_id": "run-1",
            "summary": {"passed": 10, "blocked": 0, "total": 10},
            "next_required_actions": [],
        },
    }
    for filename, payload in payloads.items():
        (tmp_path / filename).write_text(json.dumps(payload), encoding="utf-8")
    return list(payloads.keys())


def test_verify_verification_bundle_passes_for_fresh_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(build_verification_bundle.settings, "app_env", "production")
    monkeypatch.setattr(verify_verification_bundle.settings, "app_env", "production")
    included = _write_bundle_inputs(tmp_path)

    build_verification_bundle.build_verification_bundle(
        run_id="run-1",
        log_dir=tmp_path,
        included_filenames=included,
        output_zip=tmp_path / "verification_bundle_last.zip",
        output_receipt=tmp_path / "verification_bundle_last.json",
    )

    report = verify_verification_bundle.verify_verification_bundle(
        expected_run_id="run-1",
        log_dir=tmp_path,
        bundle_zip=tmp_path / "verification_bundle_last.zip",
        bundle_receipt=tmp_path / "verification_bundle_last.json",
        check_live_files=True,
    )

    assert report["ok"] is True
    assert report["checks"]["bundle_zip_sha256_matches_receipt"] is True
    assert report["checks"]["bundle_summary_matches_receipt"] is True
    assert report["checks"]["archived_files_match_summary_hash"] is True
    assert report["checks"]["live_files_match_summary_hash"] is True


def test_verify_verification_bundle_flags_live_file_tampering(tmp_path, monkeypatch):
    monkeypatch.setattr(build_verification_bundle.settings, "app_env", "production")
    monkeypatch.setattr(verify_verification_bundle.settings, "app_env", "production")
    included = _write_bundle_inputs(tmp_path)

    build_verification_bundle.build_verification_bundle(
        run_id="run-1",
        log_dir=tmp_path,
        included_filenames=included,
        output_zip=tmp_path / "verification_bundle_last.zip",
        output_receipt=tmp_path / "verification_bundle_last.json",
    )
    (tmp_path / "telegram_canary_last.json").write_text(
        json.dumps(
            {
                "ok": False,
                "generated_at": "2026-05-18T00:05:00+00:00",
                "run_id": "run-1",
                "hostname": "host-a",
                "app_env": "production",
            }
        ),
        encoding="utf-8",
    )

    report = verify_verification_bundle.verify_verification_bundle(
        expected_run_id="run-1",
        log_dir=tmp_path,
        bundle_zip=tmp_path / "verification_bundle_last.zip",
        bundle_receipt=tmp_path / "verification_bundle_last.json",
        check_live_files=True,
    )

    assert report["ok"] is False
    assert "telegram_canary_last.json: live_hash_mismatch" in report["issues"]
    assert report["files"]["telegram_canary_last.json"]["reason"] == "live_hash_mismatch"
