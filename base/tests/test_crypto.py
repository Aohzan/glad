"""Tests for the encryption of the stored secrets."""

from base.services.crypto import decrypt, encrypt


def test_round_trip():
    token = encrypt("ntfy://user:pass@host/topic")
    assert "pass" not in token
    assert decrypt(token) == "ntfy://user:pass@host/topic"


def test_unreadable_tokens(settings):
    token = encrypt("secret")
    settings.SECRET_KEY = "another key"
    assert decrypt(token) is None
    assert decrypt("not a token") is None
