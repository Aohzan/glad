"""Tests for property/views/scpi_views.py."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from moneyed import Money

from property.models.scpi import SCPI, SCPIDividend, SCPIInvestment, SCPISharePrice

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def scpi():
    return SCPI.objects.create(
        name="Test SCPI",
        management_company="Test AM",
        entry_fee_rate=Decimal("8.00"),
        exit_fee_rate=Decimal("0.00"),
    )


@pytest.fixture
def share_price(scpi):
    return SCPISharePrice.objects.create(
        scpi=scpi,
        date=datetime.date(2024, 1, 1),
        subscription_value=Money(Decimal("1080.00"), "EUR"),
        withdrawal_value=Money(Decimal("1020.00"), "EUR"),
    )


@pytest.fixture
def investment(scpi, share_price):
    return SCPIInvestment.objects.create(
        scpi=scpi,
        subscription_date=datetime.date(2023, 6, 1),
        shares_count=Decimal("10.0000"),
        unit_purchase_price=Money(Decimal("1000.00"), "EUR"),
        ownership_type=SCPIInvestment.OwnershipType.FULL,
    )


@pytest.fixture
def dividend(scpi):
    return SCPIDividend.objects.create(
        scpi=scpi,
        payment_date=datetime.date(2024, 3, 31),
        net_amount=Money(Decimal("120.00"), "EUR"),
    )


# ── SCPI List ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSCPIListView:
    def test_get_list_empty(self, user_client):
        url = reverse("property:scpi_list")
        response = user_client.get(url)
        assert response.status_code == 200

    def test_get_list_with_data(self, user_client, investment):
        url = reverse("property:scpi_list")
        response = user_client.get(url)
        assert response.status_code == 200
        assert b"Test SCPI" in response.content

    def test_requires_login(self, client):
        url = reverse("property:scpi_list")
        response = client.get(url)
        assert response.status_code == 302


# ── SCPI Fund Detail ─────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSCPIFundDetailView:
    def test_get_fund_detail(self, user_client, investment):
        url = reverse(
            "property:scpi_fund_detail", kwargs={"scpi_pk": investment.scpi.pk}
        )
        response = user_client.get(url)
        assert response.status_code == 200
        assert b"Test SCPI" in response.content

    def test_get_fund_detail_not_found(self, user_client):
        url = reverse("property:scpi_fund_detail", kwargs={"scpi_pk": 9999})
        response = user_client.get(url)
        assert response.status_code == 404

    def test_shows_dividends(self, user_client, investment, dividend):
        url = reverse(
            "property:scpi_fund_detail", kwargs={"scpi_pk": investment.scpi.pk}
        )
        response = user_client.get(url)
        assert response.status_code == 200
        assert b"120" in response.content


# ── SCPI Fund CRUD ────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestEditSCPI:
    def test_get_create_form(self, user_client):
        url = reverse("property:scpi_new")
        response = user_client.get(url)
        assert response.status_code == 200

    def test_post_create_scpi(self, user_client):
        url = reverse("property:scpi_new")
        data = {
            "name": "New Fund",
            "management_company": "Fund AM",
            "entry_fee_rate": "7.50",
            "exit_fee_rate": "",
            "dividend_recurrence": "quarterly",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        assert SCPI.objects.filter(name="New Fund").exists()

    def test_get_edit_form(self, user_client, scpi):
        url = reverse("property:scpi_edit", kwargs={"scpi_pk": scpi.pk})
        response = user_client.get(url)
        assert response.status_code == 200

    def test_post_edit_scpi(self, user_client, scpi):
        url = reverse("property:scpi_edit", kwargs={"scpi_pk": scpi.pk})
        data = {
            "name": "Renamed Fund",
            "management_company": "Test AM",
            "entry_fee_rate": "8.00",
            "exit_fee_rate": "0.00",
            "dividend_recurrence": "quarterly",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        scpi.refresh_from_db()
        assert scpi.name == "Renamed Fund"


@pytest.mark.django_db
class TestDeleteSCPI:
    def test_post_delete(self, user_client, scpi):
        pk = scpi.pk
        url = reverse("property:scpi_delete", kwargs={"scpi_pk": pk})
        response = user_client.post(url)
        assert response.status_code == 302
        assert not SCPI.objects.filter(pk=pk).exists()

    def test_get_delete_redirects(self, user_client, scpi):
        url = reverse("property:scpi_delete", kwargs={"scpi_pk": scpi.pk})
        response = user_client.get(url)
        assert response.status_code == 302


# ── SCPI Share Price CRUD ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSCPISharePriceViews:
    def test_get_add_price_form(self, user_client, scpi):
        url = reverse("property:scpi_share_price_add", kwargs={"scpi_pk": scpi.pk})
        response = user_client.get(url)
        assert response.status_code == 200

    def test_post_add_price(self, user_client, scpi):
        url = reverse("property:scpi_share_price_add", kwargs={"scpi_pk": scpi.pk})
        data = {
            "date": "2025-01-01",
            "subscription_value_0": "1100.00",
            "subscription_value_1": "EUR",
            "withdrawal_value_0": "",
            "withdrawal_value_1": "EUR",
        }
        response = user_client.post(url, data)
        assert response.status_code in (200, 302)

    def test_post_delete_price(self, user_client, scpi, share_price):
        url = reverse(
            "property:scpi_share_price_delete",
            kwargs={"scpi_pk": scpi.pk, "price_pk": share_price.pk},
        )
        response = user_client.post(url)
        assert response.status_code == 302
        assert not SCPISharePrice.objects.filter(pk=share_price.pk).exists()

    def test_get_delete_price_redirects(self, user_client, scpi, share_price):
        url = reverse(
            "property:scpi_share_price_delete",
            kwargs={"scpi_pk": scpi.pk, "price_pk": share_price.pk},
        )
        response = user_client.get(url)
        assert response.status_code == 302


# ── SCPI Investment CRUD ──────────────────────────────────────────────────────


@pytest.mark.django_db
class TestEditSCPIInvestment:
    def test_get_create_form(self, user_client):
        url = reverse("property:scpi_investment_new")
        response = user_client.get(url)
        assert response.status_code == 200

    def test_post_create_investment(self, user_client, scpi):
        url = reverse("property:scpi_investment_new")
        data = {
            "scpi": scpi.pk,
            "subscription_date": "2023-06-01",
            "shares_count": "5.0000",
            "unit_purchase_price_0": "1000.00",
            "unit_purchase_price_1": "EUR",
            "enjoyment_date": "",
            "ownership_type": "full",
            "dismemberment_start_date": "",
            "dismemberment_end_date": "",
            "bare_ownership_ratio": "",
            "notes": "",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        assert SCPIInvestment.objects.filter(scpi=scpi).exists()

    def test_get_edit_form(self, user_client, investment):
        url = reverse(
            "property:scpi_investment_edit", kwargs={"investment_pk": investment.pk}
        )
        response = user_client.get(url)
        assert response.status_code == 200

    def test_post_edit_investment(self, user_client, investment):
        url = reverse(
            "property:scpi_investment_edit", kwargs={"investment_pk": investment.pk}
        )
        data = {
            "scpi": investment.scpi.pk,
            "subscription_date": "2023-06-01",
            "shares_count": "15.0000",  # changed
            "unit_purchase_price_0": "1000.00",
            "unit_purchase_price_1": "EUR",
            "enjoyment_date": "",
            "ownership_type": "full",
            "dismemberment_start_date": "",
            "dismemberment_end_date": "",
            "bare_ownership_ratio": "",
            "notes": "",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        investment.refresh_from_db()
        assert investment.shares_count == Decimal("15.0000")


@pytest.mark.django_db
class TestDeleteSCPIInvestment:
    def test_post_delete(self, user_client, investment):
        pk = investment.pk
        url = reverse("property:scpi_investment_delete", kwargs={"investment_pk": pk})
        response = user_client.post(url)
        assert response.status_code == 302
        assert not SCPIInvestment.objects.filter(pk=pk).exists()

    def test_get_delete_redirects(self, user_client, investment):
        url = reverse(
            "property:scpi_investment_delete", kwargs={"investment_pk": investment.pk}
        )
        response = user_client.get(url)
        assert response.status_code == 302


# ── Dividend CRUD ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSCPIDividendViews:
    def test_get_add_dividend_form(self, user_client, scpi):
        url = reverse("property:scpi_dividend_add", kwargs={"scpi_pk": scpi.pk})
        response = user_client.get(url)
        assert response.status_code == 200

    def test_post_add_dividend(self, user_client, scpi):
        url = reverse("property:scpi_dividend_add", kwargs={"scpi_pk": scpi.pk})
        data = {
            "payment_date": "2024-03-31",
            "gross_amount_0": "130.00",
            "gross_amount_1": "EUR",
            "net_amount_0": "120.00",
            "net_amount_1": "EUR",
            "notes": "",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        assert SCPIDividend.objects.filter(scpi=scpi).exists()

    def test_get_edit_dividend_form(self, user_client, scpi, dividend):
        url = reverse(
            "property:scpi_dividend_edit",
            kwargs={"scpi_pk": scpi.pk, "dividend_pk": dividend.pk},
        )
        response = user_client.get(url)
        assert response.status_code == 200

    def test_post_edit_dividend(self, user_client, scpi, dividend):
        url = reverse(
            "property:scpi_dividend_edit",
            kwargs={"scpi_pk": scpi.pk, "dividend_pk": dividend.pk},
        )
        data = {
            "payment_date": "2024-03-31",
            "gross_amount_0": "",
            "gross_amount_1": "EUR",
            "net_amount_0": "150.00",
            "net_amount_1": "EUR",
            "notes": "updated",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        dividend.refresh_from_db()
        assert dividend.net_amount.amount == Decimal("150.00")

    def test_post_delete_dividend(self, user_client, scpi, dividend):
        pk = dividend.pk
        url = reverse(
            "property:scpi_dividend_delete",
            kwargs={"scpi_pk": scpi.pk, "dividend_pk": pk},
        )
        response = user_client.post(url)
        assert response.status_code == 302
        assert not SCPIDividend.objects.filter(pk=pk).exists()

    def test_get_delete_dividend_redirects(self, user_client, scpi, dividend):
        url = reverse(
            "property:scpi_dividend_delete",
            kwargs={"scpi_pk": scpi.pk, "dividend_pk": dividend.pk},
        )
        response = user_client.get(url)
        assert response.status_code == 302

    def test_post_invalid_add_dividend(self, user_client, scpi):
        """Invalid POST on add-dividend should re-render the form with errors."""
        url = reverse("property:scpi_dividend_add", kwargs={"scpi_pk": scpi.pk})
        response = user_client.post(url, {})  # empty form
        assert response.status_code == 200  # stays on form

    def test_post_invalid_edit_dividend(self, user_client, scpi, dividend):
        """Invalid POST on edit-dividend should re-render the form with errors."""
        url = reverse(
            "property:scpi_dividend_edit",
            kwargs={"scpi_pk": scpi.pk, "dividend_pk": dividend.pk},
        )
        response = user_client.post(url, {})  # empty form
        assert response.status_code == 200


# ── Additional coverage ────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSCPIViewsCoverage:
    def test_post_invalid_add_share_price(self, user_client, scpi):
        """Invalid POST on add-share-price should show error and re-render."""
        url = reverse("property:scpi_share_price_add", kwargs={"scpi_pk": scpi.pk})
        response = user_client.post(url, {})  # empty → invalid
        assert response.status_code == 200

    def test_post_invalid_edit_scpi_fund(self, user_client, scpi):
        """Invalid POST on edit-scpi should re-render the form."""
        url = reverse("property:scpi_edit", kwargs={"scpi_pk": scpi.pk})
        response = user_client.post(url, {})  # empty → invalid (name required)
        assert response.status_code == 200

    def test_post_invalid_create_investment(self, user_client):
        """Invalid POST on create-investment should re-render the form."""
        url = reverse("property:scpi_investment_new")
        response = user_client.post(url, {})  # empty → invalid
        assert response.status_code == 200
