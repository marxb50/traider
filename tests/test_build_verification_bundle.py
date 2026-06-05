import json
import zipfile

from scripts import build_verification_bundle


def test_build_verification_bundle_writes_zip_and_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(build_verification_bundle.settings, "app_env", "production")
    included = {
        "telegram_canary_last.json": {
            "ok": True,
            "generated_at": "2026-05-18T00:00:00+00:00",
            "run_id": "run-1",
            "hostname": "host-a",
            "app_env": "production",
        },
        "goal_acceptance_last.json": {
            "complete": True,
            "ready_for_local_handoff": True,
            "generated_at": "2026-05-18T00:00:01+00:00",
            "expected_run_id": "run-1",
            "summary": {"passed": 10, "blocked": 0, "total": 10},
            "next_required_actions": [],
        },
    }
    for filename, payload in included.items():
        (tmp_path / filename).write_text(json.dumps(payload), encoding="utf-8")

    report = build_verification_bundle.build_verification_bundle(
        run_id="run-1",
        log_dir=tmp_path,
        included_filenames=list(included.keys()),
        output_zip=tmp_path / "verification_bundle_last.zip",
        output_receipt=tmp_path / "verification_bundle_last.json",
    )

    assert report["ok"] is True
    assert (tmp_path / "verification_bundle_last.zip").exists()
    assert (tmp_path / "verification_bundle_last.json").exists()
    assert report["acceptance_summary"]["complete"] is True

    with zipfile.ZipFile(tmp_path / "verification_bundle_last.zip") as archive:
        names = set(archive.namelist())
        assert "summary/bundle_summary.json" in names
        assert "summary/bundle_summary.md" in names
        assert "receipts/telegram_canary_last.json" in names
        assert "receipts/goal_acceptance_last.json" in names
        summary = json.loads(archive.read("summary/bundle_summary.json").decode("utf-8"))
        assert summary["run_id"] == "run-1"
        assert summary["files"]["goal_acceptance_last.json"]["content_reason"] == "acceptance_complete"


def test_build_verification_bundle_flags_run_id_mismatch_and_incomplete_acceptance(tmp_path, monkeypatch):
    monkeypatch.setattr(build_verification_bundle.settings, "app_env", "production")
    (tmp_path / "goal_acceptance_last.json").write_text(
        json.dumps(
            {
                "complete": False,
                "ready_for_local_handoff": False,
                "generated_at": "2026-05-18T00:00:01+00:00",
                "expected_run_id": "run-old",
            }
        ),
        encoding="utf-8",
    )

    report = build_verification_bundle.build_verification_bundle(
        run_id="run-new",
        log_dir=tmp_path,
        included_filenames=["goal_acceptance_last.json"],
        output_zip=tmp_path / "verification_bundle_last.zip",
        output_receipt=tmp_path / "verification_bundle_last.json",
    )

    assert report["ok"] is False
    assert "goal_acceptance_last.json: run_id_mismatch" in report["issues"]
    assert report["files"]["goal_acceptance_last.json"]["content_reason"] == "acceptance_incomplete"
