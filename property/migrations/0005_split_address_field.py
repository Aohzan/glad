"""Best-effort parse of the legacy free-text ``address`` field into structured fields."""

import re

from django.db import migrations

# Matches "12 rue de la Liberté, 75014 Paris, France" style addresses.
# The leading house number is optional (e.g. "Le Bourg, 24200 Sarlat-la-Canéda, France").
ADDRESS_PATTERN = re.compile(
    r"^(?:(?P<number>\d+(?:\s?(?:bis|ter|quater))?)\s+)?(?P<street>.*?),\s*"
    r"(?P<postal>\d{5})\s+(?P<city>[^,]+?)(?:,\s*(?P<country>.+))?$"
)


def split_addresses(apps, schema_editor):
    Property = apps.get_model("property", "Property")
    for prop in Property.objects.exclude(address__isnull=True).exclude(address=""):
        match = ADDRESS_PATTERN.match(prop.address.strip())
        if match:
            prop.street_number = match.group("number") or None
            prop.street_name = match.group("street") or None
            prop.postal_code = match.group("postal")
            prop.city = match.group("city").strip()
            prop.country = match.group("country") or "France"
        else:
            # Unparsable: keep the original text so no information is lost.
            prop.street_name = prop.address
        prop.save(
            update_fields=[
                "street_number",
                "street_name",
                "postal_code",
                "city",
                "country",
            ]
        )


def merge_addresses(apps, schema_editor):
    Property = apps.get_model("property", "Property")
    for prop in Property.objects.all():
        parts = [
            part
            for part in (
                " ".join(p for p in (prop.street_number, prop.street_name) if p).strip()
                or None,
                f"{prop.postal_code} {prop.city}".strip()
                if prop.postal_code or prop.city
                else None,
                prop.country if prop.country != "France" else None,
            )
            if part
        ]
        if parts:
            prop.address = ", ".join(parts)
            prop.save(update_fields=["address"])


class Migration(migrations.Migration):
    dependencies = [
        ("property", "0004_add_address_and_cadastral_fields"),
    ]

    operations = [
        migrations.RunPython(split_addresses, merge_addresses),
    ]
