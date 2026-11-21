"""Tests of the household page: members managed outside the administration."""

import datetime

import pytest
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from accounts.forms import HouseholdMemberForm, member_username
from accounts.models import is_child

STRONG_PASSWORD = "Correct-Horse-42-battery"


def _member(response):
    assert response.status_code == 302, response.context["form"].errors
    assert response.url == reverse("accounts:household")
    return User.objects.order_by("-pk").first()


@pytest.mark.django_db
class TestList:
    def test_lists_adults_and_children(self, user_client, user):
        child = User.objects.create_user(username="child-zoe", first_name="Zoé")
        child.profile.is_child = True  # ty: ignore[unresolved-attribute]
        child.profile.birth_date = datetime.date(2015, 3, 1)  # ty: ignore[unresolved-attribute]
        child.profile.save()  # ty: ignore[unresolved-attribute]

        response = user_client.get(reverse("accounts:household"))

        assert response.status_code == 200
        members = response.context["members"]
        assert [m["user"] for m in members] == [user, child]
        assert members[0]["can_log_in"] and not members[0]["is_child"]
        assert members[1]["is_child"] and not members[1]["can_log_in"]
        assert reverse("accounts:household_edit", args=[child.pk]) in (
            response.content.decode()
        )

    def test_requires_login(self, client):
        response = client.get(reverse("accounts:household"))
        assert response.status_code == 302

    def test_settings_link(self, user_client):
        response = user_client.get(reverse("accounts:settings"))
        assert reverse("accounts:household") in response.content.decode()


@pytest.mark.django_db
class TestAdd:
    def test_child(self, user_client):
        response = user_client.post(
            reverse("accounts:household_add"),
            {"first_name": "Zoé", "kind": "child", "birth_date": "2015-03-01"},
        )
        child = _member(response)
        assert child.username == "child-zoe"
        assert not child.has_usable_password()
        assert not child.is_staff and not child.is_superuser
        assert is_child(child)
        assert child.profile.birth_date == datetime.date(2015, 3, 1)

    def test_adult_without_login(self, user_client):
        response = user_client.post(
            reverse("accounts:household_add"),
            {"first_name": "Camille", "last_name": "Martin", "kind": "adult"},
        )
        adult = _member(response)
        assert adult.username == "member-camille"
        assert not adult.has_usable_password()
        assert not is_child(adult)
        assert adult.profile.birth_date is None
        assert authenticate(username="member-camille", password="") is None

    def test_first_name_required(self, user_client):
        response = user_client.post(
            reverse("accounts:household_add"), {"first_name": "", "kind": "adult"}
        )
        assert response.status_code == 200
        assert "first_name" in response.context["form"].errors

    def test_get_shows_the_form(self, user_client):
        response = user_client.get(reverse("accounts:household_add"))
        assert response.status_code == 200
        assert "kind" in response.context["form"].fields

    def test_non_superuser_cannot_create_a_login(self, user_client):
        response = user_client.get(reverse("accounts:household_add"))
        assert "can_log_in" not in response.context["form"].fields

        response = user_client.post(
            reverse("accounts:household_add"),
            {
                "first_name": "Camille",
                "kind": "adult",
                "can_log_in": "on",
                "login": "camille",
                "password1": STRONG_PASSWORD,
                "password2": STRONG_PASSWORD,
            },
        )
        adult = _member(response)
        assert adult.username == "member-camille"
        assert not adult.has_usable_password()

    def test_superuser_creates_a_login(self, admin_client):
        response = admin_client.post(
            reverse("accounts:household_add"),
            {
                "first_name": "Camille",
                "kind": "adult",
                "can_log_in": "on",
                "login": "camille",
                "password1": STRONG_PASSWORD,
                "password2": STRONG_PASSWORD,
            },
        )
        adult = _member(response)
        assert adult.username == "camille"
        assert not adult.is_staff and not adult.is_superuser
        assert authenticate(username="camille", password=STRONG_PASSWORD) == adult

    @pytest.mark.parametrize(
        ("data", "field"),
        [
            ({"login": "", "password1": STRONG_PASSWORD}, "login"),
            ({"login": "admin", "password1": STRONG_PASSWORD}, "login"),
            ({"login": "camille", "password1": ""}, "password1"),
            (
                {"login": "camille", "password1": "1234", "password2": "1234"},
                "password1",
            ),
            (
                {"login": "camille", "password1": STRONG_PASSWORD, "password2": "x"},
                "password2",
            ),
            (
                {"login": "camille", "password1": STRONG_PASSWORD, "kind": "child"},
                "can_log_in",
            ),
        ],
    )
    def test_superuser_login_errors(self, admin_client, data, field):
        data = {
            "first_name": "Camille",
            "kind": "adult",
            "can_log_in": "on",
            "password2": data.get("password1", ""),
            **data,
        }
        response = admin_client.post(reverse("accounts:household_add"), data)
        assert response.status_code == 200
        assert field in response.context["form"].errors


@pytest.mark.django_db
class TestEdit:
    def test_birth_date_and_names(self, user_client):
        child = User.objects.create_user(username="child-zoe", first_name="Zoé")
        child.profile.is_child = True  # ty: ignore[unresolved-attribute]
        child.profile.save()  # ty: ignore[unresolved-attribute]
        url = reverse("accounts:household_edit", args=[child.pk])

        response = user_client.get(url)
        assert response.status_code == 200
        assert "kind" not in response.context["form"].fields

        response = user_client.post(
            url,
            {"first_name": "Zoé", "last_name": "Martin", "birth_date": "2015-03-01"},
        )
        assert response.status_code == 302
        child.refresh_from_db()
        child.profile.refresh_from_db()  # ty: ignore[unresolved-attribute]
        assert child.last_name == "Martin"
        assert child.username == "child-zoe"
        assert is_child(child)
        assert child.profile.birth_date == datetime.date(2015, 3, 1)  # ty: ignore[unresolved-attribute]

    def test_a_member_who_logs_in_is_edited_by_themselves_or_a_superuser(
        self, user_client, user, admin_user
    ):
        # user_client and admin_client share one client: log the admin in apart.
        admin_client = Client()
        admin_client.force_login(admin_user)
        # Another login member, even a superuser, is out of reach.
        url = reverse("accounts:household_edit", args=[admin_user.pk])
        assert user_client.get(url).status_code == 403
        assert user_client.post(url, {"first_name": "Root"}).status_code == 403
        listed = user_client.get(reverse("accounts:household")).context["members"]
        editable = {m["user"]: m["editable"] for m in listed}
        assert editable == {user: True, admin_user: False}

        # Oneself, and a superuser for anyone.
        own = reverse("accounts:household_edit", args=[user.pk])
        response = user_client.post(
            own, {"first_name": "Me", "birth_date": "1980-01-01"}
        )
        assert response.status_code == 302
        response = admin_client.post(own, {"first_name": "Moi", "birth_date": ""})
        assert response.status_code == 302
        user.refresh_from_db()
        assert user.first_name == "Moi"
        assert not user.is_superuser and user.has_usable_password()

    def test_editing_a_superuser_keeps_its_rights(self, admin_client, admin_user):
        url = reverse("accounts:household_edit", args=[admin_user.pk])
        response = admin_client.post(url, {"first_name": "Root", "birth_date": ""})
        assert response.status_code == 302
        admin_user.refresh_from_db()
        assert admin_user.first_name == "Root"
        assert admin_user.is_superuser and admin_user.has_usable_password()

    def test_rejected_submission_keeps_the_stored_name(self, admin_client):
        adult = User.objects.create_user(
            username="member-camille", first_name="Camille"
        )
        adult.set_unusable_password()
        adult.save()
        url = reverse("accounts:household_edit", args=[adult.pk])
        response = admin_client.post(
            url,
            {
                "first_name": "Renamed",
                "can_log_in": "on",
                "login": "newname",
                "password1": "1234",
                "password2": "1234",
            },
        )
        assert response.status_code == 200
        assert response.context["member"].first_name == "Camille"
        assert response.context["member"].username == "member-camille"
        adult.refresh_from_db()
        assert adult.username == "member-camille"

    def test_superuser_gives_a_login_to_an_adult(self, admin_client):
        adult = User.objects.create_user(
            username="member-camille", first_name="Camille"
        )
        adult.set_unusable_password()
        adult.save()
        url = reverse("accounts:household_edit", args=[adult.pk])
        assert "can_log_in" in admin_client.get(url).context["form"].fields

        response = admin_client.post(
            url,
            {
                "first_name": "Camille",
                "can_log_in": "on",
                "login": "camille",
                "password1": STRONG_PASSWORD,
                "password2": STRONG_PASSWORD,
            },
        )
        assert response.status_code == 302
        assert authenticate(username="camille", password=STRONG_PASSWORD) is not None

    def test_no_login_fields_for_a_member_who_logs_in(self, admin_client, user):
        url = reverse("accounts:household_edit", args=[user.pk])
        assert "can_log_in" not in admin_client.get(url).context["form"].fields

    def test_unknown_or_inactive_member(self, user_client):
        inactive = User.objects.create_user(username="gone", is_active=False)
        for pk in (inactive.pk, 999999):
            url = reverse("accounts:household_edit", args=[pk])
            assert user_client.get(url).status_code == 404


@pytest.mark.django_db
def test_member_username_is_unique():
    assert member_username("Camille") == "member-camille"
    User.objects.create_user(username="member-camille")
    assert member_username("Camille") == "member-camille-2"
    assert member_username("!!", prefix="child") == "child-member"


@pytest.mark.django_db
def test_form_without_acting_superuser(user):
    form = HouseholdMemberForm(acting_user=user)
    assert not form.with_login


@pytest.mark.django_db
def test_save_without_commit_writes_nothing(admin_user):
    form = HouseholdMemberForm(
        {"first_name": "Zoé", "kind": "child", "birth_date": "2015-03-01"},
        acting_user=admin_user,
    )
    assert form.is_valid(), form.errors
    child = form.save(commit=False)
    assert child.pk is None
    assert not User.objects.filter(first_name="Zoé").exists()
    child.save()
    form.save_m2m()
    assert is_child(child)
    assert child.profile.birth_date == datetime.date(2015, 3, 1)


@pytest.mark.django_db
def test_administration_is_linked_from_the_settings_only(user, admin_user):
    """The administration is a tool for advanced users, not part of the menus."""
    admin_url = reverse("admin:index")
    for member, linked in ((user, False), (admin_user, True)):
        client = Client()
        client.force_login(member)
        settings_page = client.get(reverse("accounts:settings")).content.decode()
        household_page = client.get(reverse("accounts:household")).content.decode()
        assert (f'href="{admin_url}"' in settings_page) is linked
        assert f'href="{admin_url}"' not in household_page
