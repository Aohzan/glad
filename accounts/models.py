"""Models for the accounts app."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import UserManager
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class UserProfile(models.Model):
    """Extended profile for the user."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    session_timeout = models.PositiveIntegerField(
        default=15,
        verbose_name=_("Session timeout (minutes)"),
        help_text=_(
            "Auto-logout after this many minutes of inactivity. Default: 15 minutes."
        ),
    )
    notify_on_login = models.BooleanField(
        default=True,
        verbose_name=_("Notify on login"),
        help_text=_("Receive an email notification when you log in."),
    )
    live_data_enabled = models.BooleanField(
        default=True,
        verbose_name=_("Enable live market data"),
        help_text=_(
            "Fetch real-time market data from Yahoo Finance for holdings and "
            "ISIN autofill. Disable to avoid external network calls."
        ),
    )

    birth_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Birth date"),
        help_text=_("Used to value a life usufruct (article 669 CGI)."),
    )
    is_child = models.BooleanField(
        default=False,
        verbose_name=_("Child"),
        help_text=_("A child is a household member who cannot log in."),
    )
    monthly_expenses = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Monthly expenses"),
        help_text=_(
            "Usual household spending per month, used to size the emergency fund."
        ),
    )

    class Meta:
        verbose_name = _("User profile")
        verbose_name_plural = _("User profiles")

    def __str__(self):
        return f"Profile of {self.user.username}"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, raw=False, **kwargs):
    """Automatically create a UserProfile when a new User is created.

    Fixtures (*raw* saves) carry their own profile rows.
    """
    if created and not raw:
        UserProfile.objects.get_or_create(user=instance)


def is_child(user) -> bool:
    """True when *user* is a child of the household (who cannot log in)."""
    return bool(getattr(getattr(user, "profile", None), "is_child", False))


class ChildManager(UserManager):
    """Users flagged as children."""

    def get_queryset(self):
        return super().get_queryset().filter(profile__is_child=True)


class Child(User):  # ty: ignore[unsupported-base]
    """A child of the household: an owner of assets who cannot log in."""

    objects = ChildManager()

    class Meta:
        proxy = True
        verbose_name = _("Child")
        verbose_name_plural = _("Children")


class PasskeyCredential(models.Model):
    """WebAuthn passkey credential stored per user."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="passkey_credential"
    )
    credential_id = models.TextField(unique=True)
    public_key = models.TextField()
    sign_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Passkey credential")
        verbose_name_plural = _("Passkey credentials")

    def __str__(self):
        return f"Passkey for {self.user.username}"
