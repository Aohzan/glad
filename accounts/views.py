"""Views for the accounts app."""

import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_not_required, login_required
from django.contrib.auth.forms import PasswordChangeForm, UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, FormView, TemplateView
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import (
    base64url_to_bytes,
    bytes_to_base64url,
    parse_authentication_credential_json,
    parse_registration_credential_json,
)
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .models import PasskeyCredential, UserProfile


class SignUpView(CreateView):
    """View for user registration."""

    form_class = UserCreationForm
    success_url = reverse_lazy("login")
    template_name = "registration/signup.html"


class LogoutConfirmView(TemplateView):
    """View to confirm user logout."""

    template_name = "logout.html"


class SettingsView(LoginRequiredMixin, FormView):
    """View for user settings."""

    template_name = "accounts/settings.html"
    form_class = PasswordChangeForm
    success_url = reverse_lazy("accounts:settings")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        update_session_auth_hash(self.request, form.user)
        messages.success(self.request, _("Password updated successfully."))
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["passkey_registered"] = PasskeyCredential.objects.filter(
            user=self.request.user
        ).exists()
        return context


def _get_rp_id(request):
    """Get the Relying Party ID for WebAuthn."""
    configured = getattr(settings, "WEBAUTHN_RP_ID", None)
    if configured:
        return configured

    # Extract hostname without port
    host = request.get_host().split(":")[0]

    # For localhost, we can use it directly (special-cased in WebAuthn)
    if host in ("localhost", "127.0.0.1"):
        return "localhost"

    return host


def _get_origin(request):
    """Get the expected origin for WebAuthn."""
    configured = getattr(settings, "WEBAUTHN_ORIGIN", None)
    if configured:
        return configured
    return f"{request.scheme}://{request.get_host()}"


def _store_challenge(request, key, challenge):
    request.session[key] = (
        challenge.decode("latin-1") if isinstance(challenge, bytes) else challenge
    )


def _load_challenge(request, key):
    stored = request.session.get(key)
    if not stored:
        return None
    return stored.encode("latin-1") if isinstance(stored, str) else stored


@login_required
@require_POST
def passkey_register_options(request):
    """Generate WebAuthn registration options for the current user."""
    try:
        options = generate_registration_options(
            rp_id=_get_rp_id(request),
            rp_name="Glad",
            user_id=str(request.user.pk).encode("utf-8"),
            user_name=request.user.username,
            user_display_name=request.user.get_full_name() or request.user.username,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
            attestation=AttestationConveyancePreference.NONE,
        )

        _store_challenge(request, "passkey_register_challenge", options.challenge)
        return JsonResponse(json.loads(options_to_json(options)))
    except Exception as e:
        return JsonResponse(
            {"success": False, "error": f"Failed to generate options: {str(e)}"},
            status=500,
        )


@login_required
@require_POST
def passkey_register_complete(request):
    """Verify registration and store the passkey for the current user."""
    try:
        challenge = _load_challenge(request, "passkey_register_challenge")
        if not challenge:
            return JsonResponse(
                {"success": False, "error": "missing_challenge"}, status=400
            )

        payload = json.loads(request.body or "{}")
        credential = parse_registration_credential_json(json.dumps(payload))

        verification = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_origin=_get_origin(request),
            expected_rp_id=_get_rp_id(request),
        )

        PasskeyCredential.objects.update_or_create(
            user=request.user,
            defaults={
                "credential_id": bytes_to_base64url(verification.credential_id),
                "public_key": bytes_to_base64url(verification.credential_public_key),
                "sign_count": verification.sign_count,
            },
        )

        request.session.pop("passkey_register_challenge", None)
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_not_required
@require_POST
def passkey_auth_options(request):
    """Generate WebAuthn authentication options."""
    try:
        options = generate_authentication_options(
            rp_id=_get_rp_id(request),
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        _store_challenge(request, "passkey_auth_challenge", options.challenge)
        return JsonResponse(json.loads(options_to_json(options)))
    except Exception as e:
        return JsonResponse(
            {"success": False, "error": f"Failed to generate options: {str(e)}"},
            status=500,
        )


@login_not_required
@require_POST
def passkey_auth_complete(request):
    """Verify authentication and log the user in using the passkey."""
    try:
        challenge = _load_challenge(request, "passkey_auth_challenge")
        if not challenge:
            return JsonResponse(
                {"success": False, "error": "missing_challenge"}, status=400
            )

        payload = json.loads(request.body or "{}")
        credential = parse_authentication_credential_json(json.dumps(payload))

        stored = (
            PasskeyCredential.objects.select_related("user")
            .filter(credential_id=credential.id)
            .first()
        )
        if not stored:
            return JsonResponse(
                {"success": False, "error": "unknown_credential"}, status=400
            )

        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_origin=_get_origin(request),
            expected_rp_id=_get_rp_id(request),
            credential_public_key=base64url_to_bytes(stored.public_key),
            credential_current_sign_count=stored.sign_count,
        )

        stored.sign_count = verification.new_sign_count
        stored.save(update_fields=["sign_count"])

        request.session.pop("passkey_auth_challenge", None)
        login(request, stored.user)
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_POST
def passkey_delete(request):
    """Remove the stored passkey for the current user."""
    PasskeyCredential.objects.filter(user=request.user).delete()
    return JsonResponse({"success": True})


@login_required
@require_POST
def toggle_app_lock(request):
    """Enable or disable the app lock feature for the current user."""
    try:
        data = json.loads(request.body or "{}")
        enabled = data.get("enabled")
        if enabled is None:
            return JsonResponse(
                {"success": False, "error": "missing_enabled"}, status=400
            )
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        profile.app_lock_enabled = bool(enabled)
        profile.save(update_fields=["app_lock_enabled"])
        return JsonResponse(
            {"success": True, "app_lock_enabled": profile.app_lock_enabled}
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_POST
def password_verify(request):
    """Verify the current user's password (used by the app lock screen)."""
    try:
        data = json.loads(request.body or "{}")
        password = data.get("password", "")
        if request.user.check_password(password):
            return JsonResponse({"success": True})
        return JsonResponse({"success": False, "error": "invalid_password"}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_POST
def passkey_verify_options(request):
    """Generate WebAuthn authentication options for the lock screen (already logged in)."""
    try:
        options = generate_authentication_options(
            rp_id=_get_rp_id(request),
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        _store_challenge(request, "passkey_verify_challenge", options.challenge)
        return JsonResponse(json.loads(options_to_json(options)))
    except Exception as e:
        return JsonResponse(
            {"success": False, "error": f"Failed to generate options: {str(e)}"},
            status=500,
        )


@login_required
@require_POST
def passkey_verify_complete(request):
    """Verify a WebAuthn assertion for the lock screen without re-authenticating."""
    try:
        challenge = _load_challenge(request, "passkey_verify_challenge")
        if not challenge:
            return JsonResponse(
                {"success": False, "error": "missing_challenge"}, status=400
            )

        payload = json.loads(request.body or "{}")
        credential = parse_authentication_credential_json(json.dumps(payload))

        stored = (
            PasskeyCredential.objects.select_related("user")
            .filter(credential_id=credential.id, user=request.user)
            .first()
        )
        if not stored:
            return JsonResponse(
                {"success": False, "error": "unknown_credential"}, status=400
            )

        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_origin=_get_origin(request),
            expected_rp_id=_get_rp_id(request),
            credential_public_key=base64url_to_bytes(stored.public_key),
            credential_current_sign_count=stored.sign_count,
        )

        stored.sign_count = verification.new_sign_count
        stored.save(update_fields=["sign_count"])

        request.session.pop("passkey_verify_challenge", None)
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)
