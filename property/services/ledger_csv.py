"""Reading the CSV files imported into the ledger of a property.

The file comes from a spreadsheet, a bank or an accounting tool: the columns
may be named in French or in English, separated by ``;`` or ``,``, encoded in
UTF-8 or Latin-1, and the category given by its code or its label.
"""

import csv
import datetime
import io
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext as _

from base.csv_utils import (
    decode_upload,
    detect_delimiter,
    normalize_column,
    parse_amount,
    parse_datetime,
)
from property.models import PropertyLedgerEntry

#: Columns of the import, in the order of the prompt.
COLUMNS = ("date", "amount", "category", "description", "notes", "reference_period")
REQUIRED_COLUMNS = ("date", "amount", "category", "description")

#: Accepted column names (as normalized by ``normalize_column``) per column.
COLUMN_ALIASES = {
    "date": (
        "date",
        "date_operation",
        "date_d'operation",
        "date_de_l'operation",
        "jour",
    ),
    "amount": (
        "amount",
        "montant",
        "montant_eur",
        "montant_(eur)",
        "somme",  # codespell:ignore somme
        "value",
    ),
    "category": (
        "category",
        "categorie",  # codespell:ignore categorie
        "management_category",
    ),
    "description": (
        "description",
        "libelle",
        "label",
        "intitule",
        "objet",  # codespell:ignore objet
    ),
    "notes": ("notes", "note", "commentaire", "commentaires", "comment", "comments"),
    "reference_period": (
        "reference_period",
        "periode",  # codespell:ignore periode
        "periode_de_reference",
        "period",
    ),
}
_COLUMN_BY_ALIAS: dict[str, str] = {
    alias: column for column, aliases in COLUMN_ALIASES.items() for alias in aliases
}


class LedgerCSVError(ValueError):
    """The file cannot be imported; the message is shown to the user."""


@dataclass
class ParsedEntry:
    """A row of the file ready to become a ledger entry."""

    row: int
    flow_type: str
    category: str
    amount: Decimal
    entry_date: datetime.date
    description: str
    notes: str
    reference_period: datetime.date | None


def _key(text: str) -> str:
    """*text* lowercased, without accents and with single spaces."""
    stripped = "".join(
        c
        for c in unicodedata.normalize("NFD", text.strip().lower())
        if unicodedata.category(c) != "Mn"
    )
    return " ".join(stripped.split())


def read_rows(data: bytes) -> tuple[list[str], list[list[str]]]:
    """Header (canonical column names) and data rows of an uploaded file.

    Raises LedgerCSVError when the file is empty, lacks a required column or
    has no data row.
    """
    lines = decode_upload(data).splitlines(keepends=True)
    # Spreadsheets may write blank or whitespace-only lines before the header.
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        raise LedgerCSVError(_("The CSV file is empty."))
    text, first_line = "".join(lines), lines[0]
    reader = csv.reader(io.StringIO(text), delimiter=detect_delimiter(first_line))
    header = []
    for name in next(reader):
        column = _COLUMN_BY_ALIAS.get(normalize_column(name), name.strip())
        # A second column with the same meaning is ignored.
        header.append(column if column not in header else "")
    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing:
        raise LedgerCSVError(
            _("CSV file is missing required columns: %(cols)s")
            % {"cols": ", ".join(missing)}
        )
    rows = list(reader)
    if not any(any(cell.strip() for cell in row) for row in rows):
        raise LedgerCSVError(_("The CSV file contains no data rows."))
    return header, rows


def _category_keys() -> dict[str, str]:
    """Category code by the key of its code and of its label in every language.

    The current language comes first, then the other languages of the site:
    an export written in French is read the same whatever the language of the
    user.
    """
    current = translation.get_language() or settings.LANGUAGE_CODE
    languages = [current] + [
        code for code, _name in settings.LANGUAGES if code != current
    ]
    keys: dict[str, str] = {}
    for category in PropertyLedgerEntry.ManagementCategory:
        keys[_key(category.value)] = category.value
        for language in languages:
            with translation.override(language):
                keys.setdefault(_key(category.label), category.value)
    return keys


def resolve_category(raw: str, keys: dict[str, str] | None = None) -> str | None:
    """Category code of *raw*, given by its code or its label, None when unknown."""
    return (keys if keys is not None else _category_keys()).get(_key(raw))


def resolve_categories(header: list[str], rows: list[list[str]]) -> list[list[str]]:
    """*rows* with each category label replaced by its code (unknown ones kept).

    Done at upload, in the language of the user, so that the confirmation step
    only has codes to check.
    """
    index = header.index("category")
    keys = _category_keys()
    resolved = []
    for row in rows:
        row = list(row)
        if index < len(row):
            row[index] = resolve_category(row[index], keys) or row[index]
        resolved.append(row)
    return resolved


def parse_entries(
    header: list[str], rows: list[list[str]]
) -> tuple[list[ParsedEntry], list[tuple[int, str]]]:
    """Entries of the valid rows, and (row number, reason) for the others.

    The first data row is row 2 (row 1 is the header); blank rows are skipped.
    The sign of the amount gives the flow type, and must match the category.
    """
    keys = _category_keys()
    income_categories = {c.value for c in PropertyLedgerEntry._INCOME_CATEGORIES}

    def cell(row: list[str], column: str) -> str:
        if column not in header:
            return ""
        index = header.index(column)
        return row[index].strip() if index < len(row) else ""

    entries: list[ParsedEntry] = []
    errors: list[tuple[int, str]] = []
    for number, row in enumerate(rows, start=2):
        if not any(c.strip() for c in row):
            continue
        raw_date = cell(row, "date")
        parsed_date = parse_datetime(raw_date)
        if not parsed_date:
            errors.append((number, _("Invalid date: %(val)s") % {"val": raw_date}))
            continue
        raw_amount = cell(row, "amount")
        try:
            if not raw_amount:
                raise ValueError(raw_amount)
            amount = parse_amount(raw_amount)
        except ValueError:
            errors.append((number, _("Invalid amount: %(val)s") % {"val": raw_amount}))
            continue
        if amount == 0:
            errors.append((number, _("Amount must not be zero.")))
            continue
        raw_category = cell(row, "category")
        category = resolve_category(raw_category, keys)
        if category is None:
            errors.append(
                (number, _("Unknown category: %(val)s") % {"val": raw_category})
            )
            continue
        if category in income_categories and amount < 0:
            errors.append(
                (
                    number,
                    _("Category %(cat)s requires a positive amount.")
                    % {"cat": category},
                )
            )
            continue
        if category not in income_categories and amount > 0:
            errors.append(
                (
                    number,
                    _("Category %(cat)s requires a negative amount.")
                    % {"cat": category},
                )
            )
            continue
        reference = parse_datetime(cell(row, "reference_period"))
        entries.append(
            ParsedEntry(
                row=number,
                flow_type=(
                    PropertyLedgerEntry.FlowType.INCOME
                    if amount > 0
                    else PropertyLedgerEntry.FlowType.EXPENSE
                ),
                category=category,
                amount=abs(amount),
                entry_date=parsed_date.date(),
                description=cell(row, "description"),
                notes=cell(row, "notes"),
                reference_period=reference.date() if reference else None,
            )
        )
    return entries, errors


def ai_prompt(property_obj) -> str:
    """Instructions for an AI turning an export of transactions into an importable file."""
    income = PropertyLedgerEntry._INCOME_CATEGORIES
    categories = list(PropertyLedgerEntry.ManagementCategory)
    return "\n".join(
        [
            _(
                'I keep the accounts of my rental property "%(name)s". Attached is an '
                "export of its transactions (from an accounting tool such as Matera, "
                "a bank statement or a spreadsheet). Convert it and answer only with a "
                "CSV file, using ; as separator, with these columns:"
            )
            % {"name": property_obj.name},
            "",
            ";".join(COLUMNS[:5]),
            "",
            _("- date: date of the transaction, as YYYY-MM-DD"),
            _(
                "- amount: positive for an income, negative for an expense, with a dot "
                "as decimal separator and without currency symbol"
            ),
            _("- category: one of the codes below, written exactly as listed"),
            _("- description: short description of the transaction"),
            _(
                "- notes: optional, for example the account or the category of the export"
            ),
            "",
            _("Rules:"),
            _("- One line per transaction: do not group nor add up the transactions."),
            _(
                "- Wrap in double quotes any value that contains a ; or a line "
                "break, so that the columns stay aligned."
            ),
            _(
                "- Leave out the transfers between my own accounts and the transactions "
                "of other properties."
            ),
            _(
                "- An expense refunded to me (by the tenant, the insurance...) is "
                "other_income, with a positive amount."
            ),
            _(
                "- When no category fits, use misc_deductible for an expense or "
                "other_income for an income, and say why in the notes column."
            ),
            "",
            _("Income categories (positive amount):"),
            *[f"- {c.value}: {c.label}" for c in categories if c in income],
            "",
            _("Expense categories (negative amount):"),
            *[f"- {c.value}: {c.label}" for c in categories if c not in income],
        ]
    )
