"""Configuration of the rental app."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class RentalConfig(AppConfig):
    """Self-managed rental: tenants, documents, compliance of the leases."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "rental"
    verbose_name = _("Rental management")

    def ready(self):
        """Declare the daily job."""
        from rental.jobs import register_jobs

        register_jobs()
