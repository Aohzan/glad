"""Enqueue the periodic jobs when they are due (see ``base.scheduler``)."""

import logging
import signal
import threading
import time

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from base.scheduler import enqueue_due_jobs

logger = logging.getLogger(__name__)

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
        parser.add_argument(
            "--with-worker",
            action="store_true",
            help=(
                "Also run the task worker (db_worker) in this process, which "
                "saves the memory of a second Django process."
            ),
        )

    def handle(self, *args, **options):
        if options["once"]:
            self._tick()
            return
        self.running = True
        if options["with_worker"]:
            # The worker owns the main thread and its stop signals; the
            # scheduler thread ends with the process.
            threading.Thread(target=self._loop, daemon=True).start()
            call_command("db_worker", reload=False)
            return
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT, self._stop)
        self._loop()

    def _loop(self) -> None:
        logger.info("Scheduler started")
        while self.running:
            self._tick()
            for _ in range(INTERVAL):
                if not self.running:
                    break
                time.sleep(1)
        logger.info("Scheduler stopped")

    def _tick(self) -> None:
        close_old_connections()
        try:
            names = enqueue_due_jobs()
        except Exception as exc:  # keep the loop alive on a transient DB error
            logger.error("Could not enqueue the jobs: %s", exc)
            return
        for name in names:
            logger.info("Enqueued %s", name)

    def _stop(self, signum, frame) -> None:
        self.running = False
