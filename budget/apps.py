"""Budget application configuration for the Django project."""

from django.apps import AppConfig


class BudgetConfig(AppConfig):
    """Configuration class for the budget app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "budget"
