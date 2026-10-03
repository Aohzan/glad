"""Tests for the children of the household, who own assets but cannot log in."""

import datetime
from types import SimpleNamespace

import pytest
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.urls import reverse

from accounts.admin import child_username
from accounts.backends import HouseholdModelBackend
from accounts.models import Child, PasskeyCredential, create_user_profile, is_child


def _child(first_name="Zoé", **kwargs):
    user = User.objects.create_user(
        username=child_username(first_name), first_name=first_name, **kwargs
    )
    user.profile.is_child = True  # ty: ignore[unresolved-attribute]
    user.profile.save()  # ty: ignore[unresolved-attribute]
    return user


@pytest.mark.django_db
class TestChildUsername:
    def test_unique_from_the_first_name(self):
        assert child_username("Zoé Anne") == "child-zoe-anne"
        _child("Zoé Anne")
        assert child_username("Zoé Anne") == "child-zoe-anne-2"
        User.objects.create_user(username="child-zoe-anne-2")
        assert child_username("Zoé Anne") == "child-zoe-anne-3"

    def test_first_name_without_letters(self):
        assert child_username("!!") == "child-member"


@pytest.mark.django_db
class TestChildAdmin:
    def test_add_with_the_first_name_only(self, admin_client):
        response = admin_client.post(
            reverse("admin:accounts_child_add"),
            {"first_name": "Zoé", "last_name": "", "email": "", "birth_date": ""},
        )
        assert response.status_code == 302
        child = Child.objects.get(first_name="Zoé")
        assert child.username == "child-zoe"
        assert not child.has_usable_password()
        assert not child.is_staff
        assert child.profile.is_child
        assert child.profile.birth_date is None
        assert not child.profile.notify_on_login

    def test_first_name_is_required(self, admin_client):
        response = admin_client.post(
            reverse("admin:accounts_child_add"), {"first_name": ""}
        )
        assert response.status_code == 200
        assert "first_name" in response.context["adminform"].form.errors

    def test_edit_keeps_the_username(self, admin_client):
        child = _child()
        url = reverse("admin:accounts_child_change", args=[child.pk])
        response = admin_client.get(url)
        assert response.status_code == 200
        response = admin_client.post(
            url,
            {
                "first_name": "Zoé",
                "last_name": "Martin",
                "email": "",
                "birth_date": "2019-04-02",
            },
        )
        assert response.status_code == 302
        child.refresh_from_db()
        assert child.username == "child-zoe"
        assert child.last_name == "Martin"
        assert child.profile.birth_date == datetime.date(2019, 4, 2)

    def test_list_shows_only_children(self, admin_client, user):
        _child()
        response = admin_client.get(reverse("admin:accounts_child_changelist"))
        assert response.status_code == 200
        assert list(response.context["cl"].queryset) == list(Child.objects.all())
        assert user.pk not in {c.pk for c in Child.objects.all()}


@pytest.mark.django_db
class TestNoLogin:
    def test_a_child_cannot_log_in(self, client):
        child = _child(password="secret-password")
        assert authenticate(username=child.username, password="secret-password") is None
        assert not client.login(username=child.username, password="secret-password")

    def test_the_session_of_a_user_flagged_as_child_is_dropped(self, user_client, user):
        assert user_client.get(reverse("index")).status_code == 200
        user.profile.is_child = True
        user.profile.save()
        response = user_client.get(reverse("index"))
        assert response.status_code == 302
        assert reverse("login") in response.url

    def test_unknown_session_user(self):
        assert HouseholdModelBackend().get_user(999_999) is None

    def test_passkey_of_a_child_is_refused(self, client, monkeypatch):
        child = _child()
        PasskeyCredential.objects.create(
            user=child, credential_id="cred-child", public_key="ignored"
        )
        session = client.session
        session["passkey_auth_challenge"] = "challenge"
        session.save()
        monkeypatch.setattr(
            "accounts.views.parse_authentication_credential_json",
            lambda payload: SimpleNamespace(id="cred-child"),
        )
        response = client.post(
            reverse("accounts:passkey_auth_complete"),
            data="{}",
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_is_child():
    assert is_child(_child())
    assert not is_child(User.objects.create_user(username="adult"))
    assert not is_child(SimpleNamespace())


@pytest.mark.django_db
def test_fixtures_bring_their_own_profile():
    """Raw saves (fixtures) do not create a profile: the fixture carries it."""
    user = User(username="raw-user")
    user.save_base(raw=True)
    create_user_profile(User, user, created=True, raw=True)
    assert not hasattr(User.objects.get(pk=user.pk), "profile")
