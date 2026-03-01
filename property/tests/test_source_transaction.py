"""Tests for AmortizationAsset.source_transactions — capitalized works feature.

Covers:
- Capitalized transaction excluded from LMNP charges
- Non-capitalized transaction included normally
- M2M deletion removes link but preserves the asset
- Form filters only eligible transactions for the property
- Multiple transactions can be linked to a single asset (M2M)
"""

import datetime
from typing import cast

import pytest
from django.forms import ModelMultipleChoiceField
from moneyed import Money

from property.forms import AmortizationAssetForm
from property.models import AmortizationAsset, Property, PropertyLedgerEntry
from property.services.tax_lmnp import _get_category_totals_for_year, get_lmnp_summary

# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def prop(db):
    return Property.objects.create(
        name="Capitalization Test Property",
        property_type=Property.APARTMENT,
        buying_value=Money(200_000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
        tax_regime=Property.TaxRegime.LMNP_REEL,
    )


@pytest.fixture
def other_prop(db):
    return Property.objects.create(
        name="Other Property",
        property_type=Property.APARTMENT,
        buying_value=Money(100_000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
        tax_regime=Property.TaxRegime.LMNP_REEL,
    )


def _make_works_entry(prop, amount=5000, date=None, description="Roof repair"):
    return PropertyLedgerEntry.objects.create(
        property=prop,
        flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
        management_category="works",
        amount=Money(amount, "EUR"),
        entry_date=date or datetime.date(2023, 3, 15),
        description=description,
        recurrence_type=PropertyLedgerEntry.RecurrenceType.NONE,
    )


def _make_income_entry(prop, amount=10000):
    return PropertyLedgerEntry.objects.create(
        property=prop,
        flow_type=PropertyLedgerEntry.FlowType.INCOME,
        management_category="rent_collected",
        amount=Money(amount, "EUR"),
        entry_date=datetime.date(2023, 6, 1),
        recurrence_type=PropertyLedgerEntry.RecurrenceType.NONE,
    )


def _make_asset(prop, tx=None, amount=5000):
    asset = AmortizationAsset.objects.create(
        property=prop,
        label="Roof",
        beginning_date=datetime.date(2023, 3, 15),
        value_total=Money(amount, "EUR"),
        duration_years=25,
    )
    if tx is not None:
        asset.source_transactions.add(tx)
    return asset


# ─── Tax calculation exclusion ────────────────────────────────────────────────


@pytest.mark.django_db
class TestCapitalizedTransactionExclusion:
    def test_linked_transaction_excluded_from_category_totals(self, prop):
        """A works transaction linked to an asset must not appear in category totals."""
        tx = _make_works_entry(prop)
        _make_asset(prop, tx=tx)

        totals = _get_category_totals_for_year(prop.pk, 2023)
        assert "works" not in totals or totals.get("works", 0) == 0

    def test_unlinked_transaction_included_in_category_totals(self, prop):
        """A works transaction NOT linked to any asset must appear in category totals."""
        _make_works_entry(prop, amount=3000)

        totals = _get_category_totals_for_year(prop.pk, 2023)
        assert totals.get("works") == 3000

    def test_only_linked_transaction_excluded_when_both_exist(self, prop):
        """When two works entries exist and one is linked, only the unlinked one counts."""
        tx_linked = _make_works_entry(prop, amount=5000, description="Capitalized roof")
        _make_works_entry(prop, amount=2000, description="Minor repair")
        _make_asset(prop, tx=tx_linked)

        totals = _get_category_totals_for_year(prop.pk, 2023)
        assert totals.get("works") == 2000

    def test_multiple_transactions_linked_to_asset_are_all_excluded(self, prop):
        """All transactions linked to an asset must be excluded from category totals."""
        tx1 = _make_works_entry(prop, amount=3000, description="Invoice 1")
        tx2 = _make_works_entry(prop, amount=2000, description="Invoice 2")
        asset = _make_asset(prop, tx=tx1)
        asset.source_transactions.add(tx2)

        totals = _get_category_totals_for_year(prop.pk, 2023)
        assert "works" not in totals or totals.get("works", 0) == 0

    def test_linked_transaction_excluded_from_lmnp_charges(self, prop):
        """The LMNP summary charges total must exclude capitalized transactions."""
        _make_income_entry(prop, amount=10_000)
        tx = _make_works_entry(prop, amount=5_000)
        _make_asset(prop, tx=tx)

        summary = get_lmnp_summary(prop.pk, 2023)
        # charges should be 0 since the only expense is capitalized
        assert summary["charges"] == 0

    def test_unlinked_works_entry_appears_in_charges(self, prop):
        """Without an asset link, a works entry reduces taxable income normally."""
        _make_income_entry(prop, amount=10_000)
        _make_works_entry(prop, amount=4_000)

        summary = get_lmnp_summary(prop.pk, 2023)
        assert summary["charges"] == 4_000


# ─── M2M deletion removes link ────────────────────────────────────────────────


@pytest.mark.django_db
class TestSourceTransactionRemoval:
    def test_delete_transaction_removes_m2m_link(self, prop):
        """Deleting a linked transaction must remove it from the M2M relation."""
        tx = _make_works_entry(prop)
        asset = _make_asset(prop, tx=tx)

        assert asset.source_transactions.filter(pk=tx.pk).exists()

        tx.delete()
        asset.refresh_from_db()
        assert not asset.source_transactions.exists()

    def test_asset_preserved_after_transaction_deletion(self, prop):
        """The asset itself must still exist after its source transaction is deleted."""
        tx = _make_works_entry(prop)
        asset = _make_asset(prop, tx=tx)
        asset_pk = asset.pk

        tx.delete()
        assert AmortizationAsset.objects.filter(pk=asset_pk).exists()


# ─── Form queryset filtering ───────────────────────────────────────────────────


@pytest.mark.django_db
class TestAmortizationAssetFormFiltering:
    def test_form_shows_eligible_works_transactions(self, prop):
        """Form queryset must include unlinked works/maintenance expenses."""
        tx_works = _make_works_entry(prop, description="Works tx")
        maint_tx = PropertyLedgerEntry.objects.create(
            property=prop,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category="maintenance",
            amount=Money(1000, "EUR"),
            entry_date=datetime.date(2023, 5, 1),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.NONE,
        )

        form = AmortizationAssetForm(property_obj=prop)
        qs = cast(ModelMultipleChoiceField, form.fields["source_transactions"]).queryset
        assert qs is not None
        pks = list(qs.values_list("pk", flat=True))

        assert tx_works.pk in pks
        assert maint_tx.pk in pks

    def test_form_excludes_already_linked_transactions(self, prop):
        """With M2M, already-linked transactions are still shown (many assets can share one tx)."""
        tx = _make_works_entry(prop)
        _make_asset(prop, tx=tx)  # links tx to an asset

        form = AmortizationAssetForm(property_obj=prop)
        qs = cast(ModelMultipleChoiceField, form.fields["source_transactions"]).queryset
        assert qs is not None
        pks = list(qs.values_list("pk", flat=True))

        # M2M: same transaction can be linked to multiple assets, so it stays in the list
        assert tx.pk in pks

    def test_form_includes_own_linked_transactions_when_editing(self, prop):
        """When editing an asset, its linked transactions must appear in queryset."""
        tx = _make_works_entry(prop)
        asset = _make_asset(prop, tx=tx)

        form = AmortizationAssetForm(instance=asset, property_obj=prop)
        qs = cast(ModelMultipleChoiceField, form.fields["source_transactions"]).queryset
        assert qs is not None
        pks = list(qs.values_list("pk", flat=True))

        assert tx.pk in pks

    def test_form_excludes_income_entries(self, prop):
        """Income entries must not appear in the source_transactions queryset."""
        income_tx = _make_income_entry(prop)

        form = AmortizationAssetForm(property_obj=prop)
        qs = cast(ModelMultipleChoiceField, form.fields["source_transactions"]).queryset
        assert qs is not None
        pks = list(qs.values_list("pk", flat=True))

        assert income_tx.pk not in pks

    def test_form_excludes_other_property_transactions(self, prop, other_prop):
        """Transactions from another property must not appear in the queryset."""
        other_tx = _make_works_entry(other_prop, description="Other property tx")

        form = AmortizationAssetForm(property_obj=prop)
        qs = cast(ModelMultipleChoiceField, form.fields["source_transactions"]).queryset
        assert qs is not None
        pks = list(qs.values_list("pk", flat=True))

        assert other_tx.pk not in pks

    def test_form_with_no_property_obj_returns_empty_queryset(self):
        """Without property_obj, the queryset must be empty."""
        form = AmortizationAssetForm()
        qs = cast(ModelMultipleChoiceField, form.fields["source_transactions"]).queryset
        assert qs is not None
        assert not qs.exists()

    def test_source_transactions_field_is_not_required(self, prop):
        """The source_transactions field must be optional."""
        form = AmortizationAssetForm(property_obj=prop)
        assert not form.fields["source_transactions"].required

    def test_form_excludes_recurring_transactions(self, prop):
        """Recurring entries must not appear in the queryset."""
        recurring_tx = PropertyLedgerEntry.objects.create(
            property=prop,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category="works",
            amount=Money(1000, "EUR"),
            entry_date=datetime.date(2023, 1, 1),
            recurrence_type=PropertyLedgerEntry.RecurrenceType.MONTHLY,
        )

        form = AmortizationAssetForm(property_obj=prop)
        qs = cast(ModelMultipleChoiceField, form.fields["source_transactions"]).queryset
        assert qs is not None
        pks = list(qs.values_list("pk", flat=True))

        assert recurring_tx.pk not in pks
