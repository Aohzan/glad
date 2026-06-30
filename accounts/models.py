"""Models for the accounts app."""

from django.contrib.auth import get_user_model
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

    class Meta:
        verbose_name = _("User profile")
        verbose_name_plural = _("User profiles")

    def __str__(self):
        return f"Profile of {self.user.username}"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Automatically create a UserProfile when a new User is created."""
    if created:
        UserProfile.objects.get_or_create(user=instance)


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
