from django.db import migrations
from django.db.models import Count, Max
from django.db.models.functions import TruncDate


def drop_same_day_saving_values(apps, schema_editor):
    """Keep the last entered value of each savings account and day.

    The net worth snapshots from the earliest day cleaned are dropped: they
    are recomputed on the next request.
    """
    values = apps.get_model("finance", "SavingAccountValue")
    duplicates = (
        values.objects.annotate(day=TruncDate("value_date"))
        .values("account_id", "day")
        .annotate(count=Count("id"), last=Max("id"))
        .filter(count__gt=1)
    )
    earliest = None
    for row in duplicates:
        values.objects.filter(
            account_id=row["account_id"], value_date__date=row["day"]
        ).exclude(pk=row["last"]).delete()
        earliest = min(earliest or row["day"], row["day"])
    if earliest is not None:
        snapshots = apps.get_model("base", "NetWorthSnapshot")
        snapshots.objects.filter(month__gte=earliest).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0012_one_cash_value_per_date"),
    ]

    operations = [
        migrations.RunPython(
            drop_same_day_saving_values, migrations.RunPython.noop, elidable=True
        ),
    ]
