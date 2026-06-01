"""Remove biometric_lock_enabled field from UserProfile."""

from django.db import migrations


class Migration(migrations.Migration):
    """Drop the biometric_lock_enabled column from the UserProfile table."""

    dependencies = [
        ("accounts", "0002_passkeycredential"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="userprofile",
            name="biometric_lock_enabled",
        ),
    ]
