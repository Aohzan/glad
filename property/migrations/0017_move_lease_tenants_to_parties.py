"""Move the tenant fields of each lease to a tenant party."""

from django.db import migrations


def forward(apps, schema_editor):
    Lease = apps.get_model("property", "Lease")
    LeaseParty = apps.get_model("property", "LeaseParty")
    LeaseParty.objects.bulk_create(
        LeaseParty(
            lease=lease,
            role="tenant",
            first_name=lease.first_name,
            last_name=lease.last_name,
            email=lease.email,
            phone=lease.phone,
        )
        for lease in Lease.objects.all()
        if lease.first_name or lease.last_name
    )


def backward(apps, schema_editor):
    Lease = apps.get_model("property", "Lease")
    LeaseParty = apps.get_model("property", "LeaseParty")
    for lease in Lease.objects.all():
        tenant = (
            LeaseParty.objects.filter(lease=lease, role="tenant").order_by("pk").first()
        )
        if tenant is not None:
            lease.first_name = tenant.first_name
            lease.last_name = tenant.last_name
            lease.email = tenant.email
            lease.phone = tenant.phone
            lease.save(update_fields=["first_name", "last_name", "email", "phone"])


class Migration(migrations.Migration):
    dependencies = [
        ("property", "0016_lease_parties_and_rental_fields"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
