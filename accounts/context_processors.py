"""Context processors for the accounts app."""

from .models import PasskeyCredential


def app_lock(request):
    """Expose app lock state and passkey status for the base template."""
    if not request.user.is_authenticated:
        return {
            "app_lock_enabled": False,
            "show_app_lock_prompt": False,
            "passkey_registered": False,
        }

    try:
        profile = request.user.profile
        enabled = profile.app_lock_enabled
        passkey_registered = PasskeyCredential.objects.filter(
            user=request.user
        ).exists()
        return {
            "app_lock_enabled": enabled,
            # None means the user has never been asked → show the one-time prompt
            "show_app_lock_prompt": enabled is None,
            "passkey_registered": passkey_registered,
        }
    except Exception:
        return {
            "app_lock_enabled": False,
            "show_app_lock_prompt": False,
            "passkey_registered": False,
        }
