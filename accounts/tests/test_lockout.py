"""Brute-force protection of the password login and of the password reset."""

import pytest
from axes.models import AccessAttempt
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


@pytest.fixture
def axes_enabled(settings):
    """django-axes on, as in production (the test settings turn it off)."""
    settings.AXES_ENABLED = True
    settings.AXES_FAILURE_LIMIT = 3


def _login(client, password, username="testuser", ip="203.0.113.9"):
    return client.post(
        reverse("login"),
        {"username": username, "password": password},
        REMOTE_ADDR=ip,
    )


@pytest.mark.django_db
def test_password_login_is_locked_out_after_repeated_failures(
    client, user, axes_enabled
):
    for _attempt in range(2):
        assert _login(client, "wrong").status_code == 200
    response = _login(client, "wrong")
    assert response.status_code == 429
    assert "Too many login attempts" in response.content.decode()
    # The right password is refused during the lockout.
    assert _login(client, "testpassword").status_code == 429
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_lockout_also_covers_another_address_and_another_username(
    client, user, axes_enabled
):
    for _attempt in range(3):
        _login(client, "wrong")
    # Same username from elsewhere: locked out.
    assert _login(client, "testpassword", ip="198.51.100.1").status_code == 429
    # Same address with another username: locked out.
    assert _login(client, "x", username="other").status_code == 429


@pytest.mark.django_db
def test_lockout_uses_the_address_of_the_connection_not_the_headers(
    client, user, axes_enabled
):
    for attempt in range(3):
        client.post(
            reverse("login"),
            {"username": f"user{attempt}", "password": "wrong"},
            REMOTE_ADDR="203.0.113.9",
            HTTP_X_FORWARDED_FOR=f"10.0.0.{attempt}",
        )
    assert set(AccessAttempt.objects.values_list("ip_address", flat=True)) == {
        "203.0.113.9"
    }


@pytest.mark.django_db
def test_successful_login_resets_the_failures(client, user, axes_enabled):
    for _attempt in range(2):
        _login(client, "wrong")
    assert _login(client, "testpassword").status_code == 302
    client.logout()
    for _attempt in range(2):
        assert _login(client, "wrong").status_code == 200


@pytest.mark.django_db
def test_admin_login_is_protected(client, admin_user, axes_enabled):
    url = reverse("admin:login")
    for _attempt in range(3):
        response = client.post(
            url, {"username": "admin", "password": "wrong"}, REMOTE_ADDR="1.2.3.4"
        )
    assert response.status_code == 429


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_password_reset_sends_one_email_per_address_and_cooldown(client, user):
    cache.clear()
    for _attempt in range(3):
        response = client.post(reverse("password_reset"), {"email": "User@Site.com"})
        assert response.status_code == 302
        assert response.url == reverse("password_reset_done")
    assert len(mail.outbox) == 1
    cache.clear()
