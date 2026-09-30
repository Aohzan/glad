"""Download the latest INSEE index values (IRL, consumer prices)."""

from django.core.management.base import BaseCommand, CommandError

from base.models import EconomicIndex
from base.services.insee import InseeError, refresh_index


class Command(BaseCommand):
    help = "Download the latest INSEE values of the IRL and consumer price index."

    def handle(self, *args, **options):
        failures = []
        for index in EconomicIndex:
            try:
                count = refresh_index(index)
            except InseeError as exc:
                failures.append(index.label)
                self.stderr.write(f"{index.label}: {exc}")
                continue
            self.stdout.write(f"{index.label}: {count} value(s) updated")
        if failures:
            raise CommandError(f"Failed to refresh: {', '.join(map(str, failures))}")
