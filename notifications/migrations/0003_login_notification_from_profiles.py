"""Carry the former "notify on login" email over to the notifications.

A user who received the login email gets an email channel (the account
address, through the SMTP server of the application); a user who had turned
it off gets the login notification turned off.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    UserProfile = apps.get_model("accounts", "UserProfile")
    NotificationChannel = apps.get_model("notifications", "NotificationChannel")
    NotificationPreference = apps.get_model("notifications", "NotificationPreference")
    for profile in UserProfile.objects.select_related("user"):
        user = profile.user
        if profile.is_child:
            continue
        if not profile.notify_on_login:
            NotificationPreference.objects.get_or_create(
                user=user, type_key="login", defaults={"enabled": False}
            )
        elif user.email and not NotificationChannel.objects.filter(
            user=user, kind="email"
        ).exists():
            NotificationChannel.objects.create(user=user, name="Email", kind="email")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_userprofile_is_child_child"),
        ("notifications", "0002_channel_kind"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
