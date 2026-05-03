"""Tests for property/views/csv_views.py."""

import datetime
import io
from decimal import Decimal

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from moneyed import Money

from property.models import Property, PropertyLedgerEntry
from property.views.csv_views import (
    _SESSION_DATA_KEY,
    _SESSION_HEADER_KEY,
    _SESSION_PROPERTY_KEY,
)

# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def property_obj():
    return Property.objects.create(
        name="CSV Test Property",
        property_type=Property.APARTMENT,
        buying_value=Money(200_000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
    )


def _make_csv(rows: list[list[str]], header: list[str] | None = None) -> io.BytesIO:
    """Build an in-memory CSV file."""
    if header is None:
        header = ["date", "amount", "category", "description"]
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(str(c) for c in row))
    return io.BytesIO("\n".join(lines).encode("utf-8"))


# ─── csv_import GET ───────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCSVImportGet:
    def test_get_renders_form(self, user_client, property_obj):
        url = reverse("property:csv_import", kwargs={"property_pk": property_obj.pk})
        response = user_client.get(url)
        assert response.status_code == 200
        assert "form" in response.context
        assert "valid_categories" in response.context

    def test_get_unknown_property_returns_404(self, user_client):
        url = reverse("property:csv_import", kwargs={"property_pk": 999999})
        response = user_client.get(url)
        assert response.status_code == 404

    def test_get_requires_login(self, client, property_obj):
        url = reverse("property:csv_import", kwargs={"property_pk": property_obj.pk})
        response = client.get(url)
        assert response.status_code == 302
        assert (
            "/accounts/login" in response["Location"]
            or "/login" in response["Location"]
        )


# ─── csv_import POST ──────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCSVImportPost:
    def _url(self, property_obj):
        return reverse("property:csv_import", kwargs={"property_pk": property_obj.pk})

    def test_valid_csv_stores_session_and_renders_preview(
        self, user_client, property_obj
    ):
        csv_file = _make_csv(
            [
                ["2024-01-15", "800.00", "rent_collected", "January rent"],
                ["2024-01-20", "-150.50", "maintenance", "Plumber"],
            ]
        )
        response = user_client.post(
            self._url(property_obj),
            {"csv_file": csv_file},
            format="multipart",
        )
        assert response.status_code == 200
        assert "preview_rows" in response.context
        assert len(response.context["preview_rows"]) == 2
        assert response.context["total_rows"] == 2
        session = user_client.session
        assert session[_SESSION_DATA_KEY] is not None
        assert session[_SESSION_HEADER_KEY] == [
            "date",
            "amount",
            "category",
            "description",
        ]
        assert session[_SESSION_PROPERTY_KEY] == property_obj.pk

    def test_missing_required_column_shows_error(self, user_client, property_obj):
        csv_file = _make_csv(
            [["2024-01-15", "800.00", "January rent"]],
            header=["date", "amount", "description"],  # missing 'category'
        )
        response = user_client.post(self._url(property_obj), {"csv_file": csv_file})
        assert response.status_code == 200
        msgs = [str(m) for m in get_messages(response.wsgi_request)]
        assert any("category" in m for m in msgs)

    def test_empty_csv_shows_error(self, user_client, property_obj):
        csv_file = io.BytesIO(b"date,amount,category,description\n")
        response = user_client.post(self._url(property_obj), {"csv_file": csv_file})
        assert response.status_code == 200
        msgs = [str(m) for m in get_messages(response.wsgi_request)]
        assert any("no data" in m.lower() for m in msgs)

    def test_completely_empty_file_shows_error(self, user_client, property_obj):
        # Django's FileField rejects empty files via form validation (not a Django message)
        csv_file = io.BytesIO(b"")
        response = user_client.post(self._url(property_obj), {"csv_file": csv_file})
        assert response.status_code == 200
        assert response.context["form"].errors

    def test_non_utf8_file_shows_error(self, user_client, property_obj):
        raw = (
            b"date,amount,category,description\n2024-01-15,800,rent_collected,\xff\xfe"
        )
        csv_file = io.BytesIO(raw)
        response = user_client.post(self._url(property_obj), {"csv_file": csv_file})
        assert response.status_code == 200
        msgs = [str(m) for m in get_messages(response.wsgi_request)]
        assert any("decoded" in m.lower() or "utf" in m.lower() for m in msgs)

    def test_optional_columns_accepted(self, user_client, property_obj):
        csv_file = _make_csv(
            [
                [
                    "2024-01-15",
                    "800.00",
                    "rent_collected",
                    "Rent",
                    "Some notes",
                    "2024-01-01",
                ]
            ],
            header=[
                "date",
                "amount",
                "category",
                "description",
                "notes",
                "reference_period",
            ],
        )
        response = user_client.post(self._url(property_obj), {"csv_file": csv_file})
        assert response.status_code == 200
        assert "preview_rows" in response.context

    def test_post_missing_file_shows_form_errors(self, user_client, property_obj):
        response = user_client.post(self._url(property_obj), {})
        assert response.status_code == 200
        assert response.context["form"].errors


# ─── csv_import_confirm POST ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestCSVImportConfirm:
    def _url(self, property_obj):
        return reverse(
            "property:csv_import_confirm", kwargs={"property_pk": property_obj.pk}
        )

    def _seed_session(self, user_client, property_obj, rows=None, header=None):
        if header is None:
            header = ["date", "amount", "category", "description"]
        if rows is None:
            rows = [
                ["2024-01-15", "800.00", "rent_collected", "January rent"],
                ["2024-01-20", "-150.50", "maintenance", "Plumber"],
            ]
        session = user_client.session
        session[_SESSION_DATA_KEY] = rows
        session[_SESSION_HEADER_KEY] = header
        session[_SESSION_PROPERTY_KEY] = property_obj.pk
        session.save()

    def test_confirm_creates_entries_and_redirects(self, user_client, property_obj):
        self._seed_session(user_client, property_obj)
        response = user_client.post(self._url(property_obj))
        assert response.status_code == 302
        assert response["Location"].endswith(
            reverse("property:detail", kwargs={"pk": property_obj.pk})
        )
        assert PropertyLedgerEntry.objects.filter(property=property_obj).count() == 2

    def test_confirm_income_entry_fields(self, user_client, property_obj):
        self._seed_session(
            user_client,
            property_obj,
            rows=[["2024-03-01", "1000.00", "rent_collected", "March rent"]],
        )
        user_client.post(self._url(property_obj))
        entry = PropertyLedgerEntry.objects.get(property=property_obj)
        assert entry.flow_type == PropertyLedgerEntry.FlowType.INCOME
        assert entry.amount == Money(Decimal("1000.00"), "EUR")
        assert (
            entry.management_category
            == PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED
        )
        assert entry.description == "March rent"
        assert entry.entry_date == datetime.date(2024, 3, 1)

    def test_confirm_expense_entry_fields(self, user_client, property_obj):
        self._seed_session(
            user_client,
            property_obj,
            rows=[["2024-03-05", "-200.00", "insurance", "Home insurance"]],
        )
        user_client.post(self._url(property_obj))
        entry = PropertyLedgerEntry.objects.get(property=property_obj)
        assert entry.flow_type == PropertyLedgerEntry.FlowType.EXPENSE
        assert entry.amount == Money(Decimal("200.00"), "EUR")
        assert (
            entry.management_category
            == PropertyLedgerEntry.ManagementCategory.INSURANCE
        )

    def test_confirm_with_notes_and_reference_period(self, user_client, property_obj):
        self._seed_session(
            user_client,
            property_obj,
            rows=[
                [
                    "2024-03-01",
                    "800.00",
                    "rent_collected",
                    "Rent",
                    "My note",
                    "2024-03-01",
                ]
            ],
            header=[
                "date",
                "amount",
                "category",
                "description",
                "notes",
                "reference_period",
            ],
        )
        user_client.post(self._url(property_obj))
        entry = PropertyLedgerEntry.objects.get(property=property_obj)
        assert entry.notes == "My note"
        assert entry.reference_period == datetime.date(2024, 3, 1)

    def test_confirm_invalid_category_creates_warning(self, user_client, property_obj):
        self._seed_session(
            user_client,
            property_obj,
            rows=[["2024-01-15", "800.00", "invalid_cat", "Test"]],
        )
        response = user_client.post(self._url(property_obj))
        assert response.status_code == 302
        msgs = [str(m) for m in get_messages(response.wsgi_request)]
        assert any("could not be imported" in m.lower() for m in msgs)
        assert PropertyLedgerEntry.objects.filter(property=property_obj).count() == 0

    def test_confirm_invalid_date_creates_warning(self, user_client, property_obj):
        self._seed_session(
            user_client,
            property_obj,
            rows=[["not-a-date", "800.00", "rent_collected", "Test"]],
        )
        user_client.post(self._url(property_obj))
        assert PropertyLedgerEntry.objects.filter(property=property_obj).count() == 0

    def test_confirm_invalid_amount_creates_warning(self, user_client, property_obj):
        self._seed_session(
            user_client,
            property_obj,
            rows=[["2024-01-15", "notanumber", "rent_collected", "Test"]],
        )
        user_client.post(self._url(property_obj))
        assert PropertyLedgerEntry.objects.filter(property=property_obj).count() == 0

    def test_confirm_zero_amount_creates_warning(self, user_client, property_obj):
        self._seed_session(
            user_client,
            property_obj,
            rows=[["2024-01-15", "0", "rent_collected", "Test"]],
        )
        user_client.post(self._url(property_obj))
        assert PropertyLedgerEntry.objects.filter(property=property_obj).count() == 0

    def test_confirm_income_category_with_negative_amount_warns(
        self, user_client, property_obj
    ):
        self._seed_session(
            user_client,
            property_obj,
            rows=[["2024-01-15", "-800.00", "rent_collected", "Test"]],
        )
        user_client.post(self._url(property_obj))
        assert PropertyLedgerEntry.objects.filter(property=property_obj).count() == 0

    def test_confirm_expense_category_with_positive_amount_warns(
        self, user_client, property_obj
    ):
        self._seed_session(
            user_client,
            property_obj,
            rows=[["2024-01-15", "150.00", "maintenance", "Test"]],
        )
        user_client.post(self._url(property_obj))
        assert PropertyLedgerEntry.objects.filter(property=property_obj).count() == 0

    def test_confirm_partial_success(self, user_client, property_obj):
        """Valid + invalid rows: valid ones imported, invalid ones skipped."""
        self._seed_session(
            user_client,
            property_obj,
            rows=[
                ["2024-01-15", "800.00", "rent_collected", "Good row"],
                ["bad-date", "500.00", "rent_collected", "Bad row"],
            ],
        )
        user_client.post(self._url(property_obj))
        assert PropertyLedgerEntry.objects.filter(property=property_obj).count() == 1

    def test_confirm_clears_session(self, user_client, property_obj):
        self._seed_session(user_client, property_obj)
        user_client.post(self._url(property_obj))
        session = user_client.session
        assert _SESSION_DATA_KEY not in session
        assert _SESSION_HEADER_KEY not in session
        assert _SESSION_PROPERTY_KEY not in session

    def test_confirm_expired_session_redirects(self, user_client, property_obj):
        # No session data set
        response = user_client.post(self._url(property_obj))
        assert response.status_code == 302
        assert "csv/import" in response["Location"]

    def test_confirm_wrong_property_in_session_redirects(
        self, user_client, property_obj
    ):
        session = user_client.session
        session[_SESSION_DATA_KEY] = [
            ["2024-01-15", "800.00", "rent_collected", "Test"]
        ]
        session[_SESSION_HEADER_KEY] = ["date", "amount", "category", "description"]
        session[_SESSION_PROPERTY_KEY] = property_obj.pk + 9999  # different pk
        session.save()
        response = user_client.post(self._url(property_obj))
        assert response.status_code == 302
        assert "csv/import" in response["Location"]

    def test_confirm_get_returns_404(self, user_client, property_obj):
        url = reverse(
            "property:csv_import_confirm", kwargs={"property_pk": property_obj.pk}
        )
        response = user_client.get(url)
        assert response.status_code == 404

    def test_confirm_success_message(self, user_client, property_obj):
        self._seed_session(
            user_client,
            property_obj,
            rows=[["2024-01-15", "800.00", "rent_collected", "Rent"]],
        )
        response = user_client.post(self._url(property_obj))
        msgs = [str(m) for m in get_messages(response.wsgi_request)]
        assert any("imported successfully" in m.lower() for m in msgs)

    def test_comma_decimal_amount_parsed(self, user_client, property_obj):
        self._seed_session(
            user_client,
            property_obj,
            rows=[["2024-01-15", "1.200,50", "rent_collected", "Rent comma"]],
        )
        user_client.post(self._url(property_obj))
        entry = PropertyLedgerEntry.objects.get(property=property_obj)
        assert entry.amount.amount == pytest.approx(
            Decimal("1200.50"), rel=Decimal("0.01")
        )

    def test_comma_only_decimal_amount_parsed(self, user_client, property_obj):
        """European format without thousands sep: 1200,50 → 1200.50."""
        self._seed_session(
            user_client,
            property_obj,
            rows=[["2024-01-15", "1200,50", "rent_collected", "Rent comma only"]],
        )
        user_client.post(self._url(property_obj))
        entry = PropertyLedgerEntry.objects.get(property=property_obj)
        assert entry.amount.amount == pytest.approx(
            Decimal("1200.50"), rel=Decimal("0.01")
        )

    def test_us_comma_thousands_amount_parsed(self, user_client, property_obj):
        """US format 1,200.50 (comma = thousands, dot = decimal) is parsed correctly."""
        self._seed_session(
            user_client,
            property_obj,
            rows=[["2024-01-15", "1,200.50", "rent_collected", "Rent US format"]],
        )
        user_client.post(self._url(property_obj))
        entry = PropertyLedgerEntry.objects.get(property=property_obj)
        assert entry.amount.amount == pytest.approx(
            Decimal("1200.50"), rel=Decimal("0.01")
        )

    def test_unexpected_exception_during_create_is_caught(
        self, user_client, property_obj
    ):
        """A generic exception during create is caught and reported as a warning."""
        from unittest.mock import patch

        self._seed_session(
            user_client,
            property_obj,
            rows=[["2024-01-15", "800.00", "rent_collected", "Test exception"]],
        )
        with patch(
            "property.views.csv_views.PropertyLedgerEntry.objects.create",
            side_effect=RuntimeError("unexpected db error"),
        ):
            response = user_client.post(self._url(property_obj))
        assert response.status_code == 302
        msgs = [str(m) for m in get_messages(response.wsgi_request)]
        assert any("could not be imported" in m.lower() for m in msgs)
        assert PropertyLedgerEntry.objects.filter(property=property_obj).count() == 0
