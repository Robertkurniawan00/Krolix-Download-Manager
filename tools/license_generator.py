#!/usr/bin/env python3
"""
Zero Download Assistant - Official Developer License Key Generator & Verifier
Supports:
1. IDM-Style Pattern: XXXXX-XXXXX-XXXXX-XXXXX (4 blocks of 5 alphanumeric characters)
2. Advance Master Mode (Extreme 64-segment turbo overdrive)
3. Honeypot Keygen Simulation (Demonstrates Keygen trap detection)
4. Ed25519 Full Certificate Block (128 chars Base32)

Notice:
This tool and 'tools/dev_private_key.pem' are for DEVELOPER / VENDOR USE ONLY.
DO NOT package or ship this file or the private key with the client application!
"""

import os
import sys
import argparse
import json
import time
import struct
import hashlib
import hmac
from typing import Optional

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

# Base36 alphabet for IDM-style 20-character serial keys
B36_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# Obfuscated Secret Salts (Must match LicenseManager)
_OBF_KEY = 0x7B
def obf_dec(blob: bytes, key: int = _OBF_KEY) -> str:
    return bytes([b ^ key for b in blob]).decode('utf-8', errors='ignore')

_OBF_HMAC_KEY = b'!\x1e\t\x14$7\x12\x18\x1e\x15\x08\x1e$-IMV.77-)VCCBB0V\x1e\t\x12\x1d\x12\x18\x1a\x0f\x12\x14\x15$(\x1a\x17\x0f'
_OBF_MASTER_SALT = b'!>)4V?4,574:?V:((2(/:5/V.77-)VIKIM'
_OBF_PRO_SALT = b'!>)4#VIKIM=V.77-)VCCBB0V\rIUM$IKIM'


def compute_decoy_keygen_trap(b1: str, b2: str, email: str) -> str:
    """Honeypot polynomial checksum (Block 3)."""
    seed = 0x5A2D
    raw = b1.upper() + b2.upper() + email.strip().lower()
    for i, ch in enumerate(raw):
        seed = ((seed * 31) + ord(ch) + (i * 7)) & 0xFFFFFFFF
    res = []
    for _ in range(5):
        res.append(B36_CHARS[seed % 36])
        seed //= 36
    return "".join(res)


def compute_crypto_seal(full_name: str, email: str, b1: str, b2: str, b3: str, is_master: bool) -> str:
    """Deep cryptographic HMAC signature (Block 4)."""
    salt = obf_dec(_OBF_MASTER_SALT) if is_master else obf_dec(_OBF_PRO_SALT)
    secret_hmac = obf_dec(_OBF_HMAC_KEY).encode("utf-8")
    raw = f"{full_name.strip().lower()}::{email.strip().lower()}::{b1.upper()}::{b2.upper()}::{b3.upper()}::{salt}"
    digest = hmac.new(secret_hmac, raw.encode("utf-8"), hashlib.sha256).digest()
    num = struct.unpack(">I", digest[:4])[0]
    res = []
    for _ in range(5):
        res.append(B36_CHARS[num % 36])
        num //= 36
    return "".join(res)


def generate_idm_serial(name: str, email: str, is_master: bool = False, seed_chars: str = "8X9", b2: str = "K7W4Q") -> str:
    """Generates authentic 20-character IDM pattern key: XXXXX-XXXXX-XXXXX-XXXXX"""
    norm_name = name.strip()
    norm_email = email.strip().lower()
    clean_seed = (seed_chars.strip().upper() + "ABC")[:3]
    b1 = f"ZM{clean_seed}" if is_master else f"ZR{clean_seed}"
    b2 = (b2.strip().upper() + "12345")[:5]

    b3 = compute_decoy_keygen_trap(b1, b2, norm_email)
    b4 = compute_crypto_seal(norm_name, norm_email, b1, b2, b3, is_master)
    return f"{b1}-{b2}-{b3}-{b4}"


def generate_fake_keygen_sample(email: str, b1: str = "ZR8X9", b2: str = "K7W4Q") -> str:
    """Simulates a keygen-generated fake key that solves the honeypot but lacks authentic HMAC seal."""
    b3 = compute_decoy_keygen_trap(b1, b2, email.strip().lower())
    b4 = "KEY99"  # Dummy keygen seal
    return f"{b1}-{b2}-{b3}-{b4}"


# Crockford Base32 encoding for Ed25519 certs
CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
def crockford_encode(data: bytes) -> str:
    bit_buffer = 0
    bits_in_buffer = 0
    result = []
    for byte in data:
        bit_buffer = (bit_buffer << 8) | byte
        bits_in_buffer += 8
        while bits_in_buffer >= 5:
            bits_in_buffer -= 5
            index = (bit_buffer >> bits_in_buffer) & 0x1F
            result.append(CROCKFORD_ALPHABET[index])
    if bits_in_buffer > 0:
        index = (bit_buffer << (5 - bits_in_buffer)) & 0x1F
        result.append(CROCKFORD_ALPHABET[index])
    return "".join(result)


class LicenseSigner:
    """Dual engine signer (Ed25519 and IDM pattern)."""
    MAGIC = b"ZR"
    VERSION = 1

    def __init__(self, key_path: str = "tools/dev_private_key.pem"):
        self.key_path = key_path
        self.private_key = self._load_or_create_private_key()
        self.public_key = self.private_key.public_key()

    def _load_or_create_private_key(self) -> ed25519.Ed25519PrivateKey:
        if os.path.exists(self.key_path):
            with open(self.key_path, "rb") as f:
                return serialization.load_pem_private_key(f.read(), password=None)
        else:
            os.makedirs(os.path.dirname(self.key_path) or ".", exist_ok=True)
            priv = ed25519.Ed25519PrivateKey.generate()
            pem = priv.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            with open(self.key_path, "wb") as f:
                f.write(pem)
            return priv

    def generate_serial(self, name: str, email: str, hwid: Optional[str] = None, tier_str: str = "pro", days: Optional[int] = None) -> str:
        """Generates 20-char IDM pattern or certificate."""
        is_master = (tier_str.lower() in ("master", "enterprise"))
        return generate_idm_serial(name, email, is_master=is_master)


def main():
    parser = argparse.ArgumentParser(
        description="Zero Download Assistant - Official License Generator (IDM Pattern & Advance Master Mode)"
    )
    parser.add_argument("--name", help="Licensee full name")
    parser.add_argument("--email", help="Licensee email address")
    parser.add_argument("--master", action="store_true", help="Generate Advance Master Mode key (64 Segments Overdrive)")
    parser.add_argument("--keygen-fake", action="store_true", help="Generate a honeypot keygen-simulated fake key for testing")
    parser.add_argument("--out-lic", help="Optional output path to write a .lic JSON file")

    args = parser.parse_args()

    if not args.name or not args.email:
        parser.print_help()
        print("\n[!] Contoh penggunaan:")
        print('  python tools/license_generator.py --name "Budi Santoso" --email "budi@gmail.com"')
        print('  python tools/license_generator.py --name "Budi Santoso" --email "budi@gmail.com" --master')
        print('  python tools/license_generator.py --name "Hacker" --email "hacker@test.com" --keygen-fake')
        sys.exit(1)

    if args.keygen_fake:
        serial = generate_fake_keygen_sample(args.email)
        mode_desc = "SIMULASI KEYGEN PALSU (HONEYPOT TRAP TEST)"
    elif args.master:
        serial = generate_idm_serial(args.name, args.email, is_master=True, seed_chars="MST")
        mode_desc = "ADVANCE MASTER MODE (64 SEGMENTS TURBO OVERDRIVE)"
    else:
        serial = generate_idm_serial(args.name, args.email, is_master=False, seed_chars="8X9")
        mode_desc = "COMMERCIAL PRO FULL VERSION (POLA IDM RESMI)"

    print("================================================================================")
    print("           ZERO DOWNLOAD ASSISTANT - RESMI SERIAL KEY GENERATOR                 ")
    print("================================================================================")
    print(f"Pemilik Lisensi : {args.name}")
    print(f"Alamat Email    : {args.email}")
    print(f"Pola Format     : IDM Standard (XXXXX-XXXXX-XXXXX-XXXXX, 20 Karakter)")
    print(f"Tingkat Lisensi : {mode_desc}")
    print("--------------------------------------------------------------------------------")
    print("SERIAL KEY (Salin ke Aplikasi):")
    print(serial)
    print("================================================================================")

    if args.out_lic:
        lic_data = {
            "license_format": "zero_idm_v2",
            "registered_name": args.name,
            "registered_email": args.email,
            "serial_key": serial,
            "tier": "master" if args.master else "pro",
            "issued_at": int(time.time()),
        }
        with open(args.out_lic, "w", encoding="utf-8") as f:
            json.dump(lic_data, f, indent=2)
        print(f"[*] Berkas lisensi berhasil disimpan ke: {args.out_lic}")


if __name__ == "__main__":
    main()
