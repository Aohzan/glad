"""Periodic jobs of the base app (see ``base.scheduler``)."""

import datetime

from django.core.management import call_command
from django.tasks import task_backends
from django.utils.translation import gettext_lazy as _
from django_tasks_db.backend import DatabaseBackend

from base.models import EconomicIndex
from base.scheduler import Job, register
from base.services.insee import InseeError, refresh_index


def refresh_economic_indices() -> str:
    """Download the latest INSEE values; raise when one of them fails."""
    counts, failures = [], []
    for index in EconomicIndex:
        try:
            counts.append(f"{index.value}: {refresh_index(index)}")
        except InseeError as exc:
            failures.append(f"{index.value}: {exc}")
    if failures:
        raise InseeError("; ".join(failures))
    return ", ".join(counts)


def prune_task_results() -> str:
    """Forget the results of the background tasks finished a month ago."""
    if not isinstance(task_backends["default"], DatabaseBackend):
        # Tasks run inline (TASKS_BACKEND=immediate): no result is stored.
        return "Nothing to prune: tasks are not stored in the database"
    call_command("prune_db_task_results", min_age_days=30, verbosity=0)
    return ""


def register_jobs() -> None:
    register(
        Job(
            name="refresh_economic_indices",
            func="base.jobs.refresh_economic_indices",
            label=_("Refresh the INSEE indices (IRL, consumer prices)"),
            at=datetime.time(6, 0),
        )
    )
    register(
        Job(
            name="prune_task_results",
            func="base.jobs.prune_task_results",
            label=_("Clean up the finished background tasks"),
            at=datetime.time(3, 0),
        )
    )
