"""Tests for choosing the owners of an asset and the breakdown per person."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from moneyed import Money

from base.forms import PeopleFilterForm
from base.models import Ownership, household_members
from base.services.allocation import compute_allocation
from base.services.ownership import (
    NoShareLeftError,
    held_ratio,
    net_worth_by_person,
    ownerships_of,
    plan_owners,
    split_equally,
)
from finance.forms import OtherAssetForm
from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountType,
)
from finance.models.other_asset import OtherAsset
from finance.models.saving_account import SavingAccount, SavingAccountType
from property.forms import SCPIForm
from property.models import Property
from property.models.scpi import SCPI, SCPIInvestment

D = datetime.date
TODAY = D(2026, 10, 1)
CURRENCY = "XAU"  # isolates the test data from any other fixture
FULL, BARE, USUFRUCT = (
    Ownership.Right.FULL,
    Ownership.Right.BARE,
    Ownership.Right.USUFRUCT,
)


def _user(username, **kwargs):
    return User.objects.create_user(username=username, **kwargs)


def _asset(name="Painting", amount=1000):
    return OtherAsset.objects.create(
        name=name,
        acquisition_value=Money(amount, CURRENCY),
        acquisition_date=D(2020, 1, 1),
    )


def _own(asset, user, share=100, right=FULL, **kwargs):
    return Ownership.objects.create(
        content_type=ContentType.objects.get_for_model(asset),
        object_id=asset.pk,
        user=user,
        share=Decimal(share),
        right=right,
        **kwargs,
    )


def _shares(asset):
    return {(o.user.username, o.right): o.share for o in ownerships_of(asset)}


def test_split_equally():
    assert split_equally(Decimal(100), 3) == [
        Decimal("33.33"),
        Decimal("33.33"),
        Decimal("33.34"),
    ]
    assert split_equally(Decimal(50), 2) == [Decimal(25), Decimal(25)]


@pytest.mark.django_db
class TestPlanOwners:
    def test_new_asset_is_split_equally(self):
        alice, bob = _user("alice"), _user("bob")
        plan = plan_owners([], [alice, bob])
        assert plan.delete == []
        assert [(o.user, o.share, o.right) for o in plan.save] == [
            (alice, Decimal(50), FULL),
            (bob, Decimal(50), FULL),
        ]

    def test_same_owners_keep_their_shares(self):
        alice, bob = _user("alice"), _user("bob")
        asset = _asset()
        rows = [_own(asset, alice, 70), _own(asset, bob, 30)]
        plan = plan_owners(rows, [bob, alice])
        assert plan.delete == plan.save == []

    def test_part_held_outside_is_kept(self):
        alice, bob = _user("alice"), _user("bob")
        asset = _asset()
        rows = [_own(asset, alice, 50)]
        plan = plan_owners(rows, [alice, bob])
        assert [o.share for o in plan.save] == [Decimal(25), Decimal(25)]

    def test_removed_full_owner_share_goes_to_the_others(self):
        alice, bob = _user("alice"), _user("bob")
        asset = _asset()
        rows = [_own(asset, alice, 50), _own(asset, bob, 50)]
        plan = plan_owners(rows, [alice])
        assert [o.user for o in plan.delete] == [bob]
        assert [(o.user, o.share) for o in plan.save] == [(alice, Decimal(100))]

    def test_removed_dismembered_right_leaves_the_others(self):
        alice, bob = _user("alice"), _user("bob")
        asset = _asset()
        rows = [
            _own(asset, alice, right=USUFRUCT, usufruct_end_date=D(2040, 1, 1)),
            _own(asset, bob, right=BARE, usufruct_end_date=D(2040, 1, 1)),
        ]
        plan = plan_owners(rows, [alice])
        assert [o.user for o in plan.delete] == [bob]
        assert plan.save == []

    def test_new_full_owner_next_to_dismembered_rights(self):
        alice, bob = _user("alice"), _user("bob")
        asset = _asset()
        rows = [_own(asset, alice, 60, right=BARE, usufruct_end_date=D(2040, 1, 1))]
        plan = plan_owners(rows, [alice, bob])
        assert [(o.user, o.share) for o in plan.save] == [(bob, Decimal(40))]

    def test_no_share_left(self):
        alice, bob, carol = _user("alice"), _user("bob"), _user("carol")
        asset = _asset()
        rows = [
            _own(asset, alice, right=USUFRUCT, usufruct_end_date=D(2040, 1, 1)),
            _own(asset, bob, right=BARE, usufruct_end_date=D(2040, 1, 1)),
        ]
        with pytest.raises(NoShareLeftError):
            plan_owners(rows, [alice, bob, carol])

    def test_nobody_left(self):
        alice = _user("alice")
        asset = _asset()
        rows = [_own(asset, alice)]
        plan = plan_owners(rows, [])
        assert plan.delete == rows
        assert plan.save == []


def _form_data(**kwargs):
    return {
        "name": "Car",
        "category": "vehicle",
        "acquisition_date": "2023-05-01",
        "acquisition_value_0": "20000",
        "acquisition_value_1": CURRENCY,
        "is_active": "on",
        **kwargs,
    }


@pytest.mark.django_db
class TestOwnersForm:
    def test_field_follows_the_category_and_is_required(self):
        form = OtherAssetForm(_form_data())
        names = list(form.fields)
        assert names[names.index("category") + 1] == "owners"
        assert not form.is_valid()
        assert form.errors["owners"] == ["Choose at least one owner."]

    def test_create_with_two_owners(self):
        alice, bob = _user("alice", first_name="Alice"), _user("bob")
        form = OtherAssetForm(_form_data(owners=[alice.pk, bob.pk]))
        assert form.is_valid(), form.errors
        asset = form.save()
        assert _shares(asset) == {
            ("alice", FULL): Decimal(50),
            ("bob", FULL): Decimal(50),
        }
        assert form.fields["owners"].label_from_instance(alice) == "Alice"  # ty: ignore[unresolved-attribute]

    def test_edit_keeps_custom_shares(self):
        alice, bob = _user("alice"), _user("bob")
        asset = _asset()
        _own(asset, alice, 70)
        _own(asset, bob, 30)
        form = OtherAssetForm(instance=asset)
        assert set(form.fields["owners"].initial) == {alice, bob}
        form = OtherAssetForm(_form_data(owners=[alice.pk, bob.pk]), instance=asset)
        assert form.is_valid(), form.errors
        form.save()
        assert _shares(asset) == {
            ("alice", FULL): Decimal(70),
            ("bob", FULL): Decimal(30),
        }

    def test_edit_removes_an_owner(self):
        alice, bob = _user("alice"), _user("bob")
        asset = _asset()
        _own(asset, alice, 50)
        _own(asset, bob, 50)
        form = OtherAssetForm(_form_data(owners=[alice.pk]), instance=asset)
        assert form.is_valid(), form.errors
        form.save()
        assert _shares(asset) == {("alice", FULL): Decimal(100)}

    def test_commit_false_saves_owners_with_save_m2m(self):
        alice = _user("alice")
        form = OtherAssetForm(_form_data(owners=[alice.pk]))
        assert form.is_valid(), form.errors
        asset = form.save(commit=False)
        asset.save()
        assert ownerships_of(asset) == []
        form.save_m2m()
        assert _shares(asset) == {("alice", FULL): Decimal(100)}

    def test_no_share_left(self):
        alice, bob, carol = _user("alice"), _user("bob"), _user("carol")
        asset = _asset()
        _own(asset, alice, right=USUFRUCT, usufruct_end_date=D(2040, 1, 1))
        _own(asset, bob, right=BARE, usufruct_end_date=D(2040, 1, 1))
        form = OtherAssetForm(
            _form_data(owners=[alice.pk, bob.pk, carol.pk]), instance=asset
        )
        assert not form.is_valid()
        assert "no share" in str(form.errors["owners"])

    def test_typed_shares(self):
        alice, bob = _user("alice"), _user("bob")
        asset = _asset()
        _own(asset, alice, 50)
        _own(asset, bob, 50)
        form = OtherAssetForm(instance=asset)
        widget = form.fields["owners"].widget
        assert widget.with_shares
        assert widget.shares == {str(alice.pk): "50", str(bob.pk): "50"}
        assert f'name="owners_share_{alice.pk}" value="50"' in str(form["owners"])
        form = OtherAssetForm(
            _form_data(
                owners=[alice.pk, bob.pk],
                **{
                    f"owners_share_{alice.pk}": "60,5",
                    f"owners_share_{bob.pk}": "39.5",
                },
            ),
            instance=asset,
        )
        assert form.is_valid(), form.errors
        form.save()
        assert _shares(asset) == {
            ("alice", FULL): Decimal("60.5"),
            ("bob", FULL): Decimal("39.5"),
        }
        # Unchanged shares are not saved again.
        form = OtherAssetForm(
            _form_data(owners=[alice.pk], **{f"owners_share_{alice.pk}": "60.5"}),
            instance=asset,
        )
        assert form.is_valid(), form.errors
        assert [plan.save for _asset, plan in form.owners_plans] == [[]]
        form.save()
        assert _shares(asset) == {("alice", FULL): Decimal("60.5")}

    @pytest.mark.parametrize(
        ("alice_share", "bob_share", "error"),
        [
            ("70", "40", "exceed 100"),
            ("70", "", "Enter the share of every owner"),
            ("abc", "10", "Enter the share of every owner"),
            ("0", "10", "Enter the share of every owner"),
        ],
    )
    def test_invalid_shares(self, alice_share, bob_share, error):
        alice, bob = _user("alice"), _user("bob")
        form = OtherAssetForm(
            _form_data(
                owners=[alice.pk, bob.pk],
                **{
                    f"owners_share_{alice.pk}": alice_share,
                    f"owners_share_{bob.pk}": bob_share,
                },
            )
        )
        assert not form.is_valid()
        assert error in str(form.errors["owners"])
        # The typed shares are shown again.
        assert form.fields["owners"].widget.shares[str(alice.pk)] == alice_share

    def test_no_typed_share_for_a_dismembered_asset(self):
        alice = _user("alice")
        asset = _asset()
        _own(asset, alice, right=USUFRUCT, usufruct_end_date=D(2040, 1, 1))
        form = OtherAssetForm(
            _form_data(owners=[alice.pk], **{f"owners_share_{alice.pk}": "10"}),
            instance=asset,
        )
        assert not form.fields["owners"].widget.with_shares
        assert form.is_valid(), form.errors
        form.save()
        assert _shares(asset) == {("alice", USUFRUCT): Decimal(100)}
        assert "owners_share_" not in str(OtherAssetForm(instance=asset)["owners"])

    def test_children_can_own(self, user_client, user):
        child = _user("child-lea", first_name="Léa")
        child.profile.is_child = True
        child.profile.save()
        assert list(household_members())[-1] == child  # children come last
        response = user_client.post(
            reverse("finance:new_other_asset"),
            _form_data(name="Bike", owners=[child.pk]),
        )
        assert response.status_code == 302
        asset = OtherAsset.objects.get(name="Bike")
        assert _shares(asset) == {("child-lea", FULL): Decimal(100)}
        content = user_client.get(response.url).content.decode()
        assert "#baby" in content

    def test_asset_without_owner_is_flagged(self, user_client):
        asset = _asset()
        response = user_client.get(
            reverse("finance:other_asset_detail", args=[asset.pk])
        )
        assert "No owner" in response.content.decode()

    def test_scpi_fund_sets_the_owners_of_its_investments(self):
        alice, bob = _user("alice"), _user("bob")
        scpi = SCPI.objects.create(name="Owned fund")
        investments = [
            SCPIInvestment.objects.create(
                scpi=scpi,
                subscription_date=D(2020, 1, 1),
                shares_count=Decimal(1),
                unit_purchase_price=Money(100, CURRENCY),
            )
            for _index in range(2)
        ]
        _own(investments[0], alice)
        form = SCPIForm(instance=scpi)
        # The investments split their shares differently: none is shown.
        assert form.fields["owners"].widget.shares == {}
        form = SCPIForm(
            {
                "name": "Owned fund",
                "dividend_recurrence": scpi.dividend_recurrence,
                "owners": [alice.pk, bob.pk],
                f"owners_share_{alice.pk}": "70",
                f"owners_share_{bob.pk}": "30",
            },
            instance=scpi,
        )
        assert form.is_valid(), form.errors
        form.save()
        for investment in investments:
            assert _shares(investment) == {
                ("alice", FULL): Decimal(70),
                ("bob", FULL): Decimal(30),
            }
        assert SCPIForm(instance=scpi).fields["owners"].widget.shares == {
            str(alice.pk): "70",
            str(bob.pk): "30",
        }
        assert "owners" not in SCPIForm().fields

    def test_form_pages_show_the_picker(self, user_client, user):
        for url_name in (
            "finance:new_saving",
            "finance:new_investment",
            "finance:new_other_asset",
            "property:create",
            "property:scpi_investment_new",
        ):
            content = user_client.get(reverse(url_name)).content.decode()
            assert "people-picker" in content, url_name


@pytest.mark.django_db
class TestPeopleFilterForm:
    def test_selection(self):
        alice, _bob = _user("alice"), _user("bob")
        members = {u.pk for u in household_members()}
        assert PeopleFilterForm().selected() is None
        assert PeopleFilterForm({"people": []}).selected() is None
        assert PeopleFilterForm({"people": list(members)}).selected() is None
        assert PeopleFilterForm({"people": [alice.pk]}).selected() == {alice.pk}
        assert PeopleFilterForm({"people": ["999999"]}).selected() is None


@pytest.mark.django_db
class TestHeldRatio:
    def test_ratios(self):
        alice, bob = _user("alice"), _user("bob")
        asset = _asset()
        assert held_ratio([], {alice.pk}, TODAY) == 0
        assert held_ratio([], {alice.pk}, TODAY, household=True) == 1
        rows = [
            _own(asset, alice, 50),
            _own(asset, bob, 50, right=BARE),  # cannot be valued
        ]
        assert held_ratio(rows, {alice.pk}, TODAY) == Decimal("0.5")
        assert held_ratio(rows, {bob.pk}, TODAY) == 0
        assert held_ratio(rows, {alice.pk, bob.pk}, TODAY, household=True) == 1
        # A former member's part is held outside the household.
        assert held_ratio(rows, {bob.pk}, TODAY, household=True) == Decimal("0.5")


@pytest.mark.django_db
class TestAllocationByPerson:
    @pytest.fixture
    def household(self):
        alice, bob = _user("alice"), _user("bob")
        saving = SavingAccount.objects.create(
            account_type=SavingAccountType.objects.get_or_create(code="LA", name="LA")[
                0
            ],
            opening_value=Money(10000, CURRENCY),
        )
        _own(saving, alice, 50)
        _own(saving, bob, 50)
        investment = InvestmentAccount.objects.create(
            account_type=InvestmentAccountType.objects.get_or_create(
                code="PEA", name="PEA"
            )[0],
            opening_cash_value=Money(2000, CURRENCY),
        )
        _own(investment, bob)
        house = Property.objects.create(
            name="Half house",
            property_type=Property.HOUSE,
            buying_value=Money(200000, CURRENCY),
            buying_date=D(2020, 1, 1),
        )
        _own(house, alice, 50)  # the other half is held outside the household
        _asset("Unassigned painting", 1000)
        return alice, bob

    def test_household_and_people(self, household):
        alice, bob = household
        whole = compute_allocation(CURRENCY)
        alice_part = compute_allocation(CURRENCY, {alice.pk})
        bob_part = compute_allocation(CURRENCY, {bob.pk})
        assert alice_part.total == Decimal(5000) + Decimal(100000)
        assert bob_part.total == Decimal(5000) + Decimal(2000)
        # The household holds the unassigned assets, not the part held outside.
        assert whole.total == alice_part.total + bob_part.total + Decimal(1000)

    def test_view(self, user_client, household):
        alice, bob = household
        bike = OtherAsset.objects.create(  # in the reference currency of the page
            name="Bike",
            acquisition_value=Money(500, "EUR"),
            acquisition_date=D(2020, 1, 1),
        )
        _own(bike, bob)
        response = user_client.get(reverse("allocation"))
        assert response.context["is_household"]
        assert set(response.context["people_form"]["people"].value()) == {
            u.pk for u in household_members()
        }
        response = user_client.get(reverse("allocation"), {"people": [alice.pk]})
        assert not response.context["is_household"]
        assert (
            response.context["allocation"].total < response.context["household_total"]
        )
        content = response.content.decode()
        assert "Whole household" in content
        assert "people-picker" in content


@pytest.mark.django_db
def test_net_worth_of_children_and_former_members():
    User.objects.update(is_active=False)
    child = _user("child-lea", first_name="Léa")
    child.profile.is_child = True
    child.profile.save()
    former = _user("former", is_active=False)
    asset = _asset(amount=1000)
    _own(asset, child, 50)
    _own(asset, former, 50)
    people, unassigned, outside = net_worth_by_person(CURRENCY, today=TODAY)
    assert [(p.label, p.is_child, p.total) for p in people] == [
        ("Léa", True, Decimal(500))
    ]
    assert unassigned.total == 0
    assert outside.total == Decimal(500)
