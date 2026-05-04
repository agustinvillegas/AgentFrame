from __future__ import annotations
import os
import base64
from pathlib import Path
from cryptography.fernet import Fernet


_KEY_PATH = Path(__file__).resolve().parent.parent / "data" / ".secret.key"


def _load_or_create_key() -> bytes:
    if _KEY_PATH.exists():
        return _KEY_PATH.read_bytes()
    key = Fernet.generate_key()
    _KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _KEY_PATH.write_bytes(key)
    return key


_fernet = Fernet(_load_or_create_key())


def encrypt(value: str) -> str:
    return _fernet.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return _fernet.decrypt(value.encode()).decode()