"""Read foreground fullscreen state without hooks or stealing focus."""
import os
import sys


def covers_monitor(window, monitor, tolerance=2):
    return (window[0] <= monitor[0]+tolerance and window[1] <= monitor[1]+tolerance
            and window[2] >= monitor[2]-tolerance and window[3] >= monitor[3]-tolerance)


class FullscreenDetector:
    def __init__(self):
        self.user32 = None
        if sys.platform != 'win32':
            return
        import ctypes
        from ctypes import wintypes as w
        self.ctypes, self.w = ctypes, w
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        u = self.user32
        u.GetForegroundWindow.restype = w.HWND
        u.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
        u.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
        u.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
        u.IsWindowVisible.argtypes = [w.HWND]
        u.IsIconic.argtypes = [w.HWND]
        u.MonitorFromWindow.argtypes = [w.HWND, w.DWORD]
        u.MonitorFromWindow.restype = w.HANDLE
        class MonitorInfo(ctypes.Structure):
            _fields_ = [('cbSize', w.DWORD), ('rcMonitor', w.RECT), ('rcWork', w.RECT), ('dwFlags', w.DWORD)]
        self.MonitorInfo = MonitorInfo
        u.GetMonitorInfoW.argtypes = [w.HANDLE, ctypes.POINTER(MonitorInfo)]

    def active(self):
        if sys.platform=='darwin':
            from platform_support import mac_fullscreen
            return mac_fullscreen()
        if self.user32 is None:
            return False
        c, w, u = self.ctypes, self.w, self.user32
        hwnd = u.GetForegroundWindow()
        if not hwnd or not u.IsWindowVisible(hwnd) or u.IsIconic(hwnd):
            return False
        pid = w.DWORD()
        u.GetWindowThreadProcessId(hwnd, c.byref(pid))
        if pid.value == os.getpid():
            return False
        name = c.create_unicode_buffer(256)
        u.GetClassNameW(hwnd, name, len(name))
        if name.value in ('Progman', 'WorkerW', 'Shell_TrayWnd', 'Shell_SecondaryTrayWnd'):
            return False
        rect, info = w.RECT(), self.MonitorInfo()
        info.cbSize = c.sizeof(info)
        if not u.GetWindowRect(hwnd, c.byref(rect)) or not u.GetMonitorInfoW(u.MonitorFromWindow(hwnd, 2), c.byref(info)):
            return False
        # DWM bounds exclude invisible resize borders and use physical pixels.
        try:
            c.windll.dwmapi.DwmGetWindowAttribute(w.HWND(hwnd), 9, c.byref(rect), c.sizeof(rect))
        except OSError:
            pass
        m = info.rcMonitor
        return covers_monitor((rect.left,rect.top,rect.right,rect.bottom), (m.left,m.top,m.right,m.bottom))
