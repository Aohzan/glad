"""Finances application configuration for the Django project."""

from django.apps import AppConfig


class FinanceConfig(AppConfig):
    """Configuration class for the finance app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "finance"

    def ready(self):
        """Import signals when the app is ready."""
        import finance.signals  # noqa: F401
