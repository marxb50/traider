import pytest

from super_trader_quant.backend.app.services.process_lock import AlreadyRunningError, ProcessLock


def test_process_lock_blocks_second_holder(tmp_path):
    lock_path = tmp_path / "scheduler.lock"
    first = ProcessLock(lock_path).acquire()
    try:
        assert first.locked
        with pytest.raises(AlreadyRunningError):
            ProcessLock(lock_path).acquire()
    finally:
        first.release()

    second = ProcessLock(lock_path).acquire()
    try:
        assert second.locked
    finally:
        second.release()
