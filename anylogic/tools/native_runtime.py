"""Exclusive native launch; only the owned process tree may be closed."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import hashlib
import os
import subprocess
import time
from pathlib import Path
from owned_process import OwnedProcess

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT.parent / ".anylogic-native.lock.json"
ANYLOGIC = Path("C:/Program Files/AnyLogic 8.9 Personal Learning Edition/AnyLogic.exe")


class NativeBusy(RuntimeError):
    """Another task owns the runtime; no launch took place."""


def validate_generated_classes(build):
    bad=[]
    for p in Path(build).rglob("*.class"):
        try:
            content=p.read_bytes()
        except FileNotFoundError:  # Eclipse replaces old class files while rebuilding
            continue
        if b"Unresolved compilation problem" in content:
            bad.append(p)
    if bad:
        raise RuntimeError("AnyLogic emitted compiler error stubs: "+", ".join(p.name for p in bad))


def alive(pid):
    ctypes.windll.kernel32.OpenProcess.restype = wintypes.HANDLE
    ctypes.windll.kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_ulong)]
    ctypes.windll.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return ctypes.windll.kernel32.GetLastError() != 87  # access denied is not proof of death
    code = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(handle)
    return code.value == 259


class NativeLease:
    def __enter__(self):
        kernel=ctypes.windll.kernel32
        kernel.CreateMutexW.restype=wintypes.HANDLE
        kernel.CreateMutexW.argtypes=[wintypes.LPVOID,wintypes.BOOL,wintypes.LPCWSTR]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        kernel.ReleaseMutex.argtypes=[wintypes.HANDLE]
        self.mutex=kernel.CreateMutexW(None,False,"Local\\TaimAnyLogicNative")
        if not self.mutex:
            raise OSError("Cannot create native-runtime mutex")
        if kernel.WaitForSingleObject(self.mutex,0) not in (0,128):
            kernel.CloseHandle(self.mutex)
            self.mutex=None
            raise NativeBusy("Another chat holds the native-runtime mutex")
        try:
            if LOCK.exists():
                previous=json.loads(LOCK.read_text(encoding="utf-8"))
                if alive(previous["owner_pid"]):
                    raise NativeBusy(f"Native runtime reserved: {previous}")
                LOCK.unlink()  # reclamation is serialized by the OS mutex
            with LOCK.open("x",encoding="utf-8") as out:
                json.dump({"owner_pid":os.getpid(),"project":str(ROOT),"created":time.time()},out)
            # Also check processes whose launchers do not implement the lease protocol.
            check=subprocess.run(["powershell","-NoProfile","-Command",
                                  "@(Get-Process AnyLogic -ErrorAction SilentlyContinue).Count"],
                                 capture_output=True,text=True,check=True)
            if check.stdout.strip()!="0":
                raise NativeBusy("Another AnyLogic process is active; leave it untouched.")
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_):
        try:
            if LOCK.exists() and json.loads(LOCK.read_text(encoding="utf-8"))["owner_pid"] == os.getpid():
                LOCK.unlink()
        finally:
            if self.mutex:
                ctypes.windll.kernel32.ReleaseMutex(self.mutex)
                ctypes.windll.kernel32.CloseHandle(self.mutex)
                self.mutex=None


def launch(alp, experiment, logs, expected, timeout=720, keep_seconds=0):
    """P2_DONE, not process exit, proves completion. Existing logs must be separate."""
    alp, logs = Path(alp).resolve(), Path(logs).resolve()
    logs.mkdir(parents=True, exist_ok=True)
    if list(logs.glob("*.log")):
        raise ValueError("Choose a fresh log directory; old logs cannot prove a new run completed.")
    alp_hash=hashlib.sha256(alp.read_bytes()).hexdigest()  # validate before starting AnyLogic
    with NativeLease():
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        workspace = ROOT / "tools/.build/isolated-workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        owned=OwnedProcess([str(ANYLOGIC),"-data",str(workspace),"-r",str(alp),experiment],creationflags)
        proc=owned.process
        manifest = {"owner_pid": os.getpid(), "anylogic_pid": proc.pid, "alp": str(alp),
                    "alp_sha256": alp_hash,
                    "experiment": experiment, "expected": expected, "started": time.time()}
        started, last_count = time.monotonic(), -1
        try:
            (logs / "launch.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            while time.monotonic() - started < timeout:
                validate_generated_classes(workspace/(alp.stem+"_BUILD")/"classes")
                errors = list(logs.glob("p2-error-*.log"))
                if errors:
                    raise RuntimeError("Native error: " + errors[0].read_text(encoding="utf-8"))
                completed = [p for p in logs.glob("p2-store*.log")
                             if "P2_DONE," in p.read_text(encoding="utf-8")]
                if len(completed) != last_count:
                    print(f"Native {experiment}: {len(completed)}/{expected}, {time.monotonic()-started:.0f}s", flush=True)
                    last_count = len(completed)
                if len(completed) >= expected:
                    if keep_seconds:
                        time.sleep(keep_seconds)
                    manifest.update(completed=len(completed), seconds=round(time.monotonic()-started, 2), status="complete")
                    return manifest
                if proc.poll() is not None:
                    # Eclipse launchers can delegate; completion still must be observed.
                    manifest["launcher_exit_code"] = proc.returncode
                time.sleep(2)
            raise TimeoutError(f"Native {experiment}: {last_count}/{expected} logs after {timeout}s")
        finally:
            # Never kill by image name: P3 may have started since this launch.
            try:
                owned.close()
                manifest["cleanup"]="owned process job terminated"
            except BaseException as error:
                manifest["status"]="cleanup_failed"
                manifest["cleanup_error"]=str(error)
                raise
            finally:
                manifest.setdefault("status","incomplete")
                (logs/"launch.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("alp", type=Path)
    cli.add_argument("--experiment", default="Simulation")
    cli.add_argument("--logs", type=Path, required=True)
    cli.add_argument("--expected", type=int, default=1)
    cli.add_argument("--timeout", type=int, default=720)
    cli.add_argument("--wait-seconds",type=int,default=0,help="Wait for another chat to release the runtime")
    args = cli.parse_args()
    deadline=time.monotonic()+args.wait_seconds
    announced=False
    while True:
        try:
            print(json.dumps(launch(args.alp,args.experiment,args.logs,args.expected,args.timeout),indent=2))
            break
        except NativeBusy:
            if time.monotonic()>=deadline:
                raise
            if not announced:
                print("Waiting for the other chat to release AnyLogic; no process touched.",flush=True)
                announced=True
            time.sleep(5)
