"""Tests for the log filters."""

import logging

import pytest

from base.log_filters import SkipHealthChecks


def _access(path: str) -> logging.LogRecord:
    return logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:33752", "GET", path, "1.1", 200),
        None,
    )


@pytest.mark.parametrize(
    ("record", "kept"),
    [
        (_access("/health"), False),
        (_access("/health?x=1"), True),
        (_access("/rental/"), True),
        (logging.LogRecord("x", logging.INFO, __file__, 1, "plain", None, None), True),
    ],
)
def test_skip_health_checks(record, kept):
    assert SkipHealthChecks().filter(record) is kept


def test_settings_apply_the_filter_to_the_access_log():
    handlers_filters = logging.getLogger("uvicorn.access").filters
    assert any(isinstance(f, SkipHealthChecks) for f in handlers_filters)
    assert logging.getLogger("fontTools").level == logging.WARNING
