"""Enqueue the periodic jobs when they are due (see ``base.scheduler``)."""

import signal
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from base.scheduler import enqueue_due_jobs

#: Seconds between two looks at the jobs.
INTERVAL = 60


class Command(BaseCommand):
    help = (
        "Enqueue the periodic jobs that are due, every minute. The db_worker "
        "command runs them."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Enqueue the due jobs once and exit (for an external cron).",
        )

    def handle(self, *args, **options):
        if options["once"]:
            self._tick()
            return
        self.running = True
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT, self._stop)
        self.stdout.write("Scheduler started")
        while self.running:
            self._tick()
            for _ in range(INTERVAL):
                if not self.running:
                    break
                time.sleep(1)
        self.stdout.write("Scheduler stopped")

    def _tick(self) -> None:
        close_old_connections()
        try:
            names = enqueue_due_jobs()
        except Exception as exc:  # keep the loop alive on a transient DB error
            self.stderr.write(f"Could not enqueue the jobs: {exc}")
            return
        for name in names:
            self.stdout.write(f"Enqueued {name}")

    def _stop(self, signum, frame) -> None:
        self.running = False
