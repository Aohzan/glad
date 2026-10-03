from django.db import migrations


def drop_snapshots(apps, schema_editor):
    """Drop the stored net worth history, computed before the loan schedules.

    The loan balances (now read from one schedule per loan, nothing owed
    before the disbursement) and the property net values (no longer floored
    at zero) changed: the snapshots are recomputed on the next request.
    """
    apps.get_model("base", "NetWorthSnapshot").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("base", "0005_ownership_from_remaining_owner_text"),
        ("property", "0015_loan_end_date_last_installment"),
    ]

    operations = [
        migrations.RunPython(drop_snapshots, migrations.RunPython.noop, elidable=True),
    ]
