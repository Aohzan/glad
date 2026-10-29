"""Tests for the notification types registry."""

import datetime

import pytest
from django.core.exceptions import ValidationError

from notifications import registry
from notifications.registry import Event, NotificationType, Param


def test_int_param():
    param = Param("days", "Days", 30, min_value=1, max_value=60)
    assert param.clean("12") == 12
    with pytest.raises(ValidationError):
        param.clean("abc")
    with pytest.raises(ValidationError):
        param.clean(None)
    with pytest.raises(ValidationError, match="at least 1"):
        param.clean("0")
    with pytest.raises(ValidationError, match="at most 60"):
        param.clean("61")


def test_monthday_param():
    param = Param("deadline", "Deadline", "05-20", kind="monthday")
    assert param.clean(" 02-29 ") == "02-29"
    for invalid in ("5-20", "13-01", "02-30", "abc"):
        with pytest.raises(ValidationError):
            param.clean(invalid)


def test_choice_param():
    param = Param(
        "window", "Window", 1, kind="choice", choices=((1, "1 d"), (7, "7 d"))
    )
    assert param.clean("7") == 7
    with pytest.raises(ValidationError):
        param.clean("3")


def test_resolve_params_keeps_valid_values_only():
    notification_type = NotificationType(
        key="t",
        group="finance",
        label="T",
        description="",
        params=(Param("a", "A", 1, min_value=1), Param("b", "B", 2)),
    )
    assert notification_type.default_params() == {"a": 1, "b": 2}
    assert notification_type.resolve_params(None) == {"a": 1, "b": 2}
    assert notification_type.resolve_params({"a": 0, "b": "5", "c": 9}) == {
        "a": 1,
        "b": 5,
    }


def test_dedup_keys():
    once = NotificationType(key="once", group="app", label="", description="")
    again = NotificationType(
        key="again", group="app", label="", description="", renotify_days=7
    )
    event = Event(key="x", title="X")
    day = datetime.date(2026, 10, 28)
    assert once.dedup_key(event, day) == "once:x"
    assert again.dedup_key(event, day) == "again:x@2026-10-28"
    assert len(once.base_key(Event(key="k" * 400, title=""))) == 240


def test_register_rejects_an_unknown_group(sample_types):
    with pytest.raises(ValueError):
        registry.register(
            NotificationType(key="x", group="nope", label="", description="")
        )


def test_grouped_types_follow_the_group_order(sample_types):
    groups = registry.grouped_types()
    assert [str(label) for label, _ in groups] == [
        "Finance",
        "Properties",
        "Application",
    ]
    assert registry.get_type("sample") is sample_types["sample"]


def test_every_type_is_enabled_by_default():
    assert all(t.default_enabled for t in registry.types())


def test_every_app_declares_its_types():
    keys = {t.key for t in registry.types()}
    assert {
        "stale_data",
        "account_drop",
        "income_tax_return",
        "lmnp_return",
        "ledger_checks_pending",
        "app_release",
        "job_failed",
        "email_failed",
    } <= keys
