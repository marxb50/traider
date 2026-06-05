import json

from scripts.receipt_utils import write_json_receipt


def test_write_json_receipt_writes_complete_json_atomically(tmp_path):
    target = tmp_path / "receipt.json"

    write_json_receipt(target, {"ok": True, "value": 123})

    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True, "value": 123}
    temp_files = list(tmp_path.glob(".receipt.json.*.tmp"))
    assert temp_files == []
