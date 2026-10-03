"""Tests for the ownership of assets by household members."""

import datetime
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.forms import ModelChoiceField
from django.urls import reverse
from moneyed import Money

from base.forms import OwnershipForm
from base.models import Ownership
from base.services.ownership import (
    ASSET_KINDS,
    kind_of,
    life_usufruct_percent,
    net_worth_by_person,
    ownerships_of,
    right_ratio,
    temporary_usufruct_percent,
)
from finance.models.other_asset import OtherAsset
from finance.models.saving_account import SavingAccount, SavingAccountType
from property.models import Property
from property.models.scpi import SCPI, SCPIInvestment

D = datetime.date
TODAY = D(2026, 10, 1)
CURRENCY = "XAU"  # isolates the test data from any other fixture


class TestArticle669:
    @pytest.mark.parametrize(
        ("birth", "percent"),
        [
            (D(2006, 1, 1), 90),
            (D(2005, 10, 1), 80),
            (D(1981, 1, 1), 60),
            (D(1950, 1, 1), 30),
            (D(1930, 1, 1), 10),
        ],
    )
    def test_life_usufruct(self, birth, percent):
        assert life_usufruct_percent(birth, TODAY) == percent

    @pytest.mark.parametrize(
        ("end", "percent"),
        [
            (D(2031, 10, 1), 23),
            (D(2041, 10, 1), 46),
            (D(2026, 1, 1), 0),
            (D(2080, 1, 1), 100),
        ],
    )
    def test_temporary_usufruct(self, end, percent):
        assert temporary_usufruct_percent(end, TODAY) == percent


def _user(username, **kwargs):
    return User.objects.create_user(username=username, password="x", **kwargs)


def _saving(name="Owned livret", amount=10000):
    account_type = SavingAccountType.objects.get_or_create(code="LA", name="LA")[0]
    return SavingAccount.objects.create(
        account_type=account_type,
        name=name,
        opening_value=Money(amount, CURRENCY),
    )


def _own(asset, user, share=100, right=Ownership.Right.FULL, **kwargs):
    return Ownership.objects.create(
        content_type=ContentType.objects.get_for_model(asset),
        object_id=asset.pk,
        user=user,
        share=Decimal(share),
        right=right,
        **kwargs,
    )


@pytest.mark.django_db
class TestRightRatio:
    def test_ratios(self):
        alice = _user("alice")
        alice.profile.birth_date = D(1981, 1, 1)
        alice.profile.save()
        account = _saving()
        full = _own(account, alice)
        assert right_ratio(full, TODAY) == 1
        usufruct = Ownership(user=alice, right=Ownership.Right.USUFRUCT)
        assert right_ratio(usufruct, TODAY) == Decimal("0.6")
        bare = Ownership(
            user=alice,
            right=Ownership.Right.BARE,
            usufructuary_birth_date=D(1950, 1, 1),
        )
        assert right_ratio(bare, TODAY) == Decimal("0.7")
        temporary = Ownership(
            user=alice, right=Ownership.Right.BARE, usufruct_end_date=D(2031, 1, 1)
        )
        assert right_ratio(temporary, TODAY) == Decimal("0.77")
        unknown = Ownership(user=alice, right=Ownership.Right.BARE)
        assert right_ratio(unknown, TODAY) is None
        assert "alice" in str(full)


@pytest.mark.django_db
class TestKinds:
    def test_detail_urls(self):
        scpi = SCPI.objects.create(name="Owned SCPI")
        investment = SCPIInvestment.objects.create(
            scpi=scpi,
            subscription_date=D(2020, 1, 1),
            shares_count=Decimal(1),
            unit_purchase_price=Money(100, CURRENCY),
        )
        assert kind_of(investment) == "scpi"
        assert ASSET_KINDS["scpi"].detail_url(investment) == reverse(
            "property:scpi_fund_detail", kwargs={"scpi_pk": scpi.pk}
        )
        account = _saving()
        assert ASSET_KINDS["saving"].detail_url(account).endswith(f"/{account.pk}/")
        with pytest.raises(KeyError):
            kind_of(object())


@pytest.mark.django_db
class TestNetWorthByPerson:
    def test_breakdown(self):
        User.objects.exclude(username__in=["alice", "bob"]).update(is_active=False)
        alice = _user("alice", first_name="Alice")
        bob = _user("bob")
        account = _saving()
        _own(account, alice, 50)
        _own(account, bob, 50)
        prop = Property.objects.create(
            name="Owned house",
            property_type=Property.HOUSE,
            buying_value=Money(200000, CURRENCY),
            buying_date=D(2020, 1, 1),
        )
        _own(
            prop,
            alice,
            right=Ownership.Right.USUFRUCT,
            usufructuary_birth_date=D(1960, 1, 1),
        )
        unvalued = OtherAsset.objects.create(
            name="Owned painting",
            acquisition_value=Money(3000, CURRENCY),
            acquisition_date=D(2020, 1, 1),
        )
        _own(unvalued, bob, right=Ownership.Right.BARE)
        OtherAsset.objects.create(
            name="Shared car",
            acquisition_value=Money(1000, CURRENCY),
            acquisition_date=D(2020, 1, 1),
        )
        people, unassigned, outside = net_worth_by_person(CURRENCY, today=TODAY)
        by_label = {p.label: p for p in people}
        # Usufruct at 66 years: 40 % of 200,000.
        assert by_label["Alice"].by_kind == {
            "saving": Decimal(5000),
            "property": Decimal(80000),
        }
        assert by_label["bob"].total == Decimal(5000)
        assert by_label["bob"].unvalued == ["Owned painting"]
        assert unassigned.by_kind == {"other": Decimal(4000)}
        assert outside.by_kind == {"property": Decimal(120000)}


@pytest.mark.django_db
class TestOwnershipForm:
    def test_shares_cannot_exceed_100(self):
        alice, bob = _user("alice"), _user("bob")
        account = _saving()
        existing = _own(account, alice, 60)
        form = OwnershipForm(
            {"user": bob.pk, "share": "50", "right": "full"}, others=[existing]
        )
        assert not form.is_valid()
        assert "exceed 100" in str(form.errors)

    def test_dismembered_rights_can_share_the_asset(self):
        alice, bob = _user("alice"), _user("bob")
        account = _saving()
        usufruct = _own(
            account, alice, right="usufruct", usufruct_end_date=D(2040, 1, 1)
        )
        form = OwnershipForm(
            {
                "user": bob.pk,
                "share": "100",
                "right": "bare",
                "usufruct_end_date": "2040-01-01",
            },
            others=[usufruct],
        )
        assert form.is_valid(), form.errors

    def test_dismembered_right_needs_a_date(self):
        alice = _user("alice")
        form = OwnershipForm({"user": alice.pk, "share": "100", "right": "bare"})
        assert not form.is_valid()
        alice.profile.birth_date = D(1980, 1, 1)
        alice.profile.save()
        form = OwnershipForm({"user": alice.pk, "share": "100", "right": "usufruct"})
        assert form.is_valid(), form.errors

    def test_not_dismemberable(self):
        alice = _user("alice", first_name="Alice", last_name="Martin")
        form = OwnershipForm(dismemberable=False)
        assert "right" not in form.fields
        user_field = form.fields["user"]
        assert isinstance(user_field, ModelChoiceField)
        assert user_field.label_from_instance(alice) == "Alice Martin"


@pytest.mark.django_db
class TestViews:
    def test_manage_add_update_remove(self, user_client, user):
        account = _saving()
        url = reverse("manage_owners", kwargs={"kind": "saving", "pk": account.pk})
        response = user_client.get(url)
        assert response.status_code == 200
        assert "right" not in response.context["form"].fields

        response = user_client.post(url, {"user": user.pk, "share": "40"})
        assert response.status_code == 302
        response = user_client.post(url, {"user": user.pk, "share": "70"})
        ownership = Ownership.objects.get(object_id=account.pk, user=user)
        assert ownership.share == Decimal(70)
        assert user_client.get(url).context["rows"][0]["ratio"] == 1

        response = user_client.post(url, {"user": user.pk, "share": "0"})
        assert response.status_code == 200

        response = user_client.post(reverse("delete_ownership", args=[ownership.pk]))
        assert response.status_code == 302
        assert response.url == url
        assert not ownerships_of(account)

    def test_unknown_kind(self, user_client):
        url = reverse("manage_owners", kwargs={"kind": "car", "pk": 1})
        assert user_client.get(url).status_code == 404

    def test_remove_owner_of_deleted_asset(self, user_client, user):
        ownership = Ownership.objects.create(
            content_type=ContentType.objects.get_for_model(SavingAccount),
            object_id=999999,
            user=user,
        )
        response = user_client.post(reverse("delete_ownership", args=[ownership.pk]))
        assert response.url == reverse("owners")

    def test_overview_and_birth_date(self, user_client, user):
        response = user_client.get(reverse("owners"))
        assert response.status_code == 200
        response = user_client.post(reverse("owners"), {"birth_date": "1980-05-01"})
        assert response.status_code == 302
        user.profile.refresh_from_db()
        assert user.profile.birth_date == D(1980, 5, 1)
        response = user_client.post(reverse("owners"), {"birth_date": "bad"})
        assert response.status_code == 200

    def test_summary_on_detail_page(self, user_client, user):
        account = _saving()
        _own(account, user, 100)
        response = user_client.get(reverse("finance:saving_detail", args=[account.pk]))
        content = response.content.decode()
        assert "owners-summary" in content
        assert "testuser 100%" in content

    def test_deleting_the_asset_deletes_its_owners(self, user):
        account = _saving()
        _own(account, user)
        account.delete()
        assert not Ownership.objects.filter(user=user).exists()


class _LegacyAssets:
    """Stand-in for a historical model still carrying the free-text owner."""

    def __init__(self, rows):
        self.objects = self
        self.rows = rows

    def exclude(self, **kwargs):
        return self

    def __iter__(self):
        return iter(self.rows)


class _LegacyApps:
    """App registry whose saving accounts carry the given owner texts."""

    def __init__(self, owners):
        self.savings = [SimpleNamespace(pk=a.pk, owner=text) for a, text in owners]

    def get_model(self, app_label, model_name):
        if app_label == "finance":
            return _LegacyAssets(self.savings if model_name == "savingaccount" else [])
        return apps.get_model(app_label, model_name)


def _migration(name):
    return import_module(f"base.migrations.{name}")


@pytest.mark.django_db
class TestDataMigration:
    def test_owner_text_becomes_ownership(self):
        alice = _user("alice", first_name="Alice")
        _user("alice2", first_name="Twin")
        _user("alice3", first_name="Twin")
        matched, ambiguous, shared = (
            _saving("Matched"),
            _saving("Ambiguous"),
            _saving("Shared"),
        )
        legacy = _LegacyApps(
            [(matched, "ALICE"), (ambiguous, "twin"), (shared, "Both of us")]
        )
        _migration("0004_ownership_from_owner_text").forwards(legacy, None)
        assert [o.user for o in ownerships_of(matched)] == [alice]
        assert ownerships_of(ambiguous) == []
        assert ownerships_of(shared) == []

    def test_remaining_texts_before_the_field_is_dropped(self):
        User.objects.update(is_active=False)
        alice = _user("alice", first_name="Alice")
        bob = _user("bob")
        child = _user("child-zoe", first_name="Zoé")
        child.profile.is_child = True
        child.profile.save()
        matched, joint, other, owned, blank = (
            _saving(name) for name in ("Matched", "Joint", "Other", "Owned", "Blank")
        )
        _own(owned, bob)
        legacy = _LegacyApps(
            [
                (matched, " alice "),
                (joint, "Foyer"),
                (other, "Grandma"),
                (owned, "Alice"),
                (blank, "  "),
            ]
        )
        _migration("0005_ownership_from_remaining_owner_text").forwards(legacy, None)
        assert [(o.user, o.share) for o in ownerships_of(matched)] == [
            (alice, Decimal(100))
        ]
        assert sorted((o.user.username, o.share) for o in ownerships_of(joint)) == [
            ("alice", Decimal(50)),
            ("bob", Decimal(50)),
        ]
        assert ownerships_of(other) == []
        assert [o.user for o in ownerships_of(owned)] == [bob]
        assert ownerships_of(blank) == []

    def test_split_of_three(self):
        assert _migration("0005_ownership_from_remaining_owner_text")._split(3) == [
            Decimal("33.33"),
            Decimal("33.33"),
            Decimal("33.34"),
        ]
