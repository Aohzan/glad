"""Finances application configuration for the Django project."""

from django.apps import AppConfig


class FinanceConfig(AppConfig):
    """Configuration class for the finance app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "finance"

    def ready(self):
        """Import the signals and declare the periodic jobs."""
        import finance.signals  # noqa: F401
        from finance.jobs import register_jobs

        register_jobs()
