"""
Zero Download Assistant - C / Win32 Native System Integration
Utilizes Windows kernel32.dll & user32.dll for low-overhead OS coordination.
"""

import sys
import ctypes
from ctypes import wintypes

# Windows Execution State Flags (Power Management)
ES_SYSTEM_REQUIRED  = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002
ES_USER_PRESENT     = 0x00000004
ES_AWAYMODE_REQUIRED= 0x00000040
ES_CONTINUOUS       = 0x80000000

class Win32Native:
    _kernel32 = None
    _user32 = None

    @classmethod
    def _init(cls):
        if sys.platform == 'win32' and cls._kernel32 is None:
            try:
                cls._kernel32 = ctypes.windll.kernel32
                cls._user32 = ctypes.windll.user32
            except Exception:
                pass

    @classmethod
    def prevent_sleep(cls, prevent: bool = True):
        """
        Prevent Windows from going to Sleep or powering down the screen while active downloads run.
        """
        cls._init()
        if not cls._kernel32:
            return

        try:
            if prevent:
                # System required + Away mode + Continuous
                flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
                cls._kernel32.SetThreadExecutionState(flags)
            else:
                # Reset to normal continuous state
                cls._kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        except Exception as e:
            print(f"[Win32Native] Error setting thread execution state: {e}")

    @classmethod
    def flash_window(cls, hwnd: int, count: int = 3):
        """Flash window in taskbar when download finishes"""
        cls._init()
        if not cls._user32 or not hwnd:
            return

        try:
            # FLASHWINFO struct
            class FLASHWINFO(ctypes.Structure):
                _fields_ = [
                    ('cbSize', wintypes.UINT),
                    ('hwnd', wintypes.HWND),
                    ('dwFlags', wintypes.DWORD),
                    ('uCount', wintypes.UINT),
                    ('dwTimeout', wintypes.DWORD)
                ]

            FLASHW_ALL = 3
            FLASHW_TIMERNOFG = 12

            finfo = FLASHWINFO()
            finfo.cbSize = ctypes.sizeof(FLASHWINFO)
            finfo.hwnd = hwnd
            finfo.dwFlags = FLASHW_ALL | FLASHW_TIMERNOFG
            finfo.uCount = count
            finfo.dwTimeout = 0

            cls._user32.FlashWindowEx(ctypes.byref(finfo))
        except Exception as e:
            print(f"[Win32Native] Flash window error: {e}")

    @classmethod
    def play_system_alert(cls, alert_type: int = 0):
        """Trigger native Windows audio alert via user32 MessageBeep"""
        cls._init()
        if cls._user32:
            try:
                cls._user32.MessageBeep(alert_type)
            except Exception:
                pass

    @classmethod
    def force_foreground_window(cls, hwnd: int):
        """Bypass Windows LockSetForegroundWindow and force window to front"""
        cls._init()
        if not cls._user32 or not hwnd:
            return
        try:
            user32 = cls._user32
            kernel32 = cls._kernel32

            # 1. Grant unrestricted foreground permission
            try:
                user32.AllowSetForegroundWindow(-1)
            except Exception:
                pass

            # 2. Simulate Alt key down/up to convince Windows the user is interacting with our app
            VK_MENU = 0x12
            KEYEVENTF_KEYUP = 0x0002
            try:
                user32.keybd_event(VK_MENU, 0, 0, 0)
                user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
            except Exception:
                pass

            fore_hwnd = user32.GetForegroundWindow()
            if fore_hwnd != hwnd:
                fore_tid = user32.GetWindowThreadProcessId(fore_hwnd, None)
                cur_tid = kernel32.GetCurrentThreadId() if kernel32 else 0
                if fore_tid and cur_tid and fore_tid != cur_tid:
                    user32.AttachThreadInput(cur_tid, fore_tid, True)
                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    user32.ShowWindow(hwnd, 5)  # SW_SHOW
                    user32.BringWindowToTop(hwnd)
                    user32.SetForegroundWindow(hwnd)
                    user32.AttachThreadInput(cur_tid, fore_tid, False)
                else:
                    user32.ShowWindow(hwnd, 9)
                    user32.ShowWindow(hwnd, 5)
                    user32.BringWindowToTop(hwnd)
                    user32.SetForegroundWindow(hwnd)
            else:
                user32.ShowWindow(hwnd, 5)
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)

            # Extra guarantee: HWND_TOPMOST toggle ensures it sits on top of Chrome
            HWND_TOPMOST = -1
            HWND_NOTOPMOST = -2
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_SHOWWINDOW = 0x0040
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        except Exception:
            pass

    @classmethod
    def preallocate_disk_space(cls, filepath: str, size_bytes: int) -> bool:
        """
        Pre-allocate physical disk clusters on NTFS / ReFS using low-level Win32 API.
        Eliminates file fragmentation, guarantees disk space reservation,
        and provides maximum write throughput with zero fragmentation.
        """
        if size_bytes <= 0:
            return False
        cls._init()
        try:
            import os
            os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
            if sys.platform == 'win32' and cls._kernel32:
                import msvcrt
                with open(filepath, 'a+b') as f:
                    handle = msvcrt.get_osfhandle(f.fileno())
                    cls._kernel32.SetFilePointerEx.argtypes = [wintypes.HANDLE, ctypes.c_int64, ctypes.POINTER(ctypes.c_int64), wintypes.DWORD]
                    cls._kernel32.SetFilePointerEx.restype = wintypes.BOOL
                    cls._kernel32.SetEndOfFile.argtypes = [wintypes.HANDLE]
                    cls._kernel32.SetEndOfFile.restype = wintypes.BOOL
                    cls._kernel32.FlushFileBuffers.argtypes = [wintypes.HANDLE]
                    cls._kernel32.FlushFileBuffers.restype = wintypes.BOOL

                    # FILE_BEGIN = 0: Move pointer to requested size and fix EOF boundary
                    ok_seek = cls._kernel32.SetFilePointerEx(handle, size_bytes, None, 0)
                    ok_eof = cls._kernel32.SetEndOfFile(handle)
                    cls._kernel32.FlushFileBuffers(handle)
                    return bool(ok_seek and ok_eof)
            else:
                with open(filepath, 'a+b') as f:
                    f.truncate(size_bytes)
                return True
        except Exception as e:
            print(f"[Win32Native] Pre-allocation error: {e}")
            return False

    @classmethod
    def flush_file_buffers(cls, file_obj_or_handle) -> bool:
        """
        Flush Windows filesystem dirty cache buffers directly to non-volatile physical storage (SSD/HDD).
        Prevents file corruption upon system crashes, blue screens, or unexpected reboots.
        """
        cls._init()
        if sys.platform != 'win32' or not cls._kernel32:
            try:
                if hasattr(file_obj_or_handle, 'flush'):
                    file_obj_or_handle.flush()
                import os
                if hasattr(file_obj_or_handle, 'fileno'):
                    os.fsync(file_obj_or_handle.fileno())
                return True
            except Exception:
                return False

        try:
            import msvcrt
            handle = None
            if hasattr(file_obj_or_handle, 'fileno'):
                try:
                    file_obj_or_handle.flush()
                except Exception:
                    pass
                handle = msvcrt.get_osfhandle(file_obj_or_handle.fileno())
            elif isinstance(file_obj_or_handle, int):
                handle = file_obj_or_handle
            
            if handle is not None:
                cls._kernel32.FlushFileBuffers.argtypes = [wintypes.HANDLE]
                cls._kernel32.FlushFileBuffers.restype = wintypes.BOOL
                return bool(cls._kernel32.FlushFileBuffers(handle))
            return False
        except Exception:
            return False