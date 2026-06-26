"""Tests for accounts views and context processor."""

from types import SimpleNamespace
from typing import cast

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.test import RequestFactory
from django.urls import reverse

from accounts import views
from accounts.context_processors import session_config
from accounts.models import PasskeyCredential


@pytest.mark.django_db
def test_logout_confirm_requires_authentication(client):
    response = client.get(reverse("accounts:logout_confirm"))
    assert response.status_code == 302


@pytest.mark.django_db
def test_settings_view_get(user_client):
    response = user_client.get(reverse("accounts:settings"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_settings_view_password_change_success(user_client):
    user = get_user_model().objects.get(username="testuser")
    response = user_client.post(
        reverse("accounts:settings"),
        {
            "old_password": "testpassword",
            "new_password1": "new-very-strong-password-123",
            "new_password2": "new-very-strong-password-123",
        },
        follow=True,
    )

    user.refresh_from_db()
    assert response.status_code == 200
    assert user.check_password("new-very-strong-password-123")


@pytest.mark.django_db
def test_session_config_context_anonymous():
    request = RequestFactory().get("/")
    request.user = cast(
        AbstractBaseUser | AnonymousUser, SimpleNamespace(is_authenticated=False)
    )
    context = session_config(request)
    assert context["session_timeout"] == 15
    assert context["passkey_registered"] is False


@pytest.mark.django_db
def test_session_config_context_authenticated_with_passkey(user):
    PasskeyCredential.objects.create(
        user=user,
        credential_id="cred-1",
        public_key="pub-1",
        sign_count=0,
    )
    request = RequestFactory().get("/")
    request.user = user

    context = session_config(request)
    assert context["session_timeout"] == 15
    assert context["passkey_registered"] is True


@pytest.mark.django_db
def test_session_config_context_exception_path():
    class BrokenUser:
        is_authenticated = True

        @property
        def profile(self):
            raise RuntimeError("broken profile")

    request = RequestFactory().get("/")
    request.user = cast(AbstractBaseUser | AnonymousUser, BrokenUser())
    context = session_config(request)
    assert context["session_timeout"] == 15
    assert context["passkey_registered"] is False


@pytest.mark.django_db
def test_update_session_timeout_missing_timeout(user_client):
    response = user_client.post(
        reverse("accounts:update_session_timeout"),
        data="{}",
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


@pytest.mark.django_db
def test_update_session_timeout_success(user_client, user):
    response = user_client.post(
        reverse("accounts:update_session_timeout"),
        data='{"timeout": 25}',
        content_type="application/json",
    )
    user.refresh_from_db()
    assert response.status_code == 200
    assert response.json()["session_timeout"] == 25
    assert user.profile.session_timeout == 25


@pytest.mark.django_db
def test_update_session_timeout_invalid_range(user_client):
    response = user_client.post(
        reverse("accounts:update_session_timeout"),
        data='{"timeout": 3}',
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_range"


@pytest.mark.django_db
def test_passkey_register_options_success(user_client, monkeypatch):
    monkeypatch.setattr(
        "accounts.views.generate_registration_options",
        lambda **kwargs: SimpleNamespace(challenge=b"register-challenge"),
    )
    monkeypatch.setattr(
        "accounts.views.options_to_json",
        lambda options: '{"challenge":"ok"}',
    )

    response = user_client.post(reverse("accounts:passkey_register_options"))
    assert response.status_code == 200
    assert response.json()["challenge"] == "ok"


@pytest.mark.django_db
def test_passkey_register_options_error(user_client, monkeypatch):
    def _raise(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("accounts.views.generate_registration_options", _raise)
    response = user_client.post(reverse("accounts:passkey_register_options"))
    assert response.status_code == 500
    assert response.json()["error"] == "registration_failed"


@pytest.mark.django_db
def test_passkey_register_complete_requires_challenge(user_client):
    response = user_client.post(
        reverse("accounts:passkey_register_complete"),
        data="{}",
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


@pytest.mark.django_db
def test_passkey_register_complete_success(user_client, user, monkeypatch):
    session = user_client.session
    session["passkey_register_challenge"] = "challenge"
    session.save()

    monkeypatch.setattr(
        "accounts.views.parse_registration_credential_json", lambda payload: object()
    )
    monkeypatch.setattr(
        "accounts.views.verify_registration_response",
        lambda **kwargs: SimpleNamespace(
            credential_id=b"credential",
            credential_public_key=b"public-key",
            sign_count=12,
        ),
    )

    response = user_client.post(
        reverse("accounts:passkey_register_complete"),
        data="{}",
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    cred = PasskeyCredential.objects.get(user=user)
    assert cred.sign_count == 12


@pytest.mark.django_db
def test_passkey_register_complete_invalid_json(user_client):
    session = user_client.session
    session["passkey_register_challenge"] = "challenge"
    session.save()
    response = user_client.post(
        reverse("accounts:passkey_register_complete"),
        data="{",
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


@pytest.mark.django_db
def test_passkey_auth_options_success_and_error(client, monkeypatch):
    monkeypatch.setattr(
        "accounts.views.generate_authentication_options",
        lambda **kwargs: SimpleNamespace(challenge=b"auth-challenge"),
    )
    monkeypatch.setattr(
        "accounts.views.options_to_json",
        lambda options: '{"allowCredentials":[]}',
    )
    ok = client.post(reverse("accounts:passkey_auth_options"))
    assert ok.status_code == 200

    def _raise(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("accounts.views.generate_authentication_options", _raise)
    ko = client.post(reverse("accounts:passkey_auth_options"))
    assert ko.status_code == 500
    assert ko.json()["error"] == "authentication_failed"


@pytest.mark.django_db
def test_passkey_auth_complete_success(user_client, user, monkeypatch):
    PasskeyCredential.objects.create(
        user=user,
        credential_id="cred-xyz",
        public_key="ignored",
        sign_count=1,
    )
    session = user_client.session
    session["passkey_auth_challenge"] = "challenge"
    session.save()

    monkeypatch.setattr(
        "accounts.views.parse_authentication_credential_json",
        lambda payload: SimpleNamespace(id="cred-xyz"),
    )
    monkeypatch.setattr("accounts.views.base64url_to_bytes", lambda value: b"pk")
    monkeypatch.setattr(
        "accounts.views.verify_authentication_response",
        lambda **kwargs: SimpleNamespace(new_sign_count=9),
    )

    response = user_client.post(
        reverse("accounts:passkey_auth_complete"),
        data="{}",
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.django_db
def test_passkey_auth_complete_invalid_paths(client, user_client, user):
    missing = client.post(
        reverse("accounts:passkey_auth_complete"),
        data="{}",
        content_type="application/json",
    )
    assert missing.status_code == 400

    session = client.session
    session["passkey_auth_challenge"] = "challenge"
    session.save()
    unknown = client.post(
        reverse("accounts:passkey_auth_complete"),
        data='{"id":"unknown"}',
        content_type="application/json",
    )
    assert unknown.status_code == 400

    session_user = user_client.session
    session_user["passkey_auth_challenge"] = "challenge"
    session_user.save()
    invalid_json = user_client.post(
        reverse("accounts:passkey_auth_complete"),
        data="{",
        content_type="application/json",
    )
    assert invalid_json.status_code == 400


@pytest.mark.django_db
def test_passkey_delete_paths(user_client, user):
    PasskeyCredential.objects.create(
        user=user,
        credential_id="cred-delete",
        public_key="pub-delete",
        sign_count=0,
    )

    bad_password = user_client.post(
        reverse("accounts:passkey_delete"),
        data='{"password": "bad"}',
        content_type="application/json",
    )
    assert bad_password.status_code == 400
    assert bad_password.json()["error"] == "invalid_password"

    ok = user_client.post(
        reverse("accounts:passkey_delete"),
        data='{"password": "testpassword"}',
        content_type="application/json",
    )
    assert ok.status_code == 200
    assert ok.json()["success"] is True
    assert PasskeyCredential.objects.filter(user=user).count() == 0


@pytest.mark.django_db
def test_passkey_delete_invalid_json(user_client):
    response = user_client.post(
        reverse("accounts:passkey_delete"),
        data="{",
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


def test_get_rp_id_helpers_with_request_factory(settings):
    settings.ALLOWED_HOSTS = ["localhost", "example.org"]
    request = RequestFactory().get("/", HTTP_HOST="example.org:8443")

    settings.WEBAUTHN_RP_ID = "configured-rp"
    assert views._get_rp_id(request) == "configured-rp"

    settings.WEBAUTHN_RP_ID = None
    localhost_request = RequestFactory().get("/", HTTP_HOST="localhost:8000")
    assert views._get_rp_id(localhost_request) == "localhost"
    assert views._get_rp_id(request) == "example.org"


def test_get_origin_helper(settings):
    settings.ALLOWED_HOSTS = ["example.org"]
    request = RequestFactory().get("/", secure=True, HTTP_HOST="example.org")

    settings.WEBAUTHN_ORIGIN = "https://configured.example"
    assert views._get_origin(request) == "https://configured.example"

    settings.WEBAUTHN_ORIGIN = None
    assert views._get_origin(request) == "https://example.org"


def test_store_and_load_challenge_helpers(rf):
    request = rf.get("/")
    request.session = {}

    views._store_challenge(request, "key", b"abc")
    assert views._load_challenge(request, "key") == b"abc"

    views._store_challenge(request, "key2", "plain")
    assert views._load_challenge(request, "key2") == b"plain"
    assert views._load_challenge(request, "missing") is None


@pytest.mark.django_db
def test_login_page_has_no_passkey_button(client):
    response = client.get(reverse("login"))
    assert response.status_code == 200
    content = response.content.decode()
    assert 'id="passkey-login"' not in content


@pytest.mark.django_db
def test_login_page_has_passkey_status_element(client):
    response = client.get(reverse("login"))
    assert response.status_code == 200
    content = response.content.decode()
    assert 'id="passkey-login-status"' in content
    assert 'aria-live="polite"' in content


@pytest.mark.django_db
def test_login_page_has_conditional_ui_script(client):
    response = client.get(reverse("login"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "isConditionalMediationAvailable" in content


@pytest.mark.django_db
def test_login_page_conditional_ui_sets_autocomplete(client):
    response = client.get(reverse("login"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "autocomplete" in content
    assert "webauthn" in content
