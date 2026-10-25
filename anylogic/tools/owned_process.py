"""A Windows Job contains only this launch and kills descendants on owner exit."""
import ctypes
from ctypes import wintypes as w
import subprocess
import time


class ThreadEntry(ctypes.Structure):
    _fields_=[("size",w.DWORD),("usage",w.DWORD),("thread_id",w.DWORD),("owner_pid",w.DWORD),
              ("priority",w.LONG),("delta",w.LONG),("flags",w.DWORD)]


class Accounting(ctypes.Structure):
    _fields_=[(name,ctypes.c_longlong) for name in ("user","kernel","period_user","period_kernel")]+[
        (name,w.DWORD) for name in ("faults","total_processes","active_processes","terminated")]


def resume_primary(pid):
    """The only thread of a CREATE_SUSPENDED process cannot have spawned children."""
    k=ctypes.windll.kernel32
    k.CreateToolhelp32Snapshot.restype=w.HANDLE
    k.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD]
    k.Thread32First.argtypes=[w.HANDLE,ctypes.POINTER(ThreadEntry)]
    k.Thread32Next.argtypes=[w.HANDLE,ctypes.POINTER(ThreadEntry)]
    k.OpenThread.restype=w.HANDLE
    k.OpenThread.argtypes=[w.DWORD,w.BOOL,w.DWORD]
    k.ResumeThread.argtypes=[w.HANDLE]
    k.ResumeThread.restype=w.DWORD
    snapshot=k.CreateToolhelp32Snapshot(4,0)
    if snapshot==ctypes.c_void_p(-1).value:
        raise OSError("Cannot enumerate owned suspended thread")
    try:
        entry=ThreadEntry();entry.size=ctypes.sizeof(entry)
        more=k.Thread32First(snapshot,ctypes.byref(entry))
        while more:
            if entry.owner_pid==pid:
                thread=k.OpenThread(2,False,entry.thread_id)
                if not thread:
                    raise OSError("Cannot open owned suspended thread")
                try:
                    if k.ResumeThread(thread)!=1:
                        raise OSError("Unexpected suspended-thread resume count")
                finally:
                    k.CloseHandle(thread)
                return
            more=k.Thread32Next(snapshot,ctypes.byref(entry))
        raise OSError("Owned suspended thread not found")
    finally:
        k.CloseHandle(snapshot)


class BasicLimits(ctypes.Structure):
    _fields_=[("process_time",ctypes.c_longlong),("job_time",ctypes.c_longlong),
              ("flags",w.DWORD),("min_ws",ctypes.c_size_t),("max_ws",ctypes.c_size_t),
              ("active_limit",w.DWORD),("affinity",ctypes.c_size_t),
              ("priority",w.DWORD),("scheduling",w.DWORD)]


class IoCounters(ctypes.Structure):
    _fields_=[(name,ctypes.c_ulonglong) for name in ("read_ops","write_ops","other_ops","read_bytes","write_bytes","other_bytes")]


class ExtendedLimits(ctypes.Structure):
    _fields_=[("basic",BasicLimits),("io",IoCounters),("process_memory",ctypes.c_size_t),
              ("job_memory",ctypes.c_size_t),("peak_process_memory",ctypes.c_size_t),
              ("peak_job_memory",ctypes.c_size_t)]


class OwnedProcess:
    """No image-name kills, no PID reuse, no surviving delegated child processes."""
    def __init__(self,command,creationflags=0):
        kernel=ctypes.windll.kernel32
        kernel.CreateJobObjectW.restype=w.HANDLE
        kernel.CreateJobObjectW.argtypes=[w.LPVOID,w.LPCWSTR]
        kernel.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,w.LPVOID,w.DWORD]
        kernel.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE]
        kernel.TerminateJobObject.argtypes=[w.HANDLE,w.UINT]
        kernel.CloseHandle.argtypes=[w.HANDLE]
        self.job=kernel.CreateJobObjectW(None,None)
        if not self.job:
            raise OSError("Cannot create owned-process job")
        limits=ExtendedLimits()
        limits.basic.flags=0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(self.job,9,ctypes.byref(limits),ctypes.sizeof(limits)):
            kernel.CloseHandle(self.job)
            raise OSError("Cannot enforce owned-process cleanup")
        self.process=None
        try:
            self.process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                          creationflags=creationflags|0x4)  # CREATE_SUSPENDED
            if not kernel.AssignProcessToJobObject(self.job,int(self.process._handle)):
                raise OSError("Cannot attach native process to owned job")
            resume_primary(self.process.pid)
        except BaseException:
            if self.process is not None and self.process.poll() is None:
                subprocess.run(["taskkill","/PID",str(self.process.pid),"/T","/F"],capture_output=True)
                self.process.wait(timeout=10)
            kernel.CloseHandle(self.job)
            raise

    def close(self):
        kernel=ctypes.windll.kernel32
        try:
            if not kernel.TerminateJobObject(self.job,0):
                raise OSError("Owned native-process tree could not be terminated")
            deadline=time.monotonic()+10
            while self.active_processes():
                if time.monotonic()>deadline:
                    raise TimeoutError("Owned native descendants did not exit")
                time.sleep(.05)
            self.process.wait(timeout=10)
        finally:
            kernel.CloseHandle(self.job)
            self.job=None

    def active_processes(self):
        info=Accounting()
        k=ctypes.windll.kernel32
        k.QueryInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,w.LPVOID,w.DWORD,w.LPVOID]
        if not k.QueryInformationJobObject(self.job,1,ctypes.byref(info),ctypes.sizeof(info),None):
            raise OSError("Cannot verify owned process-tree state")
        return info.active_processes
