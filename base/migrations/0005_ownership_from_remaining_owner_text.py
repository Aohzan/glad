"""Turn the last free-text owners into ownership rows before the field is dropped.

Only the assets without any ownership row are considered:

- a text matching exactly one active user (username, first name or full name,
  case-insensitive) becomes a 100 % full ownership of that user;
- a text naming the household as a whole ("Commun", "Joint", "Foyer"…) is split
  equally in full ownership between the active adults;
- any other text is dropped: the asset is left without owner, flagged on its
  page until its owners are chosen.
"""

from decimal import ROUND_DOWN, Decimal

from django.db import migrations

OWNED_MODELS = (
    ("finance", "savingaccount"),
    ("finance", "investmentaccount"),
    ("finance", "otherasset"),
)

JOINT_TEXTS = {
    "commun",
    "commune",
    "communs",
    "en commun",
    "foyer",
    "famille",
    "couple",
    "indivision",
    "joint",
    "common",
    "household",
    "family",
}


def _match(users, text):
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


def _split(count):
    part = (Decimal(100) / count).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    return [part] * (count - 1) + [Decimal(100) - part * (count - 1)]


def forwards(apps, schema_editor):
    user_model = apps.get_model("auth", "User")
    profile_model = apps.get_model("accounts", "UserProfile")
    content_type_model = apps.get_model("contenttypes", "ContentType")
    ownership_model = apps.get_model("base", "Ownership")
    users = list(user_model.objects.filter(is_active=True).order_by("pk"))
    children = set(
        profile_model.objects.filter(is_child=True).values_list("user_id", flat=True)
    )
    adults = [user for user in users if user.pk not in children]
    for app_label, model_name in OWNED_MODELS:
        model = apps.get_model(app_label, model_name)
        content_type, _created = content_type_model.objects.get_or_create(
            app_label=app_label, model=model_name
        )
        owned = set(
            ownership_model.objects.filter(content_type=content_type).values_list(
                "object_id", flat=True
            )
        )
        for obj in model.objects.exclude(owner__isnull=True).exclude(owner=""):
            text = obj.owner.strip().casefold()
            if obj.pk in owned or not text:
                continue
            user = _match(users, text)
            if user is not None:
                owners = [user]
            elif text in JOINT_TEXTS and adults:
                owners = adults
            else:
                continue
            for owner, share in zip(owners, _split(len(owners)), strict=True):
                ownership_model.objects.create(
                    content_type=content_type,
                    object_id=obj.pk,
                    user=owner,
                    share=share,
                    right="full",
                )


class Migration(migrations.Migration):
    dependencies = [
        ("base", "0004_ownership_from_owner_text"),
        ("accounts", "0006_userprofile_is_child_child"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("finance", "0006_investmentaccount_benchmark"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
