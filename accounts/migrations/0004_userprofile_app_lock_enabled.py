"""Add app_lock_enabled field to UserProfile."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add the app_lock_enabled nullable boolean field to UserProfile."""

    dependencies = [
        ("accounts", "0003_remove_userprofile_biometric_lock_enabled"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="app_lock_enabled",
            field=models.BooleanField(
                blank=True,
                default=None,
                help_text="Ask for authentication when reopening the app after inactivity.",
                null=True,
                verbose_name="App lock enabled",
            ),
        ),
    ]
