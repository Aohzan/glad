"""Add management_fee_rate and notes fields to SCPI model."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("property", "0038_scpi_scpiinvestment_scpidividend_scpishareprice"),
    ]

    operations = [
        migrations.AddField(
            model_name="scpi",
            name="management_fee_rate",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Annual management fee as a percentage, e.g. 10.00 for 10%.",
                max_digits=5,
                null=True,
                verbose_name="Management fee rate (%)",
            ),
        ),
        migrations.AddField(
            model_name="scpi",
            name="notes",
            field=models.TextField(blank=True, default="", verbose_name="Notes"),
        ),
    ]
