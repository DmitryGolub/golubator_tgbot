"""Unit tests for src.services.encryption (MultiFernet wrapper)."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

import src.services.encryption as enc
from src.core.config import settings


@pytest.fixture
def caldav_keys(monkeypatch):
    primary = Fernet.generate_key().decode()
    fallback = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "CALDAV_ENABLED", True)
    monkeypatch.setattr(settings, "CALDAV_ENCRYPTION_KEY", primary)
    monkeypatch.setattr(settings, "CALDAV_ENCRYPTION_KEYS_FALLBACK", fallback)
    enc.reset_fernet_cache()
    yield primary, fallback
    enc.reset_fernet_cache()


def test_roundtrip(caldav_keys):
    plain = "s3cr3t app-password 🔑"
    token = enc.encrypt(plain)
    assert token != plain
    assert enc.decrypt(token) == plain


def test_decrypt_with_fallback_key(monkeypatch, caldav_keys):
    primary, fallback = caldav_keys

    # Encrypt with the *old* (fallback) key — simulate a token written before
    # rotation. We do this by temporarily making the fallback the primary.
    monkeypatch.setattr(settings, "CALDAV_ENCRYPTION_KEY", fallback)
    monkeypatch.setattr(settings, "CALDAV_ENCRYPTION_KEYS_FALLBACK", None)
    enc.reset_fernet_cache()
    token_pre_rotation = enc.encrypt("legacy secret")

    # Rotate: new primary with old kept as fallback.
    monkeypatch.setattr(settings, "CALDAV_ENCRYPTION_KEY", primary)
    monkeypatch.setattr(settings, "CALDAV_ENCRYPTION_KEYS_FALLBACK", fallback)
    enc.reset_fernet_cache()

    assert enc.decrypt(token_pre_rotation) == "legacy secret"


def test_decrypt_invalid_token_raises(caldav_keys):
    with pytest.raises(enc.EncryptionError):
        enc.decrypt("not-a-real-fernet-token")


def test_disabled_raises_runtime(monkeypatch):
    monkeypatch.setattr(settings, "CALDAV_ENABLED", False)
    enc.reset_fernet_cache()
    with pytest.raises(RuntimeError):
        enc.encrypt("anything")
