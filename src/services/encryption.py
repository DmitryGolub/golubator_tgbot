"""Symmetric encryption for CalDAV credentials.

Uses `cryptography.fernet.MultiFernet` so keys can be rotated without a
migration: pass the new key as primary + old keys as fallback. New writes
use the primary; decryption tries each key in order.
"""

from __future__ import annotations

import threading
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from src.core.config import settings


class EncryptionError(Exception):
    """Raised when encrypt/decrypt fails (bad key, tampered ciphertext, etc.)."""


_fernet: Optional[MultiFernet] = None
_lock = threading.Lock()


def _build_fernet() -> MultiFernet:
    if not settings.CALDAV_ENABLED:
        raise RuntimeError("encryption disabled (CALDAV_ENABLED=False)")
    if not settings.CALDAV_ENCRYPTION_KEY:
        raise RuntimeError("CALDAV_ENCRYPTION_KEY is not set")
    try:
        primary = Fernet(settings.CALDAV_ENCRYPTION_KEY.encode())
    except Exception as exc:
        raise EncryptionError(f"invalid CALDAV_ENCRYPTION_KEY: {exc}") from exc

    keys: list[Fernet] = [primary]
    for raw in settings.caldav_fallback_keys:
        try:
            keys.append(Fernet(raw.encode()))
        except Exception as exc:
            raise EncryptionError(
                f"invalid fallback key in CALDAV_ENCRYPTION_KEYS_FALLBACK: {exc}"
            ) from exc
    return MultiFernet(keys)


def _get_fernet() -> MultiFernet:
    global _fernet
    if _fernet is None:
        with _lock:
            if _fernet is None:
                _fernet = _build_fernet()
    return _fernet


def reset_fernet_cache() -> None:
    """Test-only helper: drop the singleton so config changes are re-read."""
    global _fernet
    with _lock:
        _fernet = None


def encrypt(plaintext: str) -> str:
    if plaintext is None:
        raise EncryptionError("cannot encrypt None")
    fernet = _get_fernet()
    try:
        return fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
    except Exception as exc:
        raise EncryptionError(f"encrypt failed: {exc}") from exc


def decrypt(ciphertext: str) -> str:
    if not ciphertext:
        raise EncryptionError("cannot decrypt empty ciphertext")
    fernet = _get_fernet()
    try:
        return fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise EncryptionError("invalid or tampered ciphertext") from exc
    except Exception as exc:
        raise EncryptionError(f"decrypt failed: {exc}") from exc
