"""Migration: attach SCPIDividend directly to SCPI fund instead of SCPIInvestment.

This migration:
1. Adds a nullable `scpi` FK to SCPIDividend
2. Populates it from each dividend's investment.scpi (data migration)
3. Makes `scpi` non-nullable
4. Removes the `investment` FK
"""

import django.db.models.deletion
from django.db import migrations, models


def populate_scpi_from_investment(apps, schema_editor):
    SCPIDividend = apps.get_model("property", "SCPIDividend")
    for dividend in SCPIDividend.objects.select_related("investment__scpi").all():
        if dividend.investment_id is not None:
            dividend.scpi = dividend.investment.scpi
            dividend.save(update_fields=["scpi"])


class Migration(migrations.Migration):
    dependencies = [
        ("property", "0041_add_scpi_dividend_recurrence"),
    ]

    operations = [
        # Step 1: add nullable scpi FK
        migrations.AddField(
            model_name="scpidividend",
            name="scpi",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="dividends",
                to="property.scpi",
                verbose_name="SCPI",
            ),
        ),
        # Step 2: populate scpi from existing investment.scpi
        migrations.RunPython(
            populate_scpi_from_investment,
            reverse_code=migrations.RunPython.noop,
        ),
        # Step 3: make scpi non-nullable
        migrations.AlterField(
            model_name="scpidividend",
            name="scpi",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="dividends",
                to="property.scpi",
                verbose_name="SCPI",
            ),
        ),
        # Step 4: remove investment FK
        migrations.RemoveField(
            model_name="scpidividend",
            name="investment",
        ),
    ]
