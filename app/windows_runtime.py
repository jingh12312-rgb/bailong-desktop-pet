"""Reject an inherited Low integrity token before starting desktop services."""
import sys


def integrity_rid():
    """Read this process's mandatory integrity label without changing its token."""
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    security = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    security.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                        ctypes.POINTER(wintypes.HANDLE)]
    security.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                            wintypes.LPVOID, wintypes.DWORD,
                                            ctypes.POINTER(wintypes.DWORD)]
    security.GetSidSubAuthorityCount.argtypes = [wintypes.LPVOID]
    security.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
    security.GetSidSubAuthority.argtypes = [wintypes.LPVOID, wintypes.DWORD]
    security.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)
    token = wintypes.HANDLE()
    if not security.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        size = wintypes.DWORD()
        security.GetTokenInformation(token, 25, None, 0, ctypes.byref(size))
        if not size.value:
            raise ctypes.WinError(ctypes.get_last_error())
        label = ctypes.create_string_buffer(size.value)
        if not security.GetTokenInformation(token, 25, label, size, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        sid = ctypes.cast(label, ctypes.POINTER(wintypes.LPVOID))[0]
        count = security.GetSidSubAuthorityCount(sid)[0]
        return security.GetSidSubAuthority(sid, count - 1)[0]
    finally:
        kernel.CloseHandle(token)


def require_desktop_integrity():
    if sys.platform == 'win32' and integrity_rid() < 0x2000:
        raise RuntimeError(
            '桌宠继承了启动程序的 Low（低完整性）权限，无法正常访问 Codex 数据。\n'
            '请关闭此启动方式，从 Windows 桌面或文件资源管理器双击桌宠启动入口。\n'
            '如果通过 DSH/Codex 启动，请先退出旧的受限后端，再重新启动桌宠。\n'
            '普通桌面权限即可，无需以管理员身份运行。')
