"""Create ownership rows from the free-text owner of accounts and other assets.

An owner text matching exactly one active user (username, first name or full
name, case-insensitive) becomes a 100 % full ownership of that user. Other
texts (e.g. "Commun") are left as they are.
"""

from django.db import migrations

OWNED_MODELS = (
    ("finance", "savingaccount"),
    ("finance", "investmentaccount"),
    ("finance", "otherasset"),
)


def _match(users, text):
    text = text.strip().casefold()
    if not text:
        return None
    matches = [
        user
        for user in users
        if text
        in {
            user.username.casefold(),
            (user.first_name or "").casefold(),
            f"{user.first_name} {user.last_name}".strip().casefold(),
        }
    ]
    return matches[0] if len(matches) == 1 else None


def forwards(apps, schema_editor):
    user_model = apps.get_model("auth", "User")
    content_type_model = apps.get_model("contenttypes", "ContentType")
    ownership_model = apps.get_model("base", "Ownership")
    users = list(user_model.objects.filter(is_active=True))
    if not users:
        return
    for app_label, model_name in OWNED_MODELS:
        model = apps.get_model(app_label, model_name)
        content_type, _created = content_type_model.objects.get_or_create(
            app_label=app_label, model=model_name
        )
        for obj in model.objects.exclude(owner__isnull=True).exclude(owner=""):
            user = _match(users, obj.owner)
            if user is not None:
                ownership_model.objects.get_or_create(
                    content_type=content_type,
                    object_id=obj.pk,
                    user=user,
                    defaults={"share": 100, "right": "full"},
                )


class Migration(migrations.Migration):
    dependencies = [
        ("base", "0003_ownership"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("finance", "0006_investmentaccount_benchmark"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
