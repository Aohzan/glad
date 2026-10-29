"""Fixtures of the notifications tests."""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from notifications import registry
from notifications.registry import Event, NotificationType, Param

CHECK_CALLS: list[dict] = []


def sample_check(params, today):
    CHECK_CALLS.append(dict(params))
    yield Event(
        key="a", title=f"Alert A {params['threshold']}", body="Body A", url="/a/"
    )
    yield Event(key="b", title="Alert B", level="warning")


def broken_check(params, today):
    raise RuntimeError("boom")


@pytest.fixture
def sample_types():
    """Replace the registered types by a few test types."""
    saved = dict(registry._TYPES)
    registry._TYPES.clear()
    CHECK_CALLS.clear()
    sample = registry.register(
        NotificationType(
            key="sample",
            group="finance",
            label="Sample",
            description="Sample check",
            check=sample_check,
            params=(Param("threshold", "Threshold", 5, min_value=1, max_value=50),),
            default_enabled=False,
        )
    )
    periodic = registry.register(
        NotificationType(
            key="periodic",
            group="property",
            label="Periodic",
            description="Renotified",
            check=lambda params, today: [Event(key="p", title="Periodic")],
            renotify_days=7,
        )
    )
    immediate = registry.register(
        NotificationType(
            key="immediate",
            group="app",
            label="Immediate",
            description="Sent by the code",
        )
    )
    yield {"sample": sample, "periodic": periodic, "immediate": immediate}
    registry._TYPES.clear()
    registry._TYPES.update(saved)


@pytest.fixture
def apprise_mock():
    """Apprise replaced by a mock accepting every URL and message."""
    with patch("apprise.Apprise") as cls:
        sender = MagicMock()
        sender.add.return_value = True
        sender.notify.return_value = True
        cls.return_value = sender
        yield sender


TODAY = datetime.date(2026, 10, 28)
