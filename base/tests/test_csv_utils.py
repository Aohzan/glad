"""Tests of the CSV reading helpers."""

import datetime
from decimal import Decimal

import pytest

from base.csv_utils import (
    decode_upload,
    detect_delimiter,
    normalize_column,
    parse_amount,
    parse_date,
    parse_datetime,
)


def test_decode_upload():
    assert decode_upload("﻿catégorie".encode()) == "catégorie"
    assert decode_upload("catégorie".encode("latin-1")) == "catégorie"


def test_detect_delimiter():
    assert detect_delimiter("a;b;c") == ";"
    assert detect_delimiter("a,b;c,d") == ","


def test_normalize_column():
    assert normalize_column(" Capital Restant Dû ") == "capital_restant_du"


@pytest.mark.parametrize(
    ("raw", "amount"),
    [
        ("1200.50", Decimal("1200.50")),
        ("1200,50", Decimal("1200.50")),
        ("1 200,50", Decimal("1200.50")),
        ("1 200,50 €", Decimal("1200.50")),
        ("1.200,50", Decimal("1200.50")),
        ("1,200.50", Decimal("1200.50")),
        ("1.234.567", Decimal(1234567)),
        ("-42", Decimal(-42)),
        ("", Decimal(0)),
    ],
)
def test_parse_amount(raw, amount):
    assert parse_amount(raw) == amount


def test_parse_amount_rejects_text():
    with pytest.raises(ValueError, match="Invalid amount"):
        parse_amount("abc")


@pytest.mark.parametrize(
    ("raw", "parsed"),
    [
        ("2024-02-01", datetime.datetime(2024, 2, 1)),
        ("2024-02-01 10:30:00", datetime.datetime(2024, 2, 1, 10, 30)),
        ("2024-02-01T10:30:00+01:00", datetime.datetime(2024, 2, 1, 10, 30)),
        ("01/02/2024", datetime.datetime(2024, 2, 1)),
        ("01/02/24", datetime.datetime(2024, 2, 1)),
        ("01.02.2024", datetime.datetime(2024, 2, 1)),
        ("15/03/2024 08:00", datetime.datetime(2024, 3, 15, 8, 0)),
        ("1 février 2024", datetime.datetime(2024, 2, 1)),
        ("02/13/2024", datetime.datetime(2024, 2, 13)),
        ("not a date", None),
        ("", None),
    ],
)
def test_parse_datetime(raw, parsed):
    assert parse_datetime(raw) == parsed


def test_parse_date():
    assert parse_date(" 01/02/2024 ") == datetime.date(2024, 2, 1)
    with pytest.raises(ValueError, match="Unrecognized"):
        parse_date("not a date")
