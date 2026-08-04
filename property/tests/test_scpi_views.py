"""Tests for property/views/scpi_views.py."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from moneyed import Money

from property.models.scpi import (
    SCPI,
    SCPIBareOwnershipTheoreticalValue,
    SCPIDividend,
    SCPIInvestment,
    SCPISharePrice,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def scpi():
    return SCPI.objects.create(
        name="Test SCPI",
        management_company="Test AM",
        entry_fee_rate=Decimal("8.0000"),
        exit_fee_rate=Decimal("0.0000"),
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

    def test_fund_detail_has_estimated_value_in_context(self, user_client, investment):
        url = reverse(
            "property:scpi_fund_detail", kwargs={"scpi_pk": investment.scpi.pk}
        )
        response = user_client.get(url)
        assert response.status_code == 200
        assert "total_estimated_value" in response.context
        assert "chart_estimated_monthly" in response.context

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
            "entry_fee_rate": "7.5000",
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
            "entry_fee_rate": "8.0000",
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
            "sold_date": "",
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
            "sold_date": "",
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

    def test_add_dividend_form_defaults_date_to_today(self, user_client, scpi):
        """The add-dividend form should default payment_date to today."""
        url = reverse("property:scpi_dividend_add", kwargs={"scpi_pk": scpi.pk})
        response = user_client.get(url)
        assert response.status_code == 200
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        assert today_str.encode() in response.content


# ── Dividend batch ──────────────────────────────────────────────────────────


@pytest.fixture
def scpi2():
    return SCPI.objects.create(name="Second SCPI", management_company="Other AM")


@pytest.mark.django_db
class TestSCPIDividendBatch:
    def test_get_batch_form_empty(self, user_client):
        url = reverse("property:scpi_dividend_batch")
        response = user_client.get(url)
        assert response.status_code == 200

    def test_get_batch_form_with_funds(self, user_client, scpi, scpi2):
        url = reverse("property:scpi_dividend_batch")
        response = user_client.get(url)
        assert response.status_code == 200
        assert b"Test SCPI" in response.content
        assert b"Second SCPI" in response.content

    def test_get_batch_form_defaults_date_to_today(self, user_client, scpi):
        url = reverse("property:scpi_dividend_batch")
        response = user_client.get(url)
        assert response.status_code == 200
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        assert today_str.encode() in response.content

    def test_requires_login(self, client):
        url = reverse("property:scpi_dividend_batch")
        response = client.get(url)
        assert response.status_code == 302

    def test_post_creates_dividends(self, user_client, scpi, scpi2):
        url = reverse("property:scpi_dividend_batch")
        data = {
            "payment_date": "2024-06-30",
            "dividends-TOTAL_FORMS": "2",
            "dividends-INITIAL_FORMS": "0",
            "dividends-MIN_NUM_FORMS": "0",
            "dividends-MAX_NUM_FORMS": "1000",
            "dividends-0-update_dividend": "on",
            "dividends-0-scpi_id": str(scpi.pk),
            "dividends-0-scpi_name": scpi.name,
            "dividends-0-gross_amount": "150.00",
            "dividends-0-net_amount": "120.00",
            "dividends-1-update_dividend": "on",
            "dividends-1-scpi_id": str(scpi2.pk),
            "dividends-1-scpi_name": scpi2.name,
            "dividends-1-gross_amount": "",
            "dividends-1-net_amount": "80.00",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        assert SCPIDividend.objects.filter(scpi=scpi).count() == 1
        assert SCPIDividend.objects.filter(scpi=scpi2).count() == 1
        div0 = SCPIDividend.objects.get(scpi=scpi)
        assert div0.payment_date == datetime.date(2024, 6, 30)
        assert div0.gross_amount.amount == Decimal("150.00")
        assert div0.net_amount.amount == Decimal("120.00")
        div1 = SCPIDividend.objects.get(scpi=scpi2)
        assert div1.gross_amount is None
        assert div1.net_amount.amount == Decimal("80.00")

    def test_post_skips_unchecked_rows(self, user_client, scpi, scpi2):
        url = reverse("property:scpi_dividend_batch")
        data = {
            "payment_date": "2024-06-30",
            "dividends-TOTAL_FORMS": "2",
            "dividends-INITIAL_FORMS": "0",
            "dividends-MIN_NUM_FORMS": "0",
            "dividends-MAX_NUM_FORMS": "1000",
            "dividends-0-update_dividend": "on",
            "dividends-0-scpi_id": str(scpi.pk),
            "dividends-0-scpi_name": scpi.name,
            "dividends-0-gross_amount": "",
            "dividends-0-net_amount": "100.00",
            "dividends-1-update_dividend": "",
            "dividends-1-scpi_id": str(scpi2.pk),
            "dividends-1-scpi_name": scpi2.name,
            "dividends-1-gross_amount": "",
            "dividends-1-net_amount": "",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        assert SCPIDividend.objects.filter(scpi=scpi).count() == 1
        assert SCPIDividend.objects.filter(scpi=scpi2).count() == 0

    def test_post_nothing_checked_shows_info(self, user_client, scpi):
        url = reverse("property:scpi_dividend_batch")
        data = {
            "payment_date": "2024-06-30",
            "dividends-TOTAL_FORMS": "1",
            "dividends-INITIAL_FORMS": "0",
            "dividends-MIN_NUM_FORMS": "0",
            "dividends-MAX_NUM_FORMS": "1000",
            "dividends-0-update_dividend": "",
            "dividends-0-scpi_id": str(scpi.pk),
            "dividends-0-scpi_name": scpi.name,
            "dividends-0-gross_amount": "",
            "dividends-0-net_amount": "",
        }
        response = user_client.post(url, data, follow=True)
        assert response.status_code == 200
        assert SCPIDividend.objects.filter(scpi=scpi).count() == 0

    def test_post_checked_without_net_amount_skips(self, user_client, scpi):
        """If checkbox is checked but net_amount is empty, row is skipped."""
        url = reverse("property:scpi_dividend_batch")
        data = {
            "payment_date": "2024-06-30",
            "dividends-TOTAL_FORMS": "1",
            "dividends-INITIAL_FORMS": "0",
            "dividends-MIN_NUM_FORMS": "0",
            "dividends-MAX_NUM_FORMS": "1000",
            "dividends-0-update_dividend": "on",
            "dividends-0-scpi_id": str(scpi.pk),
            "dividends-0-scpi_name": scpi.name,
            "dividends-0-gross_amount": "",
            "dividends-0-net_amount": "",
        }
        response = user_client.post(url, data, follow=True)
        assert response.status_code == 200
        assert SCPIDividend.objects.filter(scpi=scpi).count() == 0


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


# ── Theoretical value views ───────────────────────────────────────────────────


@pytest.fixture
def investment_bare(scpi, share_price):
    return SCPIInvestment.objects.create(
        scpi=scpi,
        subscription_date=datetime.date(2020, 1, 1),
        shares_count=Decimal("20.0000"),
        unit_purchase_price=Money(Decimal("650.00"), "EUR"),
        ownership_type=SCPIInvestment.OwnershipType.BARE,
        dismemberment_start_date=datetime.date(2020, 1, 1),
        dismemberment_end_date=datetime.date(2030, 1, 1),
        bare_ownership_ratio=Decimal("65.00"),
    )


@pytest.fixture
def theoretical_value(investment_bare):
    return SCPIBareOwnershipTheoreticalValue.objects.create(
        investment=investment_bare,
        date=datetime.date(2023, 1, 1),
        value=Money(Decimal("14000.00"), "EUR"),
    )


@pytest.mark.django_db
class TestSCPITheoreticalValueViews:
    def test_get_add_theoretical_value_form(self, user_client, investment_bare):
        url = reverse(
            "property:scpi_theoretical_value_add",
            kwargs={"investment_pk": investment_bare.pk},
        )
        response = user_client.get(url)
        assert response.status_code == 200

    def test_post_add_theoretical_value(self, user_client, investment_bare):
        url = reverse(
            "property:scpi_theoretical_value_add",
            kwargs={"investment_pk": investment_bare.pk},
        )
        data = {
            "date": "2024-01-01",
            "value_0": "15000.00",
            "value_1": "EUR",
            "notes": "",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        assert SCPIBareOwnershipTheoreticalValue.objects.filter(
            investment=investment_bare
        ).exists()

    def test_get_edit_theoretical_value_form(
        self, user_client, investment_bare, theoretical_value
    ):
        url = reverse(
            "property:scpi_theoretical_value_edit",
            kwargs={
                "investment_pk": investment_bare.pk,
                "value_pk": theoretical_value.pk,
            },
        )
        response = user_client.get(url)
        assert response.status_code == 200

    def test_post_edit_theoretical_value(
        self, user_client, investment_bare, theoretical_value
    ):
        url = reverse(
            "property:scpi_theoretical_value_edit",
            kwargs={
                "investment_pk": investment_bare.pk,
                "value_pk": theoretical_value.pk,
            },
        )
        data = {
            "date": "2023-01-01",
            "value_0": "16000.00",
            "value_1": "EUR",
            "notes": "updated",
        }
        response = user_client.post(url, data)
        assert response.status_code == 302
        theoretical_value.refresh_from_db()
        assert theoretical_value.value.amount == Decimal("16000.00")

    def test_post_delete_theoretical_value(
        self, user_client, investment_bare, theoretical_value
    ):
        pk = theoretical_value.pk
        url = reverse(
            "property:scpi_theoretical_value_delete",
            kwargs={"investment_pk": investment_bare.pk, "value_pk": pk},
        )
        response = user_client.post(url)
        assert response.status_code == 302
        assert not SCPIBareOwnershipTheoreticalValue.objects.filter(pk=pk).exists()

    def test_get_delete_theoretical_value_redirects(
        self, user_client, investment_bare, theoretical_value
    ):
        url = reverse(
            "property:scpi_theoretical_value_delete",
            kwargs={
                "investment_pk": investment_bare.pk,
                "value_pk": theoretical_value.pk,
            },
        )
        response = user_client.get(url)
        assert response.status_code == 302

    def test_post_invalid_add_theoretical_value(self, user_client, investment_bare):
        url = reverse(
            "property:scpi_theoretical_value_add",
            kwargs={"investment_pk": investment_bare.pk},
        )
        response = user_client.post(url, {})  # empty → invalid
        assert response.status_code == 200

    def test_fund_detail_shows_theoretical_value_indicator(
        self, user_client, investment_bare, theoretical_value
    ):
        """Fund detail page shows the theoretical value indicator on bare investment."""
        url = reverse(
            "property:scpi_fund_detail",
            kwargs={"scpi_pk": investment_bare.scpi.pk},
        )
        response = user_client.get(url)
        assert response.status_code == 200
        assert b"bi-bookmark-check" in response.content
