"""Encrypts the Google refresh token at rest with a key derived from JSTYLE_SECRET_KEY."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def _fernet(secret_key: str) -> Fernet:
    digest = hashlib.sha256(f"jstyle-google-token:{secret_key}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(secret_key: str, value: str) -> str:
    return _fernet(secret_key).encrypt(value.encode()).decode()


def decrypt(secret_key: str, value: str) -> str | None:
    try:
        return _fernet(secret_key).decrypt(value.encode()).decode()
    except InvalidToken:
        return None
