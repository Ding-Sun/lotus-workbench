"""Probe Explorer's integrity level (and ours) to explain mount failures."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

k = ctypes.WinDLL("kernel32", use_last_error=True)
adv = ctypes.WinDLL("advapi32", use_last_error=True)
u = ctypes.WinDLL("user32", use_last_error=True)

u.FindWindowW.restype = wintypes.HWND
u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k.OpenProcess.restype = wintypes.HANDLE
adv.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
adv.GetTokenInformation.argtypes = [
    wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)
]
adv.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ubyte)]
adv.GetSidSubAuthority.argtypes = [ctypes.c_void_p, wintypes.DWORD]


def integrity(pid: int) -> int | None:
    proc = k.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not proc:
        print(f"OpenProcess({pid}) failed: {ctypes.get_last_error()}")
        return None
    token = wintypes.HANDLE()
    if not adv.OpenProcessToken(proc, 0x0008, ctypes.byref(token)):  # TOKEN_QUERY
        print(f"OpenProcessToken({pid}) failed: {ctypes.get_last_error()}")
        return None
    size = wintypes.DWORD(0)
    adv.GetTokenInformation(token, 18, None, 0, ctypes.byref(size))
    buf = ctypes.create_string_buffer(size.value)
    if not adv.GetTokenInformation(token, 18, buf, size, ctypes.byref(size)):
        print("GetTokenInformation failed")
        return None
    sid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
    count = ctypes.c_ubyte(0)
    adv.GetSidSubAuthorityCount(sid, ctypes.byref(count))
    rid = adv.GetSidSubAuthority(sid, count.value - 1)
    return int(ctypes.cast(rid, ctypes.POINTER(ctypes.c_uint))[0])


prog = int(u.FindWindowW("Progman", None))
pid = wintypes.DWORD(0)
u.GetWindowThreadProcessId(wintypes.HWND(prog), ctypes.byref(pid))
print("progman", prog, "explorer pid", pid.value)
print("explorer integrity RID", integrity(pid.value))
print("self integrity RID", integrity(k.GetCurrentProcessId()))
print("(4096=Low 8192=Medium 12288=High 16384=System)")
