"""Tests of the CSV reading helpers."""

import codecs
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
    spreadsheet_safe,
    strip_spreadsheet_guard,
)


def test_decode_upload():
    assert decode_upload("﻿catégorie".encode()) == "catégorie"
    assert decode_upload("catégorie".encode("latin-1")) == "catégorie"
    # Windows exports: the euro sign of Windows-1252, UTF-16 with its BOM.
    assert decode_upload("1 234,56 €".encode("cp1252")) == "1 234,56 €"
    assert decode_upload("catégorie;€".encode("utf-16")) == "catégorie;€"
    assert decode_upload(codecs.BOM_UTF16_BE + "é".encode("utf-16-be")) == "é"
    # A byte Windows-1252 leaves undefined falls back to Latin-1.
    assert decode_upload(b"a\x81") == "a\x81"


def test_detect_delimiter():
    assert detect_delimiter("a;b;c") == ";"
    assert detect_delimiter("a,b;c,d") == ","
    assert detect_delimiter("date\tmontant\tlibellé") == "\t"
    assert detect_delimiter("a;b,c") == ";"
    assert detect_delimiter("single") == ";"


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


@pytest.mark.parametrize("raw", ["abc", "NaN", "-Infinity"])
def test_parse_amount_rejects_text(raw):
    with pytest.raises(ValueError, match="Invalid amount"):
        parse_amount(raw)


@pytest.mark.parametrize(
    ("text", "safe"),
    [
        ("=SUM(A1:A9)", "'=SUM(A1:A9)"),
        ("+33 6", "'+33 6"),
        ("-1", "'-1"),
        ("@cmd", "'@cmd"),
        ("Rent", "Rent"),
        ("'quoted", "'quoted"),
        ("", ""),
    ],
)
def test_spreadsheet_guard_round_trip(text, safe):
    assert spreadsheet_safe(text) == safe
    assert strip_spreadsheet_guard(safe) == text


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
