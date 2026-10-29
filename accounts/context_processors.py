"""Context processors for the accounts app."""

from .models import PasskeyCredential


def session_config(request):
    """Expose the session timeout and the data preferences for the base template."""
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {
            "session_timeout": 15,
            "passkey_registered": False,
            "live_data_enabled": True,
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
            "live_data_enabled": profile.live_data_enabled,
        }
    except Exception:
        return {
            "session_timeout": 15,
            "passkey_registered": False,
            "live_data_enabled": True,
        }
