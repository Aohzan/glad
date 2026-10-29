"""Configuration of the rental app."""

import datetime

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class RentalConfig(AppConfig):
    """Self-managed rental: tenants, documents, compliance of the leases."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "rental"
    verbose_name = _("Rental management")

    def ready(self):
        """Declare the periodic jobs, by their dotted path (imported when they run)."""
        from base.scheduler import Job, register

        register(
            Job(
                name="rental_daily",
                func="rental.jobs.send_rent_emails",
                label=_("Send the rent calls and receipts"),
                at=datetime.time(7, 30),
            )
        )
        register(
            Job(
                name="poll_signatures",
                func="rental.services.signature.poll_signatures",
                label=_("Check the electronic signatures"),
                every=datetime.timedelta(minutes=15),
                when="rental.services.signature.has_pending",
            )
        )
