"""Helpers reading the CSV files exported by banks and spreadsheets (French formats)."""

import datetime
import unicodedata
from decimal import Decimal, InvalidOperation

import dateparser

#: Day-first date forms of the French bank and spreadsheet exports.
_DAY_FIRST_FORMATS = (
    "%d/%m/%Y",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%y",
    "%d-%m-%Y",
    "%d.%m.%Y",
)

#: First characters of a cell a spreadsheet reads as a formula.
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")

#: Characters removed from an amount: spaces used as thousands separator and
#: currency symbols.
_AMOUNT_NOISE = (" ", "\xa0", "\u202f", "€", "EUR")


def decode_upload(data: bytes) -> str:
    """Text of an uploaded file, in UTF-8 (with or without BOM) or Latin-1."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def detect_delimiter(header: str) -> str:
    """``;`` or ``,``, whichever splits the header line the most."""
    return ";" if header.count(";") >= header.count(",") else ","


def normalize_column(name: str) -> str:
    """Lowercase column name without accents, spaces turned into underscores."""
    s = name.strip().lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    ).replace(" ", "_")


def parse_amount(raw: str) -> Decimal:
    """Amount written the French or the English way, 0 when empty.

    ``1 200,50``, ``1.200,50``, ``1,200.50`` and ``1200.50`` all read 1200.50:
    when both separators appear, the last one is the decimal separator; a
    separator repeated several times groups the thousands.
    """
    cleaned = raw.strip()
    for noise in _AMOUNT_NOISE:
        cleaned = cleaned.replace(noise, "")
    if cleaned == "":
        return Decimal(0)
    if "," in cleaned and "." in cleaned:
        thousands = "." if cleaned.rfind(",") > cleaned.rfind(".") else ","
        cleaned = cleaned.replace(thousands, "")
    for separator in (",", "."):
        if cleaned.count(separator) > 1:
            cleaned = cleaned.replace(separator, "")
    try:
        amount = Decimal(cleaned.replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"Invalid amount: {raw!r}") from None
    if not amount.is_finite():
        raise ValueError(f"Invalid amount: {raw!r}")
    return amount


def spreadsheet_safe(text: str) -> str:
    """*text* prefixed with ``'`` when a spreadsheet would read it as a formula.

    Cells starting with ``=``, ``+``, ``-``, ``@``, a tab or a carriage return
    run as formulas once the file is opened in Excel or LibreOffice (CSV
    injection); the quote makes them plain text.
    """
    return f"'{text}" if text.startswith(_FORMULA_STARTS) else text


def strip_spreadsheet_guard(text: str) -> str:
    """*text* without the ``'`` :func:`spreadsheet_safe` adds."""
    if text.startswith("'") and text[1:].startswith(_FORMULA_STARTS):
        return text[1:]
    return text


def parse_datetime(raw: str) -> datetime.datetime | None:
    """Date and time of a CSV cell, read day first when ambiguous; None when unreadable.

    ISO dates (``2024-02-01``, ``2024-02-01 10:30:00``) come first, then the
    French day-first forms (``01/02/2024`` is the 1st of February), then any
    wording ``dateparser`` understands (``1 février 2024``), and last the
    month-first form for what cannot be day first (``02/13/2024``). The time
    zone, if any, is dropped: the application stores naive dates.
    """
    raw = raw.strip()
    if not raw:
        return None
    parsed = (
        _strptime(raw)
        or dateparser.parse(raw, settings={"DATE_ORDER": "DMY"})
        or dateparser.parse(raw)
    )
    return parsed.replace(tzinfo=None) if parsed is not None else None


def _strptime(raw: str) -> datetime.datetime | None:
    """*raw* read as an ISO date or a day-first date, None otherwise."""
    try:
        return datetime.datetime.fromisoformat(raw)
    except ValueError:
        pass
    for fmt in _DAY_FIRST_FORMATS:
        try:
            return datetime.datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def parse_date(raw: str) -> datetime.date:
    """Date of a CSV cell (see :func:`parse_datetime`); ValueError when unreadable."""
    parsed = parse_datetime(raw)
    if parsed is None:
        raise ValueError(f"Unrecognized date format: {raw!r}")
    return parsed.date()
