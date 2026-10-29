"""Tests of the API keys."""

import pytest

from mcp_server.models import ApiKey


@pytest.mark.django_db
def test_create_stores_only_the_hash(user):
    key, raw = ApiKey.create(user, "Laptop", can_write=True)
    assert raw.startswith(f"glad_{key.prefix}_")
    assert raw not in key.key_hash
    assert len(key.key_hash) == 64
    assert key.can_write
    assert str(key) == "Laptop"


@pytest.mark.django_db
def test_lookup_finds_the_key(user):
    key, raw = ApiKey.create(user, "Laptop")
    assert ApiKey.lookup(raw) == key


@pytest.mark.django_db
@pytest.mark.parametrize(
    "raw",
    [
        "",
        "nope",
        "glad_",
        "glad_short_secret",
        "other_abcd1234_secret",
        "glad_abcd1234_",
    ],
)
def test_lookup_refuses_malformed_keys(user, raw):
    ApiKey.create(user, "Laptop")
    assert ApiKey.lookup(raw) is None


@pytest.mark.django_db
def test_lookup_refuses_a_wrong_secret(user):
    key, raw = ApiKey.create(user, "Laptop")
    assert ApiKey.lookup(f"glad_{key.prefix}_wrong") is None
    assert ApiKey.lookup(raw + "x") is None


@pytest.mark.django_db
def test_lookup_refuses_a_disabled_key(user):
    key, raw = ApiKey.create(user, "Laptop")
    key.is_active = False
    key.save()
    assert ApiKey.lookup(raw) is None
