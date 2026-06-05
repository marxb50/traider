from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import TextIO


class AlreadyRunningError(RuntimeError):
    """Raised when another process already holds the same lock file."""


class ProcessLock:
    """Small cross-platform exclusive process lock.

    The lock is advisory on Linux/macOS and region-based on Windows. In both
    cases the operating system releases it if the process exits unexpectedly,
    which makes it safer than a plain PID file for the 24/7 scheduler.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._file: TextIO | None = None

    def acquire(self) -> "ProcessLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            self._lock_handle(handle)
        except OSError as exc:
            handle.close()
            raise AlreadyRunningError(f"Já existe um processo segurando a trava: {self.path}") from exc

        self._file = handle
        self._write_owner_metadata()
        return self

    def release(self) -> None:
        if self._file is None:
            return
        try:
            self._unlock_handle(self._file)
        finally:
            self._file.close()
            self._file = None

    @property
    def locked(self) -> bool:
        return self._file is not None

    def __enter__(self) -> "ProcessLock":
        return self.acquire()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

    def _write_owner_metadata(self) -> None:
        assert self._file is not None
        self._file.seek(0)
        self._file.truncate()
        self._file.write(f"pid={os.getpid()}\nhost={platform.node()}\n")
        self._file.flush()

    @staticmethod
    def _lock_handle(handle: TextIO) -> None:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            if not handle.read(1):
                handle.write("\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return

        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _unlock_handle(handle: TextIO) -> None:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            return

        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
