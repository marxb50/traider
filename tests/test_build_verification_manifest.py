import json

from scripts import build_verification_manifest
from scripts.receipt_utils import hash_file_sha256


def test_build_verification_manifest_hashes_expected_receipts(tmp_path):
    receipt_names = ["a.json", "b.json"]
    for name in receipt_names:
        (tmp_path / name).write_text(
            json.dumps({"ok": True, "run_id": "run-1", "hostname": "host-a", "app_env": "production"}),
            encoding="utf-8",
        )

    report = build_verification_manifest.build_verification_manifest(
        run_id="run-1",
        log_dir=tmp_path,
        receipt_filenames=receipt_names,
    )

    assert report["ok"] is True
    assert report["run_id"] == "run-1"
    for name in receipt_names:
        assert report["receipts"][name]["sha256"] == hash_file_sha256(tmp_path / name)


def test_build_verification_manifest_flags_missing_or_mismatched_receipt(tmp_path):
    (tmp_path / "a.json").write_text(
        json.dumps({"ok": True, "run_id": "run-old", "hostname": "host-a", "app_env": "production"}),
        encoding="utf-8",
    )

    report = build_verification_manifest.build_verification_manifest(
        run_id="run-new",
        log_dir=tmp_path,
        receipt_filenames=["a.json", "missing.json"],
    )

    assert report["ok"] is False
    assert report["receipts"]["a.json"]["reason"] == "run_id_mismatch"
    assert report["receipts"]["missing.json"]["reason"] == "missing_receipt"
