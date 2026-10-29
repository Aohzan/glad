"""Encryption of the secrets stored in the database (notification URLs…).

The key derives from SECRET_KEY: changing it makes the stored secrets
unreadable, which ``decrypt`` reports as None instead of raising.
"""

import base64
import hashlib

from django.conf import settings
lazy from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet:
    digest = hashlib.sha256(f"glad-secrets:{settings.SECRET_KEY}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    """Encrypt *value* into an ASCII token."""
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str | None:
    """Decrypt a token from ``encrypt``; None when it cannot be read."""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken, ValueError:
        return None
