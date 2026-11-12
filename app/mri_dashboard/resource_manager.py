"""Lightweight resource telemetry for MRI (no new dependency).

Samples the MRI process tree on Windows via the OS process table. Values that
cannot be measured are reported as UNKNOWN, never as zero.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TELEMETRY = ROOT / "data" / "runtime" / "resource_telemetry.jsonl"


def _powershell_process_table():
    """Reliable fallback when native PSAPI access is unavailable."""
    try:
        script = ("$p=Get-CimInstance Win32_Process | "
                  "Select-Object ProcessId,ParentProcessId,WorkingSetSize,Name; "
                  "$p | ConvertTo-Json -Compress")
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            stderr=subprocess.DEVNULL, timeout=10).decode("utf-8", "replace").strip()
        data = json.loads(out or "[]")
        return data if isinstance(data, list) else [data]
    except Exception:
        return None


def _powershell_tree(pid: int):
    rows = _powershell_process_table()
    if rows is None:
        return None
    by_parent = {}
    for row in rows:
        try:
            p = int(row.get("ProcessId")); parent = int(row.get("ParentProcessId"))
            ws = int(row.get("WorkingSetSize") or 0); name = str(row.get("Name") or "")
        except Exception:
            continue
        by_parent.setdefault(parent, []).append((p, name, ws))
    tree, stack = [], [pid]
    while stack:
        cur = stack.pop()
        for child in by_parent.get(cur, []):
            tree.append(child); stack.append(child[0])
    if not tree:
        return 0, 0, 0.0
    browsers = sum(1 for _, name, _ in tree
                   if any(x in name.lower() for x in ("chrome", "chromium", "msedge")))
    root_row = next((r for r in rows if int(r.get("ProcessId") or 0) == int(pid)), None)
    total = sum(ws for _, _, ws in tree)
    if root_row:
        total += int(root_row.get("WorkingSetSize") or 0)
    return len(tree) + (1 if root_row else 0), browsers, round(total / (1024 * 1024), 2)


def _powershell_rss(pid: int):
    rows = _powershell_process_table()
    if rows is None:
        return None
    for row in rows:
        try:
            if int(row.get("ProcessId")) == int(pid):
                return round(int(row.get("WorkingSetSize") or 0) / (1024 * 1024), 2)
        except Exception:
            continue
    return None


def _current_rss_mb():
    try:
        class PMC(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]
        counters = PMC(); counters.cb = ctypes.sizeof(PMC)
        h = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(counters), counters.cb):
            return round(counters.WorkingSetSize / (1024 * 1024), 2)
    except Exception:
        pass
    return _powershell_rss(os.getpid()) or "UNKNOWN"


def _available_memory_mb():
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MEMORYSTATUSEX(); m.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            return round(m.ullAvailPhys / (1024 * 1024), 2)
    except Exception:
        pass
    return "UNKNOWN"


def _proc_rss(pid: int):
    try:
        class PMC(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t),
                        ("PrivateUsage", ctypes.c_size_t)]
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return None
        try:
            m = PMC(); m.cb = ctypes.sizeof(PMC)
            if ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(m), m.cb):
                return round(m.WorkingSetSize / (1024 * 1024), 2)
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    except Exception:
        pass
    return None


def _native_process_tree(pid: int):
    try:
        TH32CS_SNAPPROCESS = 0x00000002
        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [("dwSize", ctypes.c_ulong), ("cntUsage", ctypes.c_ulong),
                        ("th32ProcessID", ctypes.c_ulong), ("th32DefaultHeapID", ctypes.c_void_p),
                        ("th32ModuleID", ctypes.c_ulong), ("cntThreads", ctypes.c_ulong),
                        ("th32ParentProcessID", ctypes.c_ulong),
                        ("pcPriClassBase", ctypes.c_long), ("dwFlags", ctypes.c_ulong),
                        ("szExeFile", ctypes.c_char * 260)]
        k32 = ctypes.windll.kernel32
        snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap == -1:
            return None
        entry = PROCESSENTRY32(); entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        rows = []
        try:
            ok = k32.Process32First(snap, ctypes.byref(entry))
            while ok:
                rows.append((int(entry.th32ProcessID), int(entry.th32ParentProcessID),
                             entry.szExeFile.decode("mbcs", "replace")))
                ok = k32.Process32Next(snap, ctypes.byref(entry))
        finally:
            k32.CloseHandle(snap)
        by_parent = {}
        for p, parent, name in rows:
            by_parent.setdefault(parent, []).append((p, name))
        tree, stack = [], [pid]
        while stack:
            cur = stack.pop()
            for child in by_parent.get(cur, []):
                tree.append(child); stack.append(child[0])
        if not tree:
            return 0, 0, 0.0
        browsers = sum(1 for _, name in tree
                       if any(x in name.lower() for x in ("chrome", "chromium", "msedge")))
        total = 0.0
        for child_pid, _ in tree:
            rss = _proc_rss(child_pid)
            if rss is not None:
                total += rss
        return len(tree), browsers, round(total, 2)
    except Exception:
        return None


def _process_tree(pid: int):
    """Return (process_count, browser_count, aggregate_rss_mb)."""
    native = _native_process_tree(pid)
    if native is not None and native[0] > 0 and native[2] not in (0, 0.0):
        return native
    ps = _powershell_tree(pid)
    if ps is not None:
        return ps
    if native is not None:
        return native
    try:
        out = subprocess.check_output(
            ["wmic", "process", "get", "ProcessId,ParentProcessId,WorkingSetSize,CommandLine", "/format:csv"],
            stderr=subprocess.DEVNULL, timeout=8).decode("utf-8", "replace")
    except Exception:
        return "UNKNOWN", "UNKNOWN", "UNKNOWN"
    rows = []
    for line in out.splitlines():
        line = line.strip()
        if not line or "," not in line or line.startswith("Node,"):
            continue
        parts = line.split(",")
        if len(parts) < 5:
            continue
        cmd = ",".join(parts[1:-3])
        try:
            parent = int(parts[-3]); ws = int(parts[-2]); p = int(parts[-1])
        except Exception:
            continue
        rows.append((p, parent, ws, cmd))
    by_parent = {}
    for p, parent, ws, cmd in rows:
        by_parent.setdefault(parent, []).append((p, parent, ws, cmd))
    tree, stack = [], [pid]
    while stack:
        cur = stack.pop()
        for child in by_parent.get(cur, []):
            tree.append(child); stack.append(child[0])
    if not tree:
        return 0, 0, 0.0
    browsers = sum(1 for p, parent, ws, cmd in tree
                   if any(x in (cmd or "").lower() for x in ("chrome", "chromium", "msedge")))
    rss = round(sum(ws for _, _, ws, _ in tree) / (1024 * 1024), 2)
    return len(tree), browsers, rss


class ResourceMonitor:
    def __init__(self, run_id, marketplace="UNKNOWN", interval=None):
        self.run_id = run_id
        self.marketplace = marketplace
        self.interval = float(interval if interval is not None
                              else os.environ.get("MRI_RESOURCE_SAMPLE_SECONDS", "15"))
        self.peak = 0.0
        self.samples = []
        self._stop = threading.Event()
        self._thread = None
        self.status = "UNKNOWN"

    def snapshot(self):
        py_rss = _current_rss_mb()
        count, browsers, tree_rss = _process_tree(os.getpid())
        if py_rss == "UNKNOWN" or tree_rss == "UNKNOWN":
            status = "UNKNOWN"
        elif count == 0:
            status = "PARTIAL"
        else:
            status = "OK"
        self.status = status
        item = {
            "run_id": self.run_id, "marketplace": self.marketplace,
            "timestamp": datetime.now().isoformat(),
            "python_rss_mb": py_rss,
            "browser_process_count": browsers,
            "browser_rss_mb": "UNKNOWN",
            "total_process_tree_rss_mb": tree_rss,
            "peak_process_tree_rss_mb": self.peak,
            "available_system_memory_mb": _available_memory_mb(),
            "active_browser_contexts": "UNKNOWN",
            "active_pages": "UNKNOWN",
            "measurement_status": status,
            "shared_memory_note": "RSS aggregate; shared pages may be double-counted",
        }
        if isinstance(tree_rss, (int, float)):
            self.peak = max(self.peak, float(tree_rss))
            item["peak_process_tree_rss_mb"] = round(self.peak, 2)
        self.samples.append(item)
        try:
            TELEMETRY.parent.mkdir(parents=True, exist_ok=True)
            with TELEMETRY.open("a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        except Exception:
            pass
        return item

    def start(self):
        self.snapshot()
        if self.interval > 0:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        return self

    def _loop(self):
        while not self._stop.wait(self.interval):
            self.snapshot()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        last = self.snapshot()
        last["measurement_status"] = self.status
        last["peak_process_tree_rss_mb"] = round(self.peak, 2)
        return last

    def summary(self):
        if not self.samples:
            return {"status": "UNKNOWN"}
        return {
            "status": self.status,
            "samples": len(self.samples),
            "peak_process_tree_rss_mb": round(self.peak, 2),
            "last": self.samples[-1],
            "telemetry_path": str(TELEMETRY),
        }
