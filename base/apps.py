"""Base application configuration for the Django project."""

from django.apps import AppConfig


class BaseConfig(AppConfig):
    """Configuration class for the base app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "base"

    def ready(self):
        """Connect the net worth snapshot invalidation signals."""
        import base.signals  # noqa: F401
