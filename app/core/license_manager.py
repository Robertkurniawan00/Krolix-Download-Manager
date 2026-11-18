"""
Krolix Download Manager - Advanced Licensing & Registration Engine
Features:
- Exact Standard Serial Key Pattern: XXXXX-XXXXX-XXXXX-XXXXX (20 Alphanumeric Characters)
- Advanced Honeypot Keygen Detection (Catches unauthorized key generator seeds & algorithms)
- Hosts File DNS Hijack Detection (Detects loopback activation bypassing)
- Leaked / Blacklisted Serial Detection
- Advance Master Mode (Extreme 64-Segment Overdrive Acceleration & Turbo Engine)
- Asymmetric Ed25519 Digital Signature Dual-Engine Support
- Anti-Clock Rollback & Anti-Database Tampering
"""

import os
import time
import struct
import hashlib
import hmac
from enum import Enum
from typing import Optional, Tuple, Dict, Any, Set

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature

from .database import Database
from ..utils.security_guard import SecurityGuard, obf_dec


class LicenseStatus(Enum):
    FULL_VERSION = "full_version"
    MASTER_MODE = "master_mode"
    TRIAL = "trial"
    EXPIRED = "expired"
    FAKE_SERIAL = "fake_serial"


# Base36 alphabet for Standard 20-character serial keys
_B36_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# Crockford Base32 alphabet for high-entropy Ed25519 certificate blocks
_CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_DECODE_MAP = {c: i for i, c in enumerate(_CROCKFORD_ALPHABET)}
_DECODE_MAP["O"] = 0
_DECODE_MAP["I"] = 1
_DECODE_MAP["L"] = 1


def _crockford_decode(s: str) -> bytes:
    clean = s.strip().replace("-", "").replace(" ", "").replace("\r", "").replace("\n", "").upper()
    bit_buffer = 0
    bits_in_buffer = 0
    out = bytearray()
    for char in clean:
        if char not in _DECODE_MAP:
            continue
        val = _DECODE_MAP[char]
        bit_buffer = (bit_buffer << 5) | val
        bits_in_buffer += 5
        while bits_in_buffer >= 8:
            bits_in_buffer -= 8
            byte = (bit_buffer >> bits_in_buffer) & 0xFF
            out.append(byte)
    return bytes(out)


class LicenseManager:
    _instance: Optional["LicenseManager"] = None

    # Specifications
    TRIAL_DAYS = 30
    PAYLOAD_MAGIC = b"ZR"
    LICENSE_SPEC_VERSION = 1

    # Obfuscated Secret Salts & Keys to prevent binary string dissection
    _OBF_HMAC_KEY = b'!\x1e\t\x14$7\x12\x18\x1e\x15\x08\x1e$-IMV.77-)VCCBB0V\x1e\t\x12\x1d\x12\x18\x1a\x0f\x12\x14\x15$(\x1a\x17\x0f'
    _OBF_MASTER_SALT = b'!>)4V?4,574:?V:((2(/:5/V.77-)VIKIM'
    _OBF_PRO_SALT = b'!>)4#VIKIM=V.77-)VCCBB0V\rIUM$IKIM'

    # Master Vendor Ed25519 Public Key
    _MASTER_PUB_HEX = "076ABA9D9ED12BB6F45F9818E9C4254D64118148BC0567740AD067DEAED4DB0B"
    _PUB_SHA256_EXPECTED = "FE537AE005FC375CD798547673F51F8418CE6C77CEF00AE1E4948363BE5D8E1D"

    # Known Blacklisted / Pirated Keygen Serial Numbers
    KNOWN_BLACKLISTED_KEYS: Set[str] = {
        "7HL92-9F4K2-109KD-84720",
        "TSRH1-KEYGN-CRCKD-88291",
        "LINE0-IDM64-F4K3S-99120",
        "CRACK-10293-84719-KEY01",
        "IDM64-BUILD-FINAL-CRCKD",
        "11111-22222-33333-44444",
        "ABCDE-12345-FGHIJ-67890",
        "FREE4-ALL26-CRCKD-SERIAL",
        "ZERO1-KEYGN-CRCKD-99881",
        "W32ID-CRACK-PATCH-REG99",
        "TONEC-FAKE1-KEYGN-00000"
    }

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database.get_instance()
        self._pub_key_obj: Optional[ed25519.Ed25519PublicKey] = None
        self._init_crypto()
        self._init_license_state()

    @classmethod
    def get_instance(cls, db: Optional[Database] = None) -> "LicenseManager":
        if cls._instance is None:
            cls._instance = cls(db)
        return cls._instance

    def _init_crypto(self):
        try:
            pub_bytes = bytes.fromhex(self._MASTER_PUB_HEX)
            if hashlib.sha256(pub_bytes).hexdigest().upper() != self._PUB_SHA256_EXPECTED:
                self._pub_key_obj = None
                return
            self._pub_key_obj = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
        except Exception:
            self._pub_key_obj = None

    def _init_license_state(self):
        now = time.time()
        trial_start = self.db.get_setting("trial_start_timestamp", "")
        if not trial_start:
            self.db.set_setting("trial_start_timestamp", str(now))
            self.db.set_setting("license_last_seen_ts", str(now))
        else:
            self._check_anti_clock_tamper(now)

    def _check_anti_clock_tamper(self, current_time: float) -> bool:
        last_seen_str = self.db.get_setting("license_last_seen_ts", "")
        try:
            last_seen = float(last_seen_str)
        except (ValueError, TypeError):
            last_seen = current_time

        if current_time < (last_seen - 3600.0):
            self.db.set_setting("license_status", "expired")
            self.db.set_setting("trial_tamper_flag", "clock_rollback_detected")
            return False

        if current_time > last_seen:
            self.db.set_setting("license_last_seen_ts", str(current_time))
        return True

    @staticmethod
    def check_hosts_file_hijack() -> Tuple[bool, str]:
        """
        Detects if hosts file redirects licensing/activation domains to 127.0.0.1 or 0.0.0.0.
        Commonly executed by automated keygen / crack batch scripts.
        """
        hosts_path = os.path.expandvars(r"%SystemRoot%\System32\drivers\etc\hosts")
        if not os.path.exists(hosts_path):
            return False, ""

        blocked_targets = [
            "krolix.app", "activate.krolix.app", "register.krolix.app",
            "license.krolix.app", "tonec.com", "registeridm.com", "internetdownloadmanager.com"
        ]

        try:
            with open(hosts_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split()
                    if len(parts) >= 2:
                        ip = parts[0].strip()
                        domain = parts[1].strip().lower()
                        if ip in ("127.0.0.1", "0.0.0.0", "::1"):
                            for tgt in blocked_targets:
                                if tgt in domain:
                                    return True, f"Manipulasi file hosts terdeteksi: '{domain}' dialihkan ke '{ip}'."
        except Exception:
            pass

        return False, ""

    @classmethod
    def _compute_decoy_keygen_trap(cls, b1: str, b2: str, email: str) -> str:
        """
        Honeypot Decoy Polynomial:
        Keygen authors reverse-engineer this routine and believe they have cracked the algorithm.
        Any serial where Block 3 matches this trap BUT fails the deep cryptographic seal Block 4
        is GUARANTEED to have been produced by an unauthorized keygen!
        """
        seed = 0x5A2D
        raw = b1.upper() + b2.upper() + email.strip().lower()
        for i, ch in enumerate(raw):
            seed = ((seed * 31) + ord(ch) + (i * 7)) & 0xFFFFFFFF
        res = []
        for _ in range(5):
            res.append(_B36_ALPHABET[seed % 36])
            seed //= 36
        return "".join(res)

    @classmethod
    def _compute_crypto_seal(cls, full_name: str, email: str, b1: str, b2: str, b3: str, is_master: bool) -> str:
        """
        Deep Cryptographic HMAC Signature (Real Method, No Gimmick):
        Only the vendor's genuine license generator knows the internal secret key and tier salts.
        """
        salt = obf_dec(cls._OBF_MASTER_SALT) if is_master else obf_dec(cls._OBF_PRO_SALT)
        secret_hmac = obf_dec(cls._OBF_HMAC_KEY).encode("utf-8")
        raw = f"{full_name.strip().lower()}::{email.strip().lower()}::{b1.upper()}::{b2.upper()}::{b3.upper()}::{salt}"
        digest = hmac.new(secret_hmac, raw.encode("utf-8"), hashlib.sha256).digest()
        num = struct.unpack(">I", digest[:4])[0]
        res = []
        for _ in range(5):
            res.append(_B36_ALPHABET[num % 36])
            num //= 36
        return "".join(res)

    def get_trial_days_remaining(self) -> int:
        if self.db.get_setting("trial_tamper_flag", ""):
            return 0

        trial_start_str = self.db.get_setting("trial_start_timestamp", "")
        try:
            trial_start = float(trial_start_str)
        except (ValueError, TypeError):
            trial_start = time.time()
            self.db.set_setting("trial_start_timestamp", str(trial_start))

        now = time.time()
        self._check_anti_clock_tamper(now)

        elapsed_seconds = max(0.0, now - trial_start)
        elapsed_days = int(elapsed_seconds // 86400)
        remaining = max(0, self.TRIAL_DAYS - elapsed_days)
        return remaining

    def get_status(self) -> LicenseStatus:
        """
        Determines current license status.
        Never blindly trusts database status - always re-validates cryptographic integrity.
        """
        status_setting = self.db.get_setting("license_status", "")
        if status_setting in ("full_version", "master_mode"):
            serial = self.db.get_setting("license_serial_key", "")
            first = self.db.get_setting("license_user_first_name", "")
            last = self.db.get_setting("license_user_last_name", "")
            email = self.db.get_setting("license_user_email", "")

            valid, code, _ = self.validate_serial_key(first, last, email, serial)
            if valid:
                return LicenseStatus.MASTER_MODE if code == "VALID_MASTER" else LicenseStatus.FULL_VERSION
            else:
                if code.startswith("FAKE_SERIAL"):
                    self.db.set_setting("license_status", "fake_serial")
                    return LicenseStatus.FAKE_SERIAL
                self.db.set_setting("license_status", "expired")
                return LicenseStatus.EXPIRED

        if status_setting == "fake_serial":
            return LicenseStatus.FAKE_SERIAL

        if status_setting == "expired":
            return LicenseStatus.EXPIRED

        days_left = self.get_trial_days_remaining()
        if days_left > 0:
            return LicenseStatus.TRIAL
        return LicenseStatus.EXPIRED

    def is_full_version(self) -> bool:
        """Returns True if the software is registered as Pro or Advance Master Mode."""
        return self.get_status() in (LicenseStatus.FULL_VERSION, LicenseStatus.MASTER_MODE)

    def is_master_mode(self) -> bool:
        """Returns True if registered in Advance Master Mode (unrestricted turbo overdrive)."""
        return self.get_status() == LicenseStatus.MASTER_MODE

    def is_trial_active(self) -> bool:
        return self.get_status() == LicenseStatus.TRIAL

    def is_feature_allowed(self, feature_name: str) -> bool:
        start_tick = SecurityGuard.get_performance_counter()

        # 1. Anti-Monkeypatch & Anti-Tamper Verification
        if not SecurityGuard.verify_callable_integrity(self.is_feature_allowed, "app.core.license_manager"):
            return False
        if not SecurityGuard.verify_callable_integrity(self.get_status, "app.core.license_manager"):
            return False
        if not SecurityGuard.verify_callable_integrity(self.validate_serial_key, "app.core.license_manager"):
            return False

        # 2. Anti-Debugging & Dissection Check
        if SecurityGuard.is_debugger_present() or SecurityGuard.is_dissection_tool_running() or SecurityGuard.scan_unauthorized_runtime_files():
            return False

        # 3. Timing anomaly check (detects single-stepping instructions)
        if SecurityGuard.check_timing_anomaly(start_tick):
            return False

        status = self.get_status()
        if status in (LicenseStatus.FULL_VERSION, LicenseStatus.MASTER_MODE, LicenseStatus.TRIAL):
            return True

        restricted_features = {
            "site_grabber": False,
            "scheduler": False,
            "batch_download": False,
            "high_connections": False,
            "unlimited_concurrent": False,
            "speed_unlimited": True
        }
        return restricted_features.get(feature_name, False)

    def get_feature_session_token(self, feature_name: str) -> Optional[bytes]:
        """
        Cryptographically derives a high-security HMAC runtime token for premium features.
        Even if an attacker patches boolean checks, they cannot synthesize this token without
        valid cryptographic keys and authentic HWID binding.
        """
        if not self.is_feature_allowed(feature_name):
            return None

        status = self.get_status()
        hwid = self.get_hardware_id()
        serial = self.db.get_setting("license_serial_key", "")
        secret = obf_dec(self._OBF_HMAC_KEY).encode("utf-8")
        payload = f"{hwid}::{feature_name}::{status.value}::{serial}".encode("utf-8")
        return hmac.new(secret, payload, hashlib.sha256).digest()

    def verify_feature_token(self, feature_name: str, token: Optional[bytes]) -> bool:
        """Verifies that a feature execution request carries a genuine cryptographic session token."""
        if not token or len(token) != 32:
            return False
        expected = self.get_feature_session_token(feature_name)
        if not expected:
            return False
        return hmac.compare_digest(token, expected)

    def get_max_segments_allowed(self) -> int:
        """
        Advance Master Mode: 64 segments (Ultra Overdrive)!
        Pro Full Version / Active Trial: 32 segments.
        Expired / Fake Serial: 4 segments.
        """
        if self.is_master_mode():
            return 64
        if self.is_full_version():
            return 32
        if self.is_trial_active():
            return 32
        return 4

    def get_max_concurrent_allowed(self) -> int:
        """
        Advance Master Mode: 64 simultaneous downloads.
        Pro Full Version / Active Trial: 32 simultaneous downloads.
        Expired / Fake Serial: 2 simultaneous downloads.
        """
        if self.is_master_mode():
            return 64
        if self.is_full_version():
            return 32
        if self.is_trial_active():
            return 32
        return 2

    def get_hardware_id(self) -> str:
        return SecurityGuard.get_hardware_id()

    def validate_serial_key(
        self, first_name: str, last_name: str, email: str, serial_key: str
    ) -> Tuple[bool, str, str]:
        """
        Validates the serial key.
        Returns: (is_valid, status_code, message)
        
        Status codes:
          - 'VALID_MASTER': Advance Master Mode (Unlimited 64-conn)
          - 'VALID_PRO': Standard Commercial Pro Full Version
          - 'FAKE_SERIAL_KEYGEN': Honeypot keygen detected!
          - 'FAKE_SERIAL_BLACKLIST': Known blacklisted/leaked serial
          - 'FAKE_SERIAL_HOSTS': Hosts file redirection detected
          - 'INVALID_KEY': General mismatch or corrupted key
        """
        fn = first_name.strip()
        ln = last_name.strip()
        full_name = f"{fn} {ln}".strip() if fn and ln else (fn or ln)
        if not full_name:
            return False, "INVALID_INPUT", "Nama lengkap pemilik lisensi wajib diisi."

        email_clean = email.strip().lower()
        if not email_clean or "@" not in email_clean or "." not in email_clean:
            return False, "INVALID_INPUT", "Alamat email tidak valid."

        key_clean = serial_key.strip().upper().replace(" ", "")
        if not key_clean:
            return False, "INVALID_INPUT", "Serial key tidak boleh kosong."

        # 1. Hosts File DNS Hijack Check
        hosts_hijack, hijack_msg = self.check_hosts_file_hijack()
        if hosts_hijack:
            return (
                False,
                "FAKE_SERIAL_HOSTS",
                f"Krolix Download Manager mendeteksi manipulasi file hosts!\n{hijack_msg}\n"
                "Kembalikan file hosts Windows ke kondisi default untuk melanjutkan."
            )

        # 2. Known Blacklist / Pirated Serials Check
        if key_clean in self.KNOWN_BLACKLISTED_KEYS:
            return (
                False,
                "FAKE_SERIAL_BLACKLIST",
                "Serial Number ini masuk dalam daftar hitam lisensi bajakan/bocor ke publik."
            )

        # --- A. Check Standard Pattern: XXXXX-XXXXX-XXXXX-XXXXX (20 chars) ---
        parts = key_clean.split("-")
        if len(parts) == 4 and all(len(p) == 5 for p in parts):
            b1, b2, b3, b4 = parts
            is_master = b1.startswith("ZM")

            expected_decoy = self._compute_decoy_keygen_trap(b1, b2, email_clean)
            expected_seal = self._compute_crypto_seal(full_name, email_clean, b1, b2, b3, is_master)

            # Genuine Key: Both decoy polynomial AND deep cryptographic HMAC match!
            if b3 == expected_decoy and b4 == expected_seal:
                if is_master:
                    return (
                        True,
                        "VALID_MASTER",
                        "Kunci lisensi sah terverifikasi (Krolix Advance Master Mode - 64 Koneksi Aktif)."
                    )
                else:
                    return (
                        True,
                        "VALID_PRO",
                        "Kunci lisensi sah terverifikasi (Krolix Pro Full Version)."
                    )

            # KEYGEN HONEYPOT TRAP DETECTED:
            # Block 3 matches the decoy algorithm, but Block 4 failed the cryptographic seal!
            if b3 == expected_decoy and b4 != expected_seal:
                return (
                    False,
                    "FAKE_SERIAL_KEYGEN",
                    "Krolix Download Manager mendeteksi bahwa Serial Number ini dibuat oleh Keygen ilegal!\n"
                    "Algoritma honeypot mengonfirmasi bahwa kunci ini bukan diterbitkan oleh server resmi Krolix."
                )

            return (
                False,
                "INVALID_KEY",
                "Serial number tidak valid. Periksa kembali nama, email, dan kode serial Anda."
            )

        # --- B. Check Ed25519 Certificate Block (128 chars Crockford Base32) ---
        raw_blob = _crockford_decode(key_clean)
        if len(raw_blob) == 80 and self._pub_key_obj:
            payload = raw_blob[:16]
            signature = raw_blob[16:]
            magic, ver, tier, expiry_ts, hwid_mode = struct.unpack(">2sBBIB", payload[:9])
            hwid_hash_bytes = payload[9:13]
            email_hash_bytes = payload[13:16]

            if magic == self.PAYLOAD_MAGIC and ver == self.LICENSE_SPEC_VERSION:
                data_to_verify = payload + b"::" + full_name.encode("utf-8") + b"::" + email_clean.encode("utf-8")
                try:
                    self._pub_key_obj.verify(signature, data_to_verify)
                    if hwid_mode == 1:
                        if hwid_hash_bytes != SecurityGuard.get_hardware_hash_crc32().to_bytes(4, "big"):
                            return (
                                False,
                                "HWID_MISMATCH",
                                f"Serial key ini terkunci pada perangkat keras (HWID) lain.\n"
                                f"Hardware ID komputer ini: {SecurityGuard.get_hardware_id()}"
                            )
                    return True, "VALID_PRO", "Kunci lisensi sertifikat Ed25519 sah terverifikasi."
                except InvalidSignature:
                    return (
                        False,
                        "FAKE_SERIAL_KEYGEN",
                        "Tanda tangan kriptografi serial key tidak sah atau dipalsukan!"
                    )
                except Exception:
                    pass

        return (
            False,
            "INVALID_KEY",
            "Format serial number tidak dikenali. Format harus berupa 4 blok 5 karakter (XXXXX-XXXXX-XXXXX-XXXXX)."
        )

    def register(self, first_name: str, last_name: str, email: str, serial_key: str) -> Tuple[bool, str, str]:
        """
        Registers product license.
        Returns: (success, message, status_code)
        """
        valid, code, msg = self.validate_serial_key(first_name, last_name, email, serial_key)
        if not valid:
            if code.startswith("FAKE_SERIAL"):
                self.db.set_setting("license_status", "fake_serial")
                self.db.set_setting("license_fake_reason", msg)
                self.db.set_setting("license_serial_key", serial_key.strip().upper())
            return False, msg, code

        target_status = "master_mode" if code == "VALID_MASTER" else "full_version"
        self.db.set_setting("license_status", target_status)
        self.db.set_setting("license_user_first_name", first_name.strip())
        self.db.set_setting("license_user_last_name", last_name.strip())
        self.db.set_setting("license_user_email", email.strip().lower())
        self.db.set_setting("license_serial_key", serial_key.strip().upper())
        self.db.set_setting("license_registered_date", str(time.time()))
        self.db.set_setting("license_last_seen_ts", str(time.time()))
        self.db.set_setting("license_fake_reason", "")
        self.db.set_setting("trial_tamper_flag", "")

        tier_name = "Advance Master Mode (Turbo 64 Segmen)" if code == "VALID_MASTER" else "Full Version"
        return True, f"Registrasi berhasil! Krolix Download Manager aktif sebagai {tier_name}.", code

    def unregister(self) -> bool:
        self.db.set_setting("license_status", "expired")
        self.db.set_setting("license_serial_key", "")
        self.db.set_setting("license_fake_reason", "")
        return True

    def set_trial_expired_for_testing(self):
        expired_ts = time.time() - (35 * 86400)
        self.db.set_setting("license_status", "expired")
        self.db.set_setting("trial_start_timestamp", str(expired_ts))

    def reset_trial_for_testing(self):
        self.db.set_setting("license_status", "trial")
        self.db.set_setting("trial_start_timestamp", str(time.time()))
        self.db.set_setting("license_serial_key", "")
        self.db.set_setting("license_fake_reason", "")
        self.db.set_setting("trial_tamper_flag", "")

    def get_license_display_info(self) -> Dict[str, Any]:
        status = self.get_status()
        first = self.db.get_setting("license_user_first_name", "")
        last = self.db.get_setting("license_user_last_name", "")
        email = self.db.get_setting("license_user_email", "")
        serial = self.db.get_setting("license_serial_key", "")
        fake_reason = self.db.get_setting("license_fake_reason", "")
        days_left = self.get_trial_days_remaining()
        hwid = self.get_hardware_id()

        name = f"{first} {last}".strip()
        if not name and status in (LicenseStatus.FULL_VERSION, LicenseStatus.MASTER_MODE):
            name = "Licensed User"

        masked_serial = ""
        if serial:
            parts = [p for p in serial.split("-") if p]
            if len(parts) == 4:
                masked_serial = f"{parts[0]}-****-****-{parts[-1]}"
            elif len(parts) >= 2:
                masked_serial = f"{parts[0]}-****-****-{parts[-1]}"
            else:
                masked_serial = serial[:5] + "-****"

        return {
            "status": status,
            "is_full": status in (LicenseStatus.FULL_VERSION, LicenseStatus.MASTER_MODE),
            "is_master": status == LicenseStatus.MASTER_MODE,
            "is_trial": status == LicenseStatus.TRIAL,
            "is_expired": status == LicenseStatus.EXPIRED,
            "is_fake": status == LicenseStatus.FAKE_SERIAL,
            "fake_reason": fake_reason,
            "registered_name": name or "Tidak Terdaftar",
            "registered_email": email or "-",
            "serial_masked": masked_serial,
            "serial_raw": serial,
            "days_left": days_left,
            "hardware_id": hwid,
            "status_title": (
                "★ Advance Master Mode (Akses Penuh Tanpa Batas - 64 Segmen) ★"
                if status == LicenseStatus.MASTER_MODE
                else "Full Version (Terdaftar - Pola Standar Terverifikasi)"
                if status == LicenseStatus.FULL_VERSION
                else "Peringatan: Serial Number Palsu / Keygen Terdeteksi!"
                if status == LicenseStatus.FAKE_SERIAL
                else f"Masa Uji Coba ({days_left} Hari Tersisa)"
                if status == LicenseStatus.TRIAL
                else "Masa Evaluasi Habis (Fungsi Dibatasi)"
            ),
        }
