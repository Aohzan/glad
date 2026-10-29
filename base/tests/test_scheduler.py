"""Tests for the periodic jobs scheduler."""

import datetime
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.urls import reverse
from django_tasks_db.backend import DatabaseBackend

from base import jobs as base_jobs
from base import scheduler
from base.models import ScheduledJob
from base.scheduler import Job, enqueue, enqueue_due_jobs, job_failed, register
from base.services.insee import InseeError

NOW = datetime.datetime(2026, 10, 28, 9, 30)
CALLS: list[str] = []


def ok_job() -> str:
    CALLS.append("ok")
    return "done"


def failing_job() -> None:
    raise RuntimeError("boom")


def nothing_to_do() -> bool:
    return False


@pytest.fixture
def test_jobs():
    """Register throwaway jobs and remove them afterwards."""
    saved = dict(scheduler._JOBS)
    scheduler._JOBS.clear()
    CALLS.clear()
    ok = register(
        Job(name="ok", func=f"{__name__}.ok_job", label="OK", at=datetime.time(8))
    )
    failing = register(
        Job(
            name="failing",
            func=f"{__name__}.failing_job",
            label="Failing",
            every=datetime.timedelta(minutes=15),
        )
    )
    yield ok, failing
    scheduler._JOBS.clear()
    scheduler._JOBS.update(saved)


def test_job_needs_one_schedule():
    with pytest.raises(ValueError):
        Job(name="x", func="x", label="x")
    with pytest.raises(ValueError):
        Job(
            name="x",
            func="x",
            label="x",
            at=datetime.time(8),
            every=datetime.timedelta(hours=1),
        )


def test_daily_job_is_due_once_after_its_time():
    job = Job(name="d", func="x", label="d", at=datetime.time(8))
    assert not job.is_due(None, NOW.replace(hour=7))
    assert job.is_due(None, NOW)
    assert job.is_due(NOW - datetime.timedelta(days=1), NOW)
    assert not job.is_due(NOW.replace(hour=8, minute=1), NOW)
    assert job.every_minutes == 0


def test_daily_job_missed_runs_when_the_scheduler_is_back():
    job = Job(name="d", func="x", label="d", at=datetime.time(8))
    last = NOW - datetime.timedelta(days=3)
    assert job.is_due(last, NOW.replace(hour=23))


def test_interval_job_is_due_after_its_interval():
    job = Job(name="i", func="x", label="i", every=datetime.timedelta(minutes=15))
    assert job.every_minutes == 15
    assert job.is_due(None, NOW)
    assert not job.is_due(NOW - datetime.timedelta(minutes=10), NOW)
    assert job.is_due(NOW - datetime.timedelta(minutes=15), NOW)


@pytest.mark.django_db
def test_enqueue_runs_the_job_and_records_success(
    test_jobs, django_capture_on_commit_callbacks
):
    ok, _ = test_jobs
    with django_capture_on_commit_callbacks(execute=True):
        assert enqueue(ok, NOW)
    state = ScheduledJob.objects.get(name="ok")
    assert state.last_status == ScheduledJob.Status.SUCCESS
    assert state.last_message == "done"
    assert state.last_enqueued_at == NOW
    assert state.last_started_at is not None
    assert state.last_finished_at is not None
    assert CALLS == ["ok"]


@pytest.mark.django_db
def test_enqueue_never_runs_the_same_slot_twice(
    test_jobs, django_capture_on_commit_callbacks
):
    ok, _ = test_jobs
    with django_capture_on_commit_callbacks(execute=True):
        assert enqueue(ok, NOW)
        assert not enqueue(ok, NOW + datetime.timedelta(minutes=1))
    assert CALLS == ["ok"]


@pytest.mark.django_db
def test_claim_loses_against_a_concurrent_scheduler(test_jobs):
    ok, _ = test_jobs
    ScheduledJob.objects.create(name="ok")
    real_filter = ScheduledJob.objects.filter

    def concurrent_filter(*args, **kwargs):
        # Another scheduler claimed the run between the read and the update.
        ScheduledJob.objects.all().update(last_enqueued_at=NOW)
        return real_filter(*args, **kwargs)

    with patch.object(ScheduledJob.objects, "filter", side_effect=concurrent_filter):
        assert not scheduler.claim(ok, NOW)


@pytest.mark.django_db
def test_force_enqueues_a_job_that_is_not_due(
    test_jobs, django_capture_on_commit_callbacks
):
    ok, _ = test_jobs
    with django_capture_on_commit_callbacks(execute=True):
        assert enqueue(ok, NOW.replace(hour=6), force=True)
    assert CALLS == ["ok"]


@pytest.mark.django_db
def test_failing_job_is_recorded_and_signalled(
    test_jobs, django_capture_on_commit_callbacks
):
    _, failing = test_jobs
    received = []

    def handler(sender, job, error, **kwargs):
        received.append((job.name, str(error)))

    job_failed.connect(handler)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            enqueue(failing, NOW)
    finally:
        job_failed.disconnect(handler)
    state = ScheduledJob.objects.get(name="failing")
    assert state.last_status == ScheduledJob.Status.FAILED
    assert state.last_message == "RuntimeError: boom"
    assert received == [("failing", "boom")]


@pytest.mark.django_db
def test_job_with_nothing_to_do_is_skipped(test_jobs):
    job = register(
        Job(
            name="idle",
            func=f"{__name__}.ok_job",
            label="Idle",
            every=datetime.timedelta(minutes=15),
            when=f"{__name__}.nothing_to_do",
        )
    )
    assert not enqueue(job, NOW)
    assert not ScheduledJob.objects.filter(name="idle").exists()


@pytest.mark.django_db
def test_enqueue_due_jobs_returns_the_enqueued_names(
    test_jobs, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        assert enqueue_due_jobs(NOW) == ["failing", "ok"]
        assert enqueue_due_jobs(NOW) == []


@pytest.mark.django_db
def test_run_scheduler_once(test_jobs, capsys, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        call_command("run_scheduler", "--once")
    out = capsys.readouterr().out
    assert "Enqueued failing" in out


@pytest.mark.django_db
def test_run_scheduler_survives_a_database_error(test_jobs, capsys):
    with patch(
        "base.management.commands.run_scheduler.enqueue_due_jobs",
        side_effect=RuntimeError("locked"),
    ):
        call_command("run_scheduler", "--once")
    assert "Could not enqueue the jobs: locked" in capsys.readouterr().err


@pytest.mark.django_db
def test_run_scheduler_loop_stops_on_signal(test_jobs, capsys):
    from base.management.commands import run_scheduler

    command = run_scheduler.Command()

    def stop_after_first_sleep(seconds):
        command._stop(None, None)

    with (
        patch.object(run_scheduler, "enqueue_due_jobs", return_value=[]),
        patch.object(run_scheduler.time, "sleep", side_effect=stop_after_first_sleep),
        patch.object(run_scheduler.signal, "signal"),
    ):
        call_command(command)
    out = capsys.readouterr().out
    assert "Scheduler started" in out
    assert "Scheduler stopped" in out


@pytest.mark.django_db
def test_run_scheduler_with_the_worker(test_jobs, capsys):
    from base.management.commands import run_scheduler

    command = run_scheduler.Command()
    started = []

    class FakeThread:
        def __init__(self, target, daemon):
            assert daemon
            started.append(target)

        def start(self):
            command.running = False
            started[0]()

    with (
        patch.object(run_scheduler.threading, "Thread", FakeThread),
        patch.object(run_scheduler, "call_command") as worker,
        patch.object(run_scheduler, "enqueue_due_jobs", return_value=[]),
    ):
        call_command(command, "--with-worker")
    worker.assert_called_once_with("db_worker", reload=False)
    assert "Scheduler started" in capsys.readouterr().out


def test_base_jobs_are_registered():
    names = {job.name for job in scheduler.jobs()}
    assert {"refresh_economic_indices", "prune_task_results"} <= names


@pytest.mark.django_db
def test_refresh_economic_indices_job():
    with patch.object(base_jobs, "refresh_index", return_value=2):
        assert base_jobs.refresh_economic_indices() == "irl: 2, cpi: 2"


@pytest.mark.django_db
def test_refresh_economic_indices_job_raises_on_failure():
    with (
        patch.object(base_jobs, "refresh_index", side_effect=InseeError("down")),
        pytest.raises(InseeError, match="irl: down; cpi: down"),
    ):
        base_jobs.refresh_economic_indices()


def test_prune_task_results_job_with_the_database_backend():
    backends = {"default": DatabaseBackend("default", {})}
    with (
        patch.object(base_jobs, "task_backends", backends),
        patch.object(base_jobs, "call_command") as mock,
    ):
        assert base_jobs.prune_task_results() == ""
    mock.assert_called_once_with("prune_db_task_results", min_age_days=30, verbosity=0)


def test_prune_task_results_job_without_stored_tasks():
    # Tests run tasks inline (TASKS_BACKEND=immediate): nothing is stored.
    with patch.object(base_jobs, "call_command") as mock:
        assert base_jobs.prune_task_results().startswith("Nothing to prune")
    mock.assert_not_called()


@pytest.mark.django_db
def test_settings_page_lists_the_jobs_for_a_superuser(admin_client, test_jobs):
    ScheduledJob.objects.create(
        name="failing", last_status=ScheduledJob.Status.FAILED, last_message="boom"
    )
    response = admin_client.get(reverse("accounts:settings"))
    assert response.status_code == 200
    content = response.content.decode()
    assert 'id="background-jobs"' in content
    assert "Every 15 min" in content
    assert "Daily at 08:00" in content


@pytest.mark.django_db
def test_settings_page_hides_the_jobs_from_other_users(user_client):
    response = user_client.get(reverse("accounts:settings"))
    assert 'id="background-jobs"' not in response.content.decode()


@pytest.mark.django_db
def test_run_scheduled_job_view(admin_client, test_jobs):
    response = admin_client.post(reverse("run_scheduled_job", args=["ok"]))
    assert response.status_code == 302
    assert response.url.endswith("#background-jobs")
    assert ScheduledJob.objects.get(name="ok").last_status


@pytest.mark.django_db
def test_run_scheduled_job_view_unknown_job(admin_client, test_jobs):
    response = admin_client.post(reverse("run_scheduled_job", args=["nope"]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_run_scheduled_job_view_requires_a_superuser(user_client, test_jobs):
    response = user_client.post(reverse("run_scheduled_job", args=["ok"]))
    assert response.status_code == 302
    assert not ScheduledJob.objects.filter(name="ok").exists()
