"""Finances application configuration for the Django project."""

import datetime

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FinanceConfig(AppConfig):
    """Configuration class for the finance app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "finance"

    def ready(self):
        """Import the signals and declare the periodic jobs.

        The jobs are named by their dotted path: their module, which loads the
        market data libraries, is only imported when a job runs.
        """
        import finance.signals  # noqa: F401
        from base.scheduler import Job, register

        register(
            Job(
                name="refresh_security_prices",
                func="finance.jobs.refresh_security_prices",
                label=_("Refresh the security prices"),
                at=datetime.time(7, 0),
            )
        )
