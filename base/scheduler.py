"""Periodic jobs run in the background by the ``run_scheduler`` command.

A job is a plain function without argument. The scheduler enqueues the
``run_job`` task when a job is due; the task runs the function in the
``db_worker`` process and records the outcome on the job's ``ScheduledJob`` row.

Apps declare their jobs with ``register`` from their ``AppConfig.ready``.
"""

import datetime
import logging
from collections.abc import Callable
from dataclasses import dataclass

from django.db import transaction
from django.dispatch import Signal
from django.tasks import task
from django.utils.functional import Promise
from django.utils.module_loading import import_string

from base.models import ScheduledJob

logger = logging.getLogger(__name__)

#: Sent with ``job`` and ``error`` when a job raises (turned into an alert by
#: the notifications app).
job_failed = Signal()


@dataclass(frozen=True)
class Job:
    """A function run every day at a given time, or at a fixed interval."""

    name: str
    func: str
    label: str | Promise
    at: datetime.time | None = None
    every: datetime.timedelta | None = None
    #: Optional dotted path to a function telling whether a run is needed at all
    #: (a poll with nothing to poll is skipped without being recorded).
    when: str | None = None

    def __post_init__(self) -> None:
        if (self.at is None) == (self.every is None):
            raise ValueError(f"Job {self.name} needs either `at` or `every`")

    @property
    def every_minutes(self) -> int:
        """The interval in minutes (0 for a daily job)."""
        return int(self.every.total_seconds() // 60) if self.every else 0

    def is_due(
        self, last_enqueued_at: datetime.datetime | None, now: datetime.datetime
    ) -> bool:
        """Whether a run should be enqueued at *now* given the previous one.

        A daily job missed while the scheduler was down runs as soon as it is
        back, but only once.
        """
        if self.every is not None:
            return last_enqueued_at is None or now - last_enqueued_at >= self.every
        assert self.at is not None
        slot = datetime.datetime.combine(now.date(), self.at)
        if now < slot:
            return False
        return last_enqueued_at is None or last_enqueued_at < slot

    def should_run(self) -> bool:
        """False when the ``when`` predicate says there is nothing to do."""
        if self.when is None:
            return True
        return bool(import_string(self.when)())


_JOBS: dict[str, Job] = {}


def register(job: Job) -> Job:
    """Declare a periodic job (idempotent, so ``ready`` may run twice)."""
    _JOBS[job.name] = job
    return job


def jobs() -> list[Job]:
    """Every declared job, by name."""
    return sorted(_JOBS.values(), key=lambda job: job.name)


def get_job(name: str) -> Job:
    return _JOBS[name]


def claim(job: Job, now: datetime.datetime, force: bool = False) -> bool:
    """Mark *job* as enqueued at *now* unless another scheduler did it first."""
    state, _ = ScheduledJob.objects.get_or_create(name=job.name)
    if not force and not job.is_due(state.last_enqueued_at, now):
        return False
    claimed = ScheduledJob.objects.filter(
        pk=state.pk, last_enqueued_at=state.last_enqueued_at
    ).update(
        last_enqueued_at=now,
        last_status=ScheduledJob.Status.ENQUEUED,
    )
    return claimed == 1


def enqueue(job: Job, now: datetime.datetime | None = None, force: bool = False):
    """Enqueue *job* when due (or always with *force*); True when enqueued."""
    now = now or datetime.datetime.now()
    if not force and not job.should_run():
        return False
    with transaction.atomic():
        if not claim(job, now, force=force):
            return False
        transaction.on_commit(lambda: run_job.enqueue(job.name))
    return True


def enqueue_due_jobs(now: datetime.datetime | None = None) -> list[str]:
    """Enqueue every due job; the names of the enqueued ones."""
    now = now or datetime.datetime.now()
    return [job.name for job in jobs() if enqueue(job, now)]


@task
def run_job(name: str) -> str:
    """Run the function of job *name* and record how it went."""
    job = get_job(name)
    ScheduledJob.objects.filter(name=name).update(
        last_started_at=datetime.datetime.now(),
        last_status=ScheduledJob.Status.RUNNING,
    )
    func: Callable[[], object] = import_string(job.func)
    try:
        result = func()
    except Exception as exc:
        logger.exception("Job %s failed", name)
        ScheduledJob.objects.filter(name=name).update(
            last_finished_at=datetime.datetime.now(),
            last_status=ScheduledJob.Status.FAILED,
            last_message=f"{type(exc).__name__}: {exc}",
        )
        job_failed.send(sender=Job, job=job, error=exc)
        raise
    message = "" if result is None else str(result)
    ScheduledJob.objects.filter(name=name).update(
        last_finished_at=datetime.datetime.now(),
        last_status=ScheduledJob.Status.SUCCESS,
        last_message=message,
    )
    return message
