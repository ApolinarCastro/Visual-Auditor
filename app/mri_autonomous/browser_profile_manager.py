"""Single-owner browser profile locks (prevent TargetClosedError / stale Chrome)."""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

LOCK_NAME = ".mri_profile.lock"


def _pid_alive(pid: int) -> bool:
    try:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        try:
            os.kill(int(pid), 0)
            return True
        except OSError:
            return False


def profile_status(profile_path) -> dict:
    path = Path(profile_path)
    lock = path / LOCK_NAME
    out = {"path": str(path), "exists": path.exists(), "locked": False,
           "pid": None, "run_id": None, "stale": False}
    if not lock.exists():
        return out
    try:
        data = json.loads(lock.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    pid = data.get("pid")
    alive = bool(pid and _pid_alive(pid))
    out.update({"pid": pid, "run_id": data.get("run_id"),
                "locked": alive, "stale": not alive})
    if not alive:
        try:
            lock.unlink()
            out["cleaned_stale"] = True
        except Exception:
            pass
    return out


class ProfileLock:
    """Context manager: acquires one owner per persistent browser profile."""

    def __init__(self, profile_path, run_id=None):
        self.path = Path(profile_path)
        self.run_id = run_id or "run"
        self.token = uuid.uuid4().hex
        self.lock_file = self.path / LOCK_NAME

    def acquire(self):
        st = profile_status(self.path)
        if st.get("locked"):
            raise RuntimeError(
                f"PROFILE_LOCKED: {self.path} en uso por PID {st.get('pid')} "
                f"(run {st.get('run_id')})")
        self.path.mkdir(parents=True, exist_ok=True)
        payload = {"pid": os.getpid(), "token": self.token,
                   "run_id": self.run_id,
                   "started_at": datetime.now().isoformat()}
        tmp = self.lock_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, self.lock_file)
        return self

    def release(self):
        try:
            data = json.loads(self.lock_file.read_text(encoding="utf-8"))
            if data.get("token") == self.token:
                self.lock_file.unlink(missing_ok=True)
        except Exception:
            pass

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()
        return False
