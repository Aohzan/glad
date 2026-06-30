"""Context processors for the accounts app."""

from .models import PasskeyCredential


def session_config(request):
    """Expose session timeout and notification configuration for the base template."""
    if not request.user.is_authenticated:
        return {
            "session_timeout": 15,
            "passkey_registered": False,
            "notify_on_login": True,
        }

    try:
        profile = request.user.profile
        timeout = profile.session_timeout
        passkey_registered = PasskeyCredential.objects.filter(
            user=request.user
        ).exists()
        return {
            "session_timeout": timeout,
            "passkey_registered": passkey_registered,
            "notify_on_login": profile.notify_on_login,
        }
    except Exception:
        return {
            "session_timeout": 15,
            "passkey_registered": False,
            "notify_on_login": True,
        }
