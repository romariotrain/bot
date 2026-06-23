"""
WIN_PROCESS — привязка к чужому процессу (Windows-only).

Воспроизводит три шага из follow.exe:
  A. enable_debug_privilege()   — FUN_14000b480: включить SeDebugPrivilege
  B. find_pid_any(names)        — FUN_14000b3b0: снапшот TH32CS_SNAPPROCESS
  C. open_and_verify(pid)       — OpenProcess(ALL_ACCESS) + QueryFullProcessImageNameW

Итоговый вызов (с retry-loop как в оригинале):
    handle, path = attach_game(timeout_s=30)
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time

# ---------------------------------------------------------------- WinAPI
kernel32 = ctypes.windll.kernel32
advapi32 = ctypes.windll.advapi32

# Константы
TH32CS_SNAPPROCESS      = 0x00000002
PROCESS_ALL_ACCESS      = 0x001FFFFF
PROCESS_QUERY_LIMITED   = 0x00001000
TOKEN_ADJUST_PRIVILEGES = 0x0020
TOKEN_QUERY             = 0x0008
SE_PRIVILEGE_ENABLED    = 0x00000002

# Три имени экзешника, в том же порядке что в follow.exe
POE_EXE_NAMES = (
    "PathOfExile.exe",
    "PathOfExileSteam.exe",
    "PathOfExile_x64.exe",
)


# ---------------------------------------------------------------- структуры

class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize",              wt.DWORD),
        ("cntUsage",            wt.DWORD),
        ("th32ProcessID",       wt.DWORD),
        ("th32DefaultHeapID",   ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID",        wt.DWORD),
        ("cntThreads",          wt.DWORD),
        ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase",      ctypes.c_long),
        ("dwFlags",             wt.DWORD),
        ("szExeFile",           ctypes.c_wchar * 260),
    ]


class LUID(ctypes.Structure):
    _fields_ = [("LowPart", wt.DWORD), ("HighPart", wt.LONG)]


class LUID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Luid", LUID), ("Attributes", wt.DWORD)]


class TOKEN_PRIVILEGES(ctypes.Structure):
    _fields_ = [
        ("PrivilegeCount", wt.DWORD),
        ("Privileges",     LUID_AND_ATTRIBUTES * 1),
    ]


# ---------------------------------------------------------------- шаг A

def enable_debug_privilege() -> None:
    """Включить SeDebugPrivilege для текущего процесса.

    Без этого OpenProcess(PROCESS_ALL_ACCESS) на защищённые процессы
    вернёт ERROR_ACCESS_DENIED (5).
    Требует запуска от имени Администратора."""
    h_token = wt.HANDLE()
    h_proc  = kernel32.GetCurrentProcess()

    ok = advapi32.OpenProcessToken(
        h_proc,
        TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY,
        ctypes.byref(h_token),
    )
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())

    luid = LUID()
    ok = advapi32.LookupPrivilegeValueW(None, "SeDebugPrivilege", ctypes.byref(luid))
    if not ok:
        kernel32.CloseHandle(h_token)
        raise ctypes.WinError(ctypes.get_last_error())

    tp = TOKEN_PRIVILEGES()
    tp.PrivilegeCount = 1
    tp.Privileges[0].Luid       = luid
    tp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED

    ok = advapi32.AdjustTokenPrivileges(
        h_token, False, ctypes.byref(tp),
        ctypes.sizeof(tp), None, None,
    )
    kernel32.CloseHandle(h_token)

    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())


# ---------------------------------------------------------------- шаг B

def find_pid(exe_name: str) -> int:
    """Вернуть PID процесса по имени exe (без пути, без учёта регистра).

    Raises ProcessLookupError если процесс не найден."""
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == wt.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())

    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)

    target = exe_name.lower()
    try:
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() == target:
                return entry.th32ProcessID
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)

    raise ProcessLookupError(f"{exe_name!r} not found in process list")


def find_pid_any(
    exe_names: tuple[str, ...] = POE_EXE_NAMES,
    extra: str | None = None,
) -> tuple[int, str]:
    """Перебрать несколько имён exe и вернуть первый найденный (pid, matched_name).

    Порядок: POE_EXE_NAMES + optional extra — как в follow.exe FUN_140012380."""
    candidates = list(exe_names)
    if extra:
        candidates.append(extra)

    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == wt.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())

    targets = {n.lower(): n for n in candidates}
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)

    try:
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            key = entry.szExeFile.lower()
            if key in targets:
                return entry.th32ProcessID, targets[key]
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)

    raise ProcessLookupError(f"None of {candidates} found in process list")


# ---------------------------------------------------------------- шаг C

def open_and_verify(pid: int) -> tuple[wt.HANDLE, str]:
    """Открыть процесс с PROCESS_ALL_ACCESS и подтвердить полный путь к exe.

    Возвращает (handle, full_path).
    Caller закрывает handle через CloseHandle."""
    handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())

    buf  = ctypes.create_unicode_buffer(1024)
    size = wt.DWORD(1024)
    ok   = kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
    if not ok:
        kernel32.CloseHandle(handle)
        raise ctypes.WinError(ctypes.get_last_error())

    return handle, buf.value


# ---------------------------------------------------------------- convenience

def attach(exe_name: str) -> tuple[wt.HANDLE, str]:
    """Однократный аттач по конкретному имени: SeDebugPrivilege → PID → handle."""
    enable_debug_privilege()
    pid = find_pid(exe_name)
    return open_and_verify(pid)


def attach_game(
    timeout_s: float = 30.0,
    poll_ms: int = 10,
    extra_exe: str | None = None,
) -> tuple[wt.HANDLE, str]:
    """Retry-loop: ждёт появления игры до timeout_s секунд.

    Перебирает PathOfExile.exe → PathOfExileSteam.exe → PathOfExile_x64.exe
    + опциональный extra_exe (как в follow.exe FUN_140012380).
    Возвращает (handle, full_path) первого найденного."""
    enable_debug_privilege()
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            pid, matched = find_pid_any(extra=extra_exe)
            return open_and_verify(pid)
        except ProcessLookupError:
            pass

        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Game process not found within {timeout_s}s "
                f"(tried: {list(POE_EXE_NAMES)})"
            )
        kernel32.Sleep(poll_ms)


# ---------------------------------------------------------------- самотест

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        # явное имя — однократный аттач
        name = sys.argv[1]
        try:
            h, full = attach(name)
            print(f"OK  {full}")
            kernel32.CloseHandle(h)
        except (ProcessLookupError, OSError) as e:
            print(f"FAIL: {e}")
    else:
        # режим по умолчанию — ждём игру 5 секунд
        print(f"Waiting for game (tries: {POE_EXE_NAMES}) ...")
        try:
            h, full = attach_game(timeout_s=5)
            print(f"OK  {full}")
            kernel32.CloseHandle(h)
        except TimeoutError as e:
            print(f"NOT FOUND: {e}")
        except OSError as e:
            print(f"WinError: {e}")
