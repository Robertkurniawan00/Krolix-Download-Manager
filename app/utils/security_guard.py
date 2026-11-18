"""
Zero Download Assistant - Security & Anti-Reverse-Engineering Guard
Protects against debugging, memory inspection, file tampering, monkeypatching, and source extraction.
Provides robust hardware fingerprinting and cryptographic integrity verification.
"""

import sys
import os
import ctypes
from ctypes import wintypes
import hashlib
import zlib
from typing import Optional, Any

# XOR-based string protection key
_OBF_KEY = 0x7B


def obf_dec(blob: bytes, key: int = _OBF_KEY) -> str:
    """Decrypts obfuscated string literals at runtime to prevent static binary analysis."""
    return bytes([b ^ key for b in blob]).decode('utf-8', errors='ignore')


def obf_enc(text: str, key: int = _OBF_KEY) -> bytes:
    """Helper to generate encrypted byte blobs."""
    return bytes([b ^ key for b in text.encode('utf-8')])


class SecurityGuard:
    # Obfuscated list of 19 known reverse engineering, memory dumper, and traffic snooping tool process names
    _RE_PROCESSES_ENC = [
        b'\x03MO\x1f\x19\x1cU\x1e\x03\x1e',                      # x64dbg.exe
        b'\x03HI\x1f\x19\x1cU\x1e\x03\x1e',                      # x32dbg.exe
        b'\x03BM\x1f\x19\x1cU\x1e\x03\x1e',                      # x96dbg.exe
        b'\x18\x13\x1e\x1a\x0f\x1e\x15\x1c\x12\x15\x1eU\x1e\x03\x1e',  # cheatengine.exe
        b'\x12\x1f\x1aMOU\x1e\x03\x1e',                          # ida64.exe
        b'\x12\x1f\x1aU\x1e\x03\x1e',                            # ida.exe
        b'\x1c\x13\x12\x1f\t\x1aU\x1e\x03\x1e',                  # ghidra.exe
        b'\x1f\x15\x08\x0b\x02U\x1e\x03\x1e',                    # dnspy.exe
        b'\x12\x17\x08\x0b\x02U\x1e\x03\x1e',                    # ilspy.exe
        b'\x1f\x1eO\x1f\x14\x0fU\x1e\x03\x1e',                  # de4dot.exe
        b'\x08\x18\x02\x17\x17\x1aU\x1e\x03\x1e',                # scylla.exe
        b'\x0b\t\x14\x18\x1e\x08\x08\x13\x1a\x18\x10\x1e\tU\x1e\x03\x1e',  # processhacker.exe
        b'\x0b\t\x14\x18\x16\x14\x15U\x1e\x03\x1e',              # procmon.exe
        b'\x0b\t\x14\x18\x16\x14\x15MOU\x1e\x03\x1e',            # procmon64.exe
        b'\x0c\x12\t\x1e\x08\x13\x1a\t\x10U\x1e\x03\x1e',        # wireshark.exe
        b'\x1d\x12\x1f\x1f\x17\x1e\tU\x1e\x03\x1e',              # fiddler.exe
        b'\x18\x13\x1a\t\x17\x1e\x08U\x1e\x03\x1e',              # charles.exe
        b'\x13\x0f\x0f\x0b\x1f\x1e\x19\x0e\x1c\x1c\x1e\tU\x1e\x03\x1e',  # httpdebugger.exe
        b'\x14\x17\x17\x02\x1f\x19\x1cU\x1e\x03\x1e',            # ollydbg.exe
    ]

    _cached_hwid: Optional[str] = None

    @classmethod
    def get_hardware_id(cls) -> str:
        """
        Generates a deterministic, unique Hardware ID (HWID) bound to this computer.
        Uses Windows MachineGuid, Volume Serial Number, and CPU specification.
        Format: ZHWID-XXXX-XXXX-XXXX-XXXX
        """
        if cls._cached_hwid:
            return cls._cached_hwid

        parts = []

        # 1. MachineGuid from registry
        if sys.platform == "win32":
            try:
                import winreg
                k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
                guid, _ = winreg.QueryValueEx(k, "MachineGuid")
                parts.append(str(guid).strip().lower())
            except Exception:
                parts.append("guid-fallback-win32")

            # 2. Volume serial number of system drive (C:)
            try:
                vol = ctypes.c_ulong()
                ctypes.windll.kernel32.GetVolumeInformationW("C:\\", None, 0, ctypes.byref(vol), None, None, None, 0)
                parts.append(f"{vol.value:08X}")
            except Exception:
                parts.append("vol-fallback-win32")

            # 3. CPU processor description
            try:
                import winreg
                k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
                cpu, _ = winreg.QueryValueEx(k, "ProcessorNameString")
                parts.append(str(cpu).strip())
            except Exception:
                parts.append("cpu-fallback-win32")
        else:
            parts.append("posix-generic-device")

        raw_fingerprint = "::".join(parts)
        h = hashlib.sha256(raw_fingerprint.encode("utf-8")).hexdigest().upper()
        cls._cached_hwid = f"ZHWID-{h[0:4]}-{h[4:8]}-{h[8:12]}-{h[12:16]}"
        return cls._cached_hwid

    @classmethod
    def get_hardware_hash_crc32(cls) -> int:
        """Returns integer CRC32 hash of the machine HWID for compact license embedding."""
        hwid = cls.get_hardware_id()
        return zlib.crc32(hwid.encode("utf-8"))

    @staticmethod
    def is_kernel_debugger_present() -> bool:
        """
        Low-level kernel debugger check via ntdll.NtQueryInformationProcess.
        Bypasses user-mode hooks placed on IsDebuggerPresent / CheckRemoteDebuggerPresent.
        """
        if sys.platform != "win32":
            return False

        try:
            ntdll = ctypes.windll.ntdll
            NtQueryInformationProcess = ntdll.NtQueryInformationProcess
            NtQueryInformationProcess.argtypes = [
                wintypes.HANDLE,
                wintypes.ULONG,
                ctypes.c_void_p,
                wintypes.ULONG,
                ctypes.POINTER(wintypes.ULONG)
            ]
            NtQueryInformationProcess.restype = wintypes.LONG

            h_proc = ctypes.windll.kernel32.GetCurrentProcess()
            ret_len = wintypes.ULONG(0)

            # 1. ProcessDebugPort (7): Returns non-zero port number if kernel debugger is attached
            port = ctypes.c_size_t(0)
            ret1 = NtQueryInformationProcess(h_proc, 7, ctypes.byref(port), ctypes.sizeof(port), ctypes.byref(ret_len))
            if ret1 == 0 and port.value != 0:
                return True

            # 2. ProcessDebugFlags (0x1F): Inverted flag. Returns 0 if process is being debugged
            flags = wintypes.ULONG(0)
            ret2 = NtQueryInformationProcess(h_proc, 0x1F, ctypes.byref(flags), ctypes.sizeof(flags), ctypes.byref(ret_len))
            if ret2 == 0 and flags.value == 0:
                return True
        except Exception:
            pass

        return False

    @classmethod
    def is_debugger_present(cls) -> bool:
        """Checks for active Win32 user-mode, remote, and kernel-mode debuggers."""
        if sys.platform != "win32":
            return False

        try:
            # 1. PEB BeingDebugged flag
            if ctypes.windll.kernel32.IsDebuggerPresent():
                return True

            # 2. CheckRemoteDebuggerPresent API
            is_remote_debugger = ctypes.c_bool(False)
            h_proc = ctypes.windll.kernel32.GetCurrentProcess()
            ctypes.windll.kernel32.CheckRemoteDebuggerPresent(h_proc, ctypes.byref(is_remote_debugger))
            if is_remote_debugger.value:
                return True

            # 3. Kernel-level NtQueryInformationProcess checks
            if cls.is_kernel_debugger_present():
                return True
        except Exception:
            pass

        return False

    @classmethod
    def is_dissection_tool_running(cls) -> bool:
        """Checks if memory analysis, disassembler, or cracking tools are running using native Win32 APIs."""
        if sys.platform != "win32":
            return False

        blacklisted = [obf_dec(b).lower() for b in cls._RE_PROCESSES_ENC]

        # 1. First attempt: Native Win32 Toolhelp32Snapshot (zero external dependencies)
        try:
            class PROCESSENTRY32W(ctypes.Structure):
                _fields_ = [
                    ('dwSize', wintypes.DWORD),
                    ('cntUsage', wintypes.DWORD),
                    ('th32ProcessID', wintypes.DWORD),
                    ('th32DefaultHeapID', ctypes.c_size_t),
                    ('th32ModuleID', wintypes.DWORD),
                    ('cntThreads', wintypes.DWORD),
                    ('th32ParentProcessID', wintypes.DWORD),
                    ('pcPriClassBase', wintypes.LONG),
                    ('dwFlags', wintypes.DWORD),
                    ('szExeFile', wintypes.WCHAR * 260)
                ]

            TH32CS_SNAPPROCESS = 0x00000002
            h_snap = ctypes.windll.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            if h_snap and h_snap != -1:
                pe = PROCESSENTRY32W()
                pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
                if ctypes.windll.kernel32.Process32FirstW(h_snap, ctypes.byref(pe)):
                    while True:
                        name = pe.szExeFile.lower()
                        if any(target in name for target in blacklisted):
                            ctypes.windll.kernel32.CloseHandle(h_snap)
                            return True
                        if not ctypes.windll.kernel32.Process32NextW(h_snap, ctypes.byref(pe)):
                            break
                ctypes.windll.kernel32.CloseHandle(h_snap)
        except Exception:
            pass

        # 2. Fallback attempt: psutil if available
        try:
            import psutil
            for proc in psutil.process_iter(['name']):
                try:
                    pname = (proc.info['name'] or '').lower()
                    if any(target in pname for target in blacklisted):
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass

        return False

    @staticmethod
    def sanitize_environment():
        """
        Strips hostile injection environment variables (PYTHONPATH, PYTHONHOME, etc.)
        used by crack loaders and unpackers to inject malicious scripts into the standalone runtime.
        """
        for var in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONINSPECT", "PYTHONDEBUG"):
            os.environ.pop(var, None)
        sys.dont_write_bytecode = True

    @staticmethod
    def scan_unauthorized_runtime_files() -> bool:
        """
        Detects rogue injection files (sitecustomize.py, usercustomize.py, .pth files)
        dropped by crackers into the application directory to hijack execution.
        """
        # Check if sitecustomize or usercustomize has been loaded into sys.modules
        if "sitecustomize" in sys.modules or "usercustomize" in sys.modules:
            return True

        # If running frozen in PyInstaller, inspect executable directory and _internal
        if getattr(sys, "frozen", False):
            try:
                app_root = os.path.dirname(sys.executable)
                rogue_names = {"sitecustomize.py", "usercustomize.py", "license_manager.py", "security_guard.py"}
                for check_dir in [app_root, os.path.join(app_root, "_internal")]:
                    if os.path.isdir(check_dir):
                        for fname in os.listdir(check_dir):
                            f_low = fname.lower()
                            if f_low in rogue_names or f_low.endswith(".pth"):
                                return True
            except Exception:
                pass

        return False

    @staticmethod
    def verify_callable_integrity(func: Any, expected_module: str) -> bool:
        """
        Verifies that a critical method (e.g. is_feature_allowed, get_status)
        has not been monkeypatched, replaced with a lambda, or hooked in memory.
        """
        if not callable(func):
            return False

        # Verify module owner
        mod = getattr(func, "__module__", None)
        if mod != expected_module:
            return False

        # Verify code object
        code = getattr(func, "__code__", None)
        if not code:
            return False

        # Reject lambdas and generator expressions used as crack patches
        if code.co_name in ("<lambda>", "<genexpr>"):
            return False

        # Reject foreign scripts outside frozen runtime
        if getattr(sys, "frozen", False):
            fn = (code.co_filename or "").lower()
            if "temp" in fn or "desktop" in fn or "downloads" in fn:
                return False

        return True

    @staticmethod
    def get_performance_counter() -> int:
        """Returns high-resolution hardware performance counter for timing anomaly checks."""
        if sys.platform == "win32":
            try:
                cnt = ctypes.c_int64(0)
                ctypes.windll.kernel32.QueryPerformanceCounter(ctypes.byref(cnt))
                return cnt.value
            except Exception:
                pass
        import time
        return int(time.perf_counter() * 1000000)

    @classmethod
    def check_timing_anomaly(cls, start_ticks: int, max_ticks: int = 25000000) -> bool:
        """Detects if a human cracker is single-stepping through license validation instructions."""
        now = cls.get_performance_counter()
        delta = now - start_ticks
        return delta > max_ticks

    @classmethod
    def init_protection(cls):
        """Runs comprehensive multi-tier security screening upon application startup."""
        cls.sanitize_environment()

        if cls.is_debugger_present() or cls.is_dissection_tool_running() or cls.scan_unauthorized_runtime_files():
            # Silently exit without giving debugging clues to the attacker
            sys.exit(0)
