"""Tests for property/services/ledger_csv.py and the AI prompt page."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import translation
from moneyed import Money

from property.models import Property
from property.services.ledger_csv import (
    LedgerCSVError,
    ai_prompt,
    parse_entries,
    read_rows,
    resolve_categories,
    resolve_category,
)

HEADER = ["date", "amount", "category", "description"]


# ── read_rows ─────────────────────────────────────────────────────────────────


def test_read_rows_french_headers_semicolon_latin1():
    data = "Date;Montant;Catégorie;Libellé;Commentaire;Période\n15/01/2024;800;rent_collected;Loyer;;\n"
    header, rows = read_rows(data.encode("latin-1"))
    assert header == [
        "date",
        "amount",
        "category",
        "description",
        "notes",
        "reference_period",
    ]
    assert rows == [["15/01/2024", "800", "rent_collected", "Loyer", "", ""]]


def test_read_rows_comma_utf8_bom_and_unknown_column():
    data = (
        "﻿date,amount,category,description,lot\n2024-01-15,800,rent_collected,Rent,A\n"
    )
    header, rows = read_rows(data.encode("utf-8"))
    assert header == ["date", "amount", "category", "description", "lot"]
    assert rows[0][4] == "A"


def test_read_rows_skips_blank_lines_before_the_header():
    header, rows = read_rows(
        b" \r\n\t\n\ndate;amount;category;description\n2024-01-15;1;rent_collected;x\n"
    )
    assert header == HEADER
    assert rows == [["2024-01-15", "1", "rent_collected", "x"]]


def test_read_rows_duplicate_column_keeps_the_first():
    header, _rows = read_rows(
        b"date;amount;montant;category;description\n2024-01-15;1;2;rent_collected;x\n"
    )
    assert header == ["date", "amount", "", "category", "description"]


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"", "empty"),
        (b"\n\n", "empty"),
        (b" \r\n\t\n", "empty"),
        (b"date;amount;description\n2024-01-15;1;x\n", "category"),
        (b"date;amount;category;description\n;;;\n", "no data"),
    ],
)
def test_read_rows_errors(data, message):
    with pytest.raises(LedgerCSVError) as error:
        read_rows(data)
    assert message in str(error.value).lower()


# ── categories ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw", ["rent_collected", "RENT_COLLECTED", "Rent collected", " rent  COLLECTED "]
)
def test_resolve_category_by_code_or_english_label(raw):
    assert resolve_category(raw) == "rent_collected"


def test_resolve_category_by_french_label():
    with translation.override("fr"):
        assert resolve_category("loyer encaisse") == "rent_collected"
        # The English label is accepted too.
        assert resolve_category("Rent collected") == "rent_collected"


def test_resolve_category_by_french_label_in_english():
    """A French export is read the same when the user works in English."""
    with translation.override("en"):
        assert resolve_category("Loyer encaissé") == "rent_collected"
        assert resolve_category("taxe foncière") == "property_tax"


def test_resolve_category_unknown():
    assert resolve_category("Encaissement locataire") is None


def test_resolve_categories_keeps_unknown_and_short_rows():
    rows = [
        ["2024-01-15", "800", "Rent collected", "Rent"],
        ["2024-01-15", "800", "whatever", "Rent"],
        ["2024-01-15"],
    ]
    assert resolve_categories(HEADER, rows) == [
        ["2024-01-15", "800", "rent_collected", "Rent"],
        ["2024-01-15", "800", "whatever", "Rent"],
        ["2024-01-15"],
    ]


# ── parse_entries ─────────────────────────────────────────────────────────────


def test_parse_entries_valid_rows():
    entries, errors = parse_entries(
        [*HEADER, "notes", "reference_period"],
        [
            ["15/01/2024", "1 234,56 €", "rent_collected", "Rent", "n", "01/01/2024"],
            [],
            ["2024-01-20", "-150.50", "Maintenance", "Plumber"],
        ],
    )
    assert errors == []
    rent, plumber = entries
    assert rent.row == 2
    assert rent.amount == Decimal("1234.56")
    assert rent.flow_type == "income"
    assert rent.entry_date == datetime.date(2024, 1, 15)
    assert rent.notes == "n"
    assert rent.reference_period == datetime.date(2024, 1, 1)
    assert plumber.row == 4
    assert plumber.amount == Decimal("150.50")
    assert plumber.flow_type == "expense"
    assert plumber.category == "maintenance"
    assert plumber.reference_period is None


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        (["not a date", "1", "rent_collected", "x"], "Invalid date"),
        (["2024-01-15", "", "rent_collected", "x"], "Invalid amount"),
        (["2024-01-15", "abc", "rent_collected", "x"], "Invalid amount"),
        (["2024-01-15", "0", "rent_collected", "x"], "must not be zero"),
        (["2024-01-15", "1", "nope", "x"], "Unknown category"),
        (["2024-01-15", "-1", "rent_collected", "x"], "positive amount"),
        (["2024-01-15", "1", "maintenance", "x"], "negative amount"),
    ],
)
def test_parse_entries_errors(row, reason):
    entries, errors = parse_entries(HEADER, [row])
    assert entries == []
    assert len(errors) == 1
    assert errors[0][0] == 2
    assert reason in errors[0][1]


# ── AI prompt ─────────────────────────────────────────────────────────────────


@pytest.fixture
def property_obj(db):
    return Property.objects.create(
        name="Studio Lyon",
        property_type=Property.APARTMENT,
        buying_value=Money(100_000, "EUR"),
        buying_date=datetime.date(2020, 1, 1),
    )


def test_ai_prompt_lists_columns_and_categories(property_obj):
    prompt = ai_prompt(property_obj)
    assert "Studio Lyon" in prompt
    assert "date;amount;category;description;notes" in prompt
    income, expenses = prompt.split("Expense categories")
    assert "- rent_collected: Rent collected" in income
    assert "- maintenance:" in expenses
    assert "- maintenance:" not in income
    assert "double quotes" in prompt


@pytest.mark.django_db
def test_ai_prompt_view(user_client, property_obj):
    url = reverse("property:csv_ai_prompt", kwargs={"property_pk": property_obj.pk})
    response = user_client.get(url)
    assert response.status_code == 200
    assert "rent_collected" in response.content.decode()
    assert (
        reverse("property:csv_import", kwargs={"property_pk": property_obj.pk})
        in response.content.decode()
    )


@pytest.mark.django_db
def test_import_page_links_to_the_prompt(user_client, property_obj):
    response = user_client.get(
        reverse("property:csv_import", kwargs={"property_pk": property_obj.pk})
    )
    assert (
        reverse("property:csv_ai_prompt", kwargs={"property_pk": property_obj.pk})
        in response.content.decode()
    )
