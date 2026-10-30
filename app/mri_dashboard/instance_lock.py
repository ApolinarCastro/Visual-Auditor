"""Single-instance lock for the MRI server.

The lock is PID-aware: stale locks from dead processes are removed, while a
live owner yields a clear error with PID/build instead of silently starting a
second server on the same port.
"""
from __future__ import annotations

import atexit
import json
import os
import socket
import uuid
from datetime import datetime
from pathlib import Path


def _runtime_dir() -> Path:
    root = Path(__file__).resolve().parents[2]
    path = root / "data" / "runtime_tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _pid_alive(pid: int) -> bool:
    try:
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
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


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, int(port))) == 0


class InstanceLock:
    def __init__(self, port: int = 8055, build_id: str = "unknown"):
        self.port = int(port)
        self.build_id = build_id
        self.token = uuid.uuid4().hex
        self.path = _runtime_dir() / f"mri_instance_{self.port}.lock"
        self.held = False

    def acquire(self) -> tuple[bool, dict]:
        if self.path.exists():
            try:
                info = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                info = {}
            pid = int(info.get("pid") or 0)
            if pid and _pid_alive(pid):
                return False, {"reason": "INSTANCE_ALREADY_RUNNING", **info}
            try:
                self.path.unlink()
            except OSError:
                return False, {"reason": "STALE_LOCK_UNREMOVABLE",
                               "path": str(self.path)}
        if port_in_use(self.port):
            return False, {"reason": "PORT_IN_USE", "port": self.port}
        payload = {
            "pid": os.getpid(),
            "token": self.token,
            "port": self.port,
            "build_id": self.build_id,
            "started_at": datetime.now().isoformat(),
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, self.path)
        self.held = True
        atexit.register(self.release)
        return True, payload

    def release(self) -> None:
        if not self.held:
            return
        try:
            info = json.loads(self.path.read_text(encoding="utf-8"))
            if info.get("token") == self.token:
                self.path.unlink(missing_ok=True)
        except Exception:
            pass
        self.held = False
