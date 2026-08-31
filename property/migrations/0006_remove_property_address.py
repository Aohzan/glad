from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("property", "0005_split_address_field"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="property",
            name="address",
        ),
    ]
