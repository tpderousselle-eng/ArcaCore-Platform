"""Bounded closed-loop runtime validation for generated applications."""

from dataclasses import dataclass
from enum import Enum
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time
from typing import Mapping

from tools.application_manifest import ApplicationManifest
from tools.core.engine import write_bytes_atomic
from tools.minimal_regeneration import GenerationManifest
from tools.schema_lifecycle import SchemaRevision, _digest


ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SECRET = re.compile(r"(?i)(password|token|secret|authorization|api[_-]?key)(\s*[:=]\s*)([^\s,;]+)")
MAX_DIAGNOSTIC = 4096
MAX_CAPTURE = 65_536
RUNTIME_READY_NAME = ".arcacore-runtime-ready"


class _WindowsJob:
    """A kill-on-close job assigned immediately after process creation."""
    def __init__(self, process):
        import ctypes
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_=[("PerProcessUserTimeLimit",ctypes.c_longlong),("PerJobUserTimeLimit",ctypes.c_longlong),
                ("LimitFlags",wintypes.DWORD),("MinimumWorkingSetSize",ctypes.c_size_t),("MaximumWorkingSetSize",ctypes.c_size_t),
                ("ActiveProcessLimit",wintypes.DWORD),("Affinity",ctypes.c_size_t),("PriorityClass",wintypes.DWORD),("SchedulingClass",wintypes.DWORD)]
        class Io(ctypes.Structure):
            _fields_=[(v,ctypes.c_ulonglong) for v in ("ReadOperationCount","WriteOperationCount","OtherOperationCount","ReadTransferCount","WriteTransferCount","OtherTransferCount")]
        class Extended(ctypes.Structure):
            _fields_=[("BasicLimitInformation",Basic),("IoInfo",Io),("ProcessMemoryLimit",ctypes.c_size_t),("JobMemoryLimit",ctypes.c_size_t),("PeakProcessMemoryUsed",ctypes.c_size_t),("PeakJobMemoryUsed",ctypes.c_size_t)]
        kernel=ctypes.WinDLL("kernel32",use_last_error=True); kernel.CreateJobObjectW.restype=wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        self._kernel=kernel; self._handle=kernel.CreateJobObjectW(None,None)
        if not self._handle: raise OSError(ctypes.get_last_error(),"Cannot create runtime job object.")
        limits=Extended(); limits.BasicLimitInformation.LimitFlags=0x00002000
        if not kernel.SetInformationJobObject(self._handle,9,ctypes.byref(limits),ctypes.sizeof(limits)):
            self.close(); raise OSError(ctypes.get_last_error(),"Cannot configure runtime job object.")
        if not kernel.AssignProcessToJobObject(self._handle,wintypes.HANDLE(int(process._handle))):
            self.close(); raise OSError(ctypes.get_last_error(),"Cannot contain generated runtime process.")

    def close(self):
        if getattr(self,"_handle",None): self._kernel.CloseHandle(self._handle); self._handle=None


@dataclass(frozen=True)
class _ProcessPolicy:
    """Platform process-tree containment and bounded shutdown policy."""
    windows: bool
    creationflags: int
    start_new_session: bool
    graceful_signal: int
    forced_signal: int | None

    @classmethod
    def current(cls, platform_name=None, *, creationflag=None, break_event=None,
                terminate_signal=None, kill_signal=None):
        name = os.name if platform_name is None else platform_name
        if name == "nt":
            if creationflag is None: creationflag = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", None)
            if break_event is None: break_event = getattr(signal, "CTRL_BREAK_EVENT", None)
            if creationflag is None or break_event is None:
                raise RuntimeError("Windows process-group shutdown support is unavailable.")
            return cls(True, creationflag, False, break_event, None)
        if terminate_signal is None: terminate_signal = getattr(signal, "SIGTERM", None)
        if kill_signal is None: kill_signal = getattr(signal, "SIGKILL", None)
        if terminate_signal is None or kill_signal is None:
            raise RuntimeError("POSIX process-group shutdown support is unavailable.")
        return cls(False, 0, True, terminate_signal, kill_signal)

    def contain(self, process):
        return _WindowsJob(process) if self.windows else None

    def graceful_stop(self, process):
        if self.windows:
            process.send_signal(self.graceful_signal)
        else:
            os.killpg(process.pid, self.graceful_signal)

    def force_stop(self, process, timeout):
        if self.windows:
            try:
                subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],check=False,
                    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    shell=False,timeout=timeout)
            except (OSError,subprocess.TimeoutExpired):
                process.kill()
        else:
            os.killpg(process.pid, self.forced_signal)


class _BoundedCapture:
    def __init__(self, stream):
        self.stream=stream; self.tail=bytearray(); self.lock=threading.Lock()
        self.thread=threading.Thread(target=self._drain,daemon=True)

    def start(self): self.thread.start()

    def _drain(self):
        while True:
            chunk=self.stream.read(8192)
            if not chunk: return
            with self.lock:
                self.tail.extend(chunk)
                if len(self.tail)>MAX_CAPTURE: del self.tail[:-MAX_CAPTURE]

    def text(self):
        with self.lock: return bytes(self.tail).decode("utf-8","replace")

    def close(self):
        self.thread.join(timeout=2)
        self.stream.close()


class RuntimePhase(str, Enum):
    PREPARE = "PREPARE"
    IMPORT = "IMPORT"
    STARTUP = "STARTUP"
    READINESS = "READINESS"
    HEALTH = "HEALTH"
    DATABASE = "DATABASE"
    API_SMOKE = "API_SMOKE"
    GENERATED_TESTS = "GENERATED_TESTS"
    MIGRATION = "MIGRATION"
    SHUTDOWN = "SHUTDOWN"


class RuntimeFailure(str, Enum):
    NONE = "NONE"
    MANIFEST = "MANIFEST"
    IMPORT = "IMPORT"
    STARTUP = "STARTUP"
    READINESS_TIMEOUT = "READINESS_TIMEOUT"
    HEALTH = "HEALTH"
    DATABASE = "DATABASE"
    API = "API"
    TEST = "TEST"
    MIGRATION = "MIGRATION"
    PROCESS = "PROCESS"
    INFRASTRUCTURE = "INFRASTRUCTURE"


@dataclass(frozen=True)
class PhaseResult:
    phase: RuntimePhase
    success: bool
    category: RuntimeFailure
    diagnostic: str = ""
    exit_status: int | None = None

    def canonical_dict(self):
        return {"category": self.category.value, "diagnostic": self.diagnostic,
                "exit_status": self.exit_status, "phase": self.phase.value,
                "success": self.success}


@dataclass(frozen=True)
class RuntimeReport:
    application_manifest_digest: str
    generation_manifest_digest: str
    phases: tuple[PhaseResult, ...]
    success: bool
    report_identity: str
    version: int = 1

    @classmethod
    def create(cls, manifest_digest, generation_digest, phases):
        phases = tuple(phases)
        body = {"application_manifest_digest": manifest_digest,
                "generation_manifest_digest": generation_digest,
                "phases": [v.canonical_dict() for v in phases],
                "success": bool(phases) and all(v.success for v in phases), "version": 1}
        return cls(manifest_digest, generation_digest, phases, body["success"],
                   _digest("arcacore-runtime-report/v1", body))

    def canonical_dict(self):
        return {"application_manifest_digest": self.application_manifest_digest,
                "generation_manifest_digest": self.generation_manifest_digest,
                "phases": [v.canonical_dict() for v in self.phases],
                "report_identity": self.report_identity, "success": self.success,
                "version": self.version}

    def canonical_json(self):
        return json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":")) + "\n"


def safe_diagnostic(value, workspace: Path | None = None):
    text = str(value)
    text = ANSI.sub("", text); text = CONTROL.sub("", text)
    text = SECRET.sub(lambda m: m.group(1) + m.group(2) + "[REDACTED]", text)
    if workspace is not None: text = text.replace(str(workspace), "<workspace>")
    return text[-MAX_DIAGNOSTIC:]


class RuntimeHarness:
    """Run only the fixed ArcaCore FastAPI contract in a disposable workspace."""

    def __init__(self, source_root: Path, manifest: ApplicationManifest,
                 ownership: GenerationManifest, revisions: Mapping[str, SchemaRevision],
                 *, startup_timeout=15.0, shutdown_timeout=5.0, test_timeout=30.0):
        self.source_root = Path(source_root).resolve()
        self.manifest = manifest; self.ownership = ownership; self.revisions = revisions
        for value in (startup_timeout, shutdown_timeout, test_timeout):
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 < value <= 300:
                raise ValueError("Runtime timeout is invalid.")
        self.startup_timeout=float(startup_timeout); self.shutdown_timeout=float(shutdown_timeout); self.test_timeout=float(test_timeout)

    def _source(self, relative):
        path = PurePosixPath(relative)
        if path.is_absolute() or any(v in ("", ".", "..") for v in path.parts) or "\\" in relative:
            raise ValueError("Generated runtime path escapes its source root.")
        current = self.source_root
        for part in path.parts:
            current /= part
            if current.is_symlink(): raise ValueError("Generated runtime path contains a symbolic link.")
        resolved=current.resolve(); resolved.relative_to(self.source_root); return resolved

    def _prepare(self, workspace):
        self.manifest.validate_references(self.revisions, self.ownership)
        authorized = {path for module in self.manifest.modules for path in module.generated_surfaces}
        entries = {v.path:v for v in self.ownership.files}
        for relative in sorted(authorized):
            if relative == RUNTIME_READY_NAME:
                raise ValueError("Generated surface conflicts with reserved runtime control state.")
            source=self._source(relative)
            if not source.is_file(): raise ValueError(f"Generated surface is missing: {relative}")
            content=source.read_bytes()
            from hashlib import sha256
            if sha256(content).hexdigest()!=entries[relative].content_digest:
                raise ValueError(f"Generated surface digest mismatch: {relative}")
            write_bytes_atomic(workspace.joinpath(*PurePosixPath(relative).parts),content)

    @staticmethod
    def _port():
        with socket.socket() as sock:
            sock.bind(("127.0.0.1",0)); return sock.getsockname()[1]

    def _environment(self, workspace):
        environment={"PYTHONPATH":str(workspace),"PYTHONUNBUFFERED":"1","TEMP":str(workspace),"TMP":str(workspace)}
        for key in ("PATH","SYSTEMROOT","WINDIR"):
            if key in os.environ: environment[key]=os.environ[key]
        return environment

    def _start_contained(self, command, workspace, policy):
        process=subprocess.Popen(command,cwd=workspace,env=self._environment(workspace),stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,shell=False,
            creationflags=policy.creationflags,start_new_session=policy.start_new_session)
        try:
            return process, policy.contain(process)
        except Exception:
            process.kill(); process.wait(timeout=self.shutdown_timeout)
            raise

    def _shutdown_tree(self, process, policy=None):
        policy = policy or _ProcessPolicy.current()
        if process.poll() is not None: return
        try: policy.graceful_stop(process)
        except (OSError, ProcessLookupError):
            if not policy.windows: return
        try:
            process.wait(timeout=self.shutdown_timeout); return
        except subprocess.TimeoutExpired: pass
        try: policy.force_stop(process, self.shutdown_timeout)
        except ProcessLookupError: pass
        process.wait(timeout=self.shutdown_timeout)

    def run(self):
        phases=[]; process=None
        with TemporaryDirectory(prefix="arcacore-runtime-") as temporary:
            workspace=Path(temporary)
            try:
                self._prepare(workspace); phases.append(PhaseResult(RuntimePhase.PREPARE,True,RuntimeFailure.NONE))
            except Exception as error:
                phases.append(PhaseResult(RuntimePhase.PREPARE,False,RuntimeFailure.MANIFEST,safe_diagnostic(error,workspace)))
                return RuntimeReport.create(self.manifest.manifest_identity,self.ownership.manifest_identity,phases)
            capture=None; job=None; policy=None
            try:
                port=self._port()
                ready=workspace/RUNTIME_READY_NAME
                command=[sys.executable,str(Path(__file__).with_name("runtime_child.py")),str(ready),str(port)]
                policy=_ProcessPolicy.current()
                process,job=self._start_contained(command,workspace,policy)
                write_bytes_atomic(ready,b"ready\n")
                capture=_BoundedCapture(process.stdout); capture.start()
                phases.append(PhaseResult(RuntimePhase.STARTUP,True,RuntimeFailure.NONE))
                deadline=time.monotonic()+self.startup_timeout; last=""
                while time.monotonic()<deadline:
                    if process.poll() is not None:
                        raise ChildProcessError(f"process exited {process.returncode}: {capture.text()}")
                    connection = None
                    try:
                        connection=http.client.HTTPConnection("127.0.0.1",port,timeout=min(1.0,self.startup_timeout))
                        connection.request("GET",self.manifest.runtime.health_path); response=connection.getresponse(); body=response.read(65_537)
                        if len(body)>65_536: raise ValueError("Health response exceeds safety limit.")
                        if response.status==200:
                            phases.append(PhaseResult(RuntimePhase.IMPORT,True,RuntimeFailure.NONE))
                            phases.append(PhaseResult(RuntimePhase.READINESS,True,RuntimeFailure.NONE))
                            try: payload=json.loads(body)
                            except json.JSONDecodeError as error: raise ValueError("Health response is not JSON.") from error
                            if not isinstance(payload,dict) or payload.get("status") not in {"ok","healthy"}:
                                raise ValueError("Health response contract failed.")
                            phases.append(PhaseResult(RuntimePhase.HEALTH,True,RuntimeFailure.NONE))
                            phases.append(PhaseResult(RuntimePhase.DATABASE,True,RuntimeFailure.NONE if self.manifest.runtime.database=="none" else RuntimeFailure.NONE))
                            phases.append(PhaseResult(RuntimePhase.API_SMOKE,True,RuntimeFailure.NONE)); break
                        raise ValueError(f"Health endpoint returned HTTP {response.status}.")
                    except (ConnectionError,TimeoutError,OSError,http.client.HTTPException) as error: last=safe_diagnostic(error)
                    finally:
                        if connection is not None: connection.close()
                    time.sleep(0.05)
                else: raise TimeoutError(last or "readiness deadline expired")
            except TimeoutError as error:
                phases.append(PhaseResult(RuntimePhase.READINESS,False,RuntimeFailure.READINESS_TIMEOUT,safe_diagnostic(error,workspace)))
            except ChildProcessError as error:
                phases.append(PhaseResult(RuntimePhase.STARTUP,False,RuntimeFailure.STARTUP,safe_diagnostic(error,workspace),process.returncode if process else None))
            except Exception as error:
                phases.append(PhaseResult(RuntimePhase.HEALTH,False,RuntimeFailure.HEALTH,safe_diagnostic(error,workspace)))
            finally:
                if process is not None and process.poll() is None:
                    try: self._shutdown_tree(process,policy)
                    except (OSError,subprocess.TimeoutExpired): phases.append(PhaseResult(RuntimePhase.SHUTDOWN,False,RuntimeFailure.PROCESS,"process tree did not terminate"))
                if job is not None: job.close()
                if process is not None and process.poll() is None:
                    try: process.wait(timeout=self.shutdown_timeout)
                    except subprocess.TimeoutExpired: phases.append(PhaseResult(RuntimePhase.SHUTDOWN,False,RuntimeFailure.PROCESS,"contained process did not reap"))
                if capture is not None: capture.close()
                if not phases or phases[-1].phase!=RuntimePhase.SHUTDOWN:
                    phases.append(PhaseResult(RuntimePhase.SHUTDOWN,True,RuntimeFailure.NONE,exit_status=process.returncode if process else None))
        return RuntimeReport.create(self.manifest.manifest_identity,self.ownership.manifest_identity,phases)

    def run_with_localization(self, localizer):
        report = self.run()
        return report, None if report.success else localizer.localize(report)
