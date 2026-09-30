"""Delete and recompute the monthly net worth snapshots."""

from django.conf import settings
from django.core.management.base import BaseCommand

from base.models import NetWorthSnapshot
from base.services.snapshots import month_starts, net_worth_history


class Command(BaseCommand):
    help = "Delete the stored net worth snapshots and recompute the past months."

    def add_arguments(self, parser):
        parser.add_argument(
            "--years", type=int, default=10, help="Number of years to recompute."
        )
        parser.add_argument(
            "--currency", default=settings.DEFAULT_CURRENCY, help="Currency."
        )

    def handle(self, *args, **options):
        NetWorthSnapshot.objects.all().delete()
        months = month_starts(options["years"] * 12)
        net_worth_history(months, options["currency"])
        count = NetWorthSnapshot.objects.count()
        self.stdout.write(f"{count} snapshot(s) computed")
