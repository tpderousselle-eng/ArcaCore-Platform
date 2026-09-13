"""Private process containment for the fixed public ArcaCore entrypoint."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

PROCESS_TIMEOUT = 60.0
MAX_OUTPUT_BYTES = 65_536


@dataclass(frozen=True)
class ProcessOutcome:
    started: bool
    diagnostic: str | None = None


class _WindowsJob:
    """Assign a suspended child to a kill-on-close job before any Python runs."""
    def __init__(self, process):
        import ctypes as c
        from ctypes import wintypes as w

        class Basic(c.Structure):
            _fields_ = [("user", c.c_longlong), ("job_user", c.c_longlong),
                ("flags", w.DWORD), ("minimum", c.c_size_t), ("maximum", c.c_size_t),
                ("processes", w.DWORD), ("affinity", c.c_size_t),
                ("priority", w.DWORD), ("scheduling", w.DWORD)]

        class Io(c.Structure):
            _fields_ = [(name, c.c_ulonglong) for name in
                ("reads", "writes", "other", "read_bytes", "write_bytes", "other_bytes")]

        class Extended(c.Structure):
            _fields_ = [("basic", Basic), ("io", Io), ("process_memory", c.c_size_t),
                ("job_memory", c.c_size_t), ("peak_process", c.c_size_t), ("peak_job", c.c_size_t)]

        class ThreadEntry(c.Structure):
            _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("thread", w.DWORD),
                ("owner", w.DWORD), ("base_priority", w.LONG), ("delta_priority", w.LONG), ("flags", w.DWORD)]

        kernel = c.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([c.c_void_p, w.LPCWSTR], w.HANDLE),
            "SetInformationJobObject": ([w.HANDLE, c.c_int, c.c_void_p, w.DWORD], w.BOOL),
            "AssignProcessToJobObject": ([w.HANDLE, w.HANDLE], w.BOOL),
            "OpenProcess": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            "CloseHandle": ([w.HANDLE], w.BOOL),
            "CreateToolhelp32Snapshot": ([w.DWORD, w.DWORD], w.HANDLE),
            "Thread32First": ([w.HANDLE, c.POINTER(ThreadEntry)], w.BOOL),
            "Thread32Next": ([w.HANDLE, c.POINTER(ThreadEntry)], w.BOOL),
            "OpenThread": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            "ResumeThread": ([w.HANDLE], w.DWORD),
        }
        for name, (args, result) in signatures.items():
            function = getattr(kernel, name); function.argtypes = args; function.restype = result
        self._kernel, self._handle = kernel, kernel.CreateJobObjectW(None, None)
        if not self._handle:
            raise OSError("Cannot create generator containment.")
        try:
            limits = Extended(); limits.basic.flags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel.SetInformationJobObject(self._handle, 9, c.byref(limits), c.sizeof(limits)):
                raise OSError("Cannot configure generator containment.")
            handle = kernel.OpenProcess(0x0101, False, process.pid)  # SET_QUOTA | TERMINATE
            if not handle:
                raise OSError("Cannot access suspended generator.")
            try:
                if not kernel.AssignProcessToJobObject(self._handle, handle):
                    raise OSError("Cannot contain suspended generator.")
            finally:
                kernel.CloseHandle(handle)
            snapshot = kernel.CreateToolhelp32Snapshot(4, 0)  # TH32CS_SNAPTHREAD
            if snapshot == c.c_void_p(-1).value:
                raise OSError("Cannot inspect suspended generator thread.")
            try:
                entry = ThreadEntry(); entry.size = c.sizeof(entry)
                found = kernel.Thread32First(snapshot, c.byref(entry))
                while found:
                    if entry.owner == process.pid:
                        thread = kernel.OpenThread(2, False, entry.thread)  # THREAD_SUSPEND_RESUME
                        if not thread:
                            raise OSError("Cannot resume contained generator.")
                        try:
                            if kernel.ResumeThread(thread) == 0xFFFFFFFF:
                                raise OSError("Cannot resume contained generator.")
                        finally:
                            kernel.CloseHandle(thread)
                        break
                    found = kernel.Thread32Next(snapshot, c.byref(entry))
                else:
                    raise OSError("Suspended generator thread is missing.")
            finally:
                kernel.CloseHandle(snapshot)
        except BaseException:
            self.close()
            raise

    def close(self):
        if getattr(self, "_handle", None):
            self._kernel.CloseHandle(self._handle)
            self._handle = None


class _OutputCounter:
    """Drain bounded chunks without retaining any subprocess text or secrets."""
    def __init__(self, stream):
        self.stream, self.count = stream, 0
        self.exceeded = threading.Event()
        self.thread = threading.Thread(target=self._drain, daemon=True)

    def _drain(self):
        while True:
            chunk = self.stream.read(8192)
            if not chunk:
                return
            self.count = min(MAX_OUTPUT_BYTES + 1, self.count + len(chunk))
            if self.count > MAX_OUTPUT_BYTES:
                self.exceeded.set()


def safe_environment(workspace: Path, runtime: Path):
    """No PATH, credentials, Python hooks or arbitrary environment inheritance."""
    result = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
    result.update({"PYTHONPATH": str(workspace), "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1", "PYTHONUTF8": "1", "HOME": str(runtime),
        "USERPROFILE": str(runtime), "LOCALAPPDATA": str(runtime),
        "TEMP": str(runtime), "TMP": str(runtime), "BLACK_CACHE_DIR": str(runtime / "black")})
    return result


def _run_process(command, workspace, runtime):
    """Internal transport; only invoke_module constructs production commands."""
    process = job = None
    captures = []
    diagnostic = None
    try:
        process = subprocess.Popen(command, cwd=workspace, env=safe_environment(workspace, runtime),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            shell=False, creationflags=(0x00000004 | subprocess.CREATE_NO_WINDOW) if os.name == "nt" else 0,
            start_new_session=os.name != "nt")
        if os.name == "nt":
            job = _WindowsJob(process)
        for stream in (process.stdout, process.stderr):
            capture = _OutputCounter(stream); captures.append(capture); capture.thread.start()
        deadline = time.monotonic() + PROCESS_TIMEOUT
        while process.poll() is None:
            if any(c.exceeded.is_set() for c in captures):
                diagnostic = "output_limit"; break
            if time.monotonic() >= deadline:
                diagnostic = "timeout"; break
            time.sleep(0.025)
        if diagnostic is None and process.returncode != 0:
            diagnostic = "nonzero_exit"
    except OSError:
        diagnostic = "process_setup"
    finally:
        # Terminate descendants even if their parent has already exited.
        if job is not None:
            job.close()
        if process is not None:
            if os.name != "nt":
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            for capture in captures:
                capture.thread.join(timeout=5)
                if capture.thread.is_alive():
                    diagnostic = "process_cleanup"
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
        if any(c.exceeded.is_set() for c in captures):
            diagnostic = "output_limit"
    return ProcessOutcome(process is not None, diagnostic)


def invoke_module(module, workspace, runtime):
    return _run_process([sys.executable, "-B", "-m", "tools.generate", module.module_name,
        *module.field_declarations, *module.constraint_declarations], workspace, runtime)
