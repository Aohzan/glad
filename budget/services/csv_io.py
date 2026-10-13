"""CSV export and import of the budget lines, and the prompt to build such a file with an AI.

The file has one line per budget line, with the columns ``kind``,
``category`` (path such as ``Transport > Fuel``), ``label``, ``amount`` (for
the whole year), ``person`` (first name or user name, empty for the whole
household) and ``notes``. The separator (``;`` or ``,``), the encoding
(UTF-8 or Latin-1) and the French amount formats are detected on import.
"""

import csv
import io
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.utils.translation import gettext as _
from moneyed import Money

from base.csv_utils import detect_delimiter, normalize_column, parse_amount
from base.models import display_name, household_members
from budget.models import (
    LABEL_MAX_LENGTH,
    BudgetCategory,
    BudgetKind,
    BudgetLine,
    BudgetYear,
)
from budget.services.categories import CategoryNode, category_tree

COLUMNS = ("kind", "category", "label", "amount", "person", "notes")
#: Most lines read from one file.
MAX_ROWS = 2000
#: Separator of the levels of a category path.
PATH_SEPARATOR = ">"

_COLUMN_ALIASES = {
    "kind": {"kind", "type", "nature", "sens"},
    "category": {"category", "categorie", "categories"},  # codespell:ignore categorie
    "label": {"label", "libelle", "description", "intitule", "name", "nom"},
    "amount": {"amount", "montant", "annual_amount", "montant_annuel", "total"},
    "person": {"person", "personne", "membre", "member", "owner"},
    "notes": {"notes", "note", "commentaire", "comment", "comments"},
}

_KIND_ALIASES = {
    BudgetKind.INCOME: {"income", "revenu", "revenus", "recette", "recettes", "credit"},
    BudgetKind.EXPENSE: {
        "expense",
        "expenses",
        "depense",
        "depenses",
        "debit",
        "charge",
    },
    BudgetKind.SAVING: {
        "saving",
        "savings",
        "epargne",
        "investissement",
        "investment",
    },
}

_HOUSEHOLD_ALIASES = {
    "",
    "household",
    "foyer",
    "menage",
    "commun",  # codespell:ignore commun
    "common",
}


def _key(text: str) -> str:
    """*text* compared without case, accents nor extra spaces."""
    return normalize_column(" ".join(text.split()))


def _path_key(path: str) -> str:
    return PATH_SEPARATOR.join(_key(part) for part in path.split(PATH_SEPARATOR))


# ─── Export ───────────────────────────────────────────────────────────────────


def export_lines(budget_year: BudgetYear) -> str:
    """CSV of the lines of *budget_year*, re-importable as is."""
    paths = {node.category.pk: node.path for node in category_tree()}
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerow(COLUMNS)
    lines = budget_year.lines.select_related("category", "person").order_by(
        "category__kind", "category__name", "label"
    )
    for line in lines:
        writer.writerow(
            [
                line.category.kind,
                paths.get(line.category_id, line.category.name),  # ty: ignore[unresolved-attribute]
                line.label,
                f"{line.amount.amount:.2f}",
                line.person.get_username() if line.person else "",
                line.notes,
            ]
        )
    return buffer.getvalue()


# ─── Import ───────────────────────────────────────────────────────────────────


@dataclass
class ImportRow:
    """One line of an imported file, checked against the categories and members."""

    number: int
    kind: str
    path: str
    label: str
    amount: Decimal
    person_id: int | None
    person_label: str
    notes: str
    category: BudgetCategory | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True when the line can be imported."""
        return not self.errors


@dataclass
class ImportPreview:
    """Lines read from a file, with the categories to create and the errors."""

    rows: list[ImportRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    #: Category paths missing from the tree, created on import when allowed.
    missing_categories: list[str] = field(default_factory=list)

    @property
    def valid_rows(self) -> list[ImportRow]:
        """Lines without error."""
        return [row for row in self.rows if row.is_valid]

    @property
    def invalid_rows(self) -> list[ImportRow]:
        """Lines with errors."""
        return [row for row in self.rows if not row.is_valid]


def _columns(header: list[str]) -> dict[str, int]:
    found = {}
    for index, name in enumerate(header):
        normalized = normalize_column(name)
        for column, aliases in _COLUMN_ALIASES.items():
            if normalized in aliases and column not in found:
                found[column] = index
    return found


def _members() -> dict[str, tuple[int, str]]:
    names: dict[str, tuple[int, str]] = {}
    for user in household_members():
        label = display_name(user)
        for name in (user.get_username(), user.first_name, label):
            if name and _key(name) not in names:
                names[_key(name)] = (user.pk, label)
    return names


def _kind(raw: str) -> str | None:
    key = _key(raw)
    for kind, aliases in _KIND_ALIASES.items():
        if key in aliases:
            return kind
    return None


def parse_lines(text: str, *, create_missing: bool = False) -> ImportPreview:
    """Read and check the budget lines of a CSV *text*.

    Unknown categories are errors unless *create_missing*, when they are
    listed in ``missing_categories`` to be created on import (their kind
    then comes from the ``kind`` column).
    """
    preview = ImportPreview()
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        preview.errors.append(_("The file is empty."))
        return preview
    reader = csv.reader(
        io.StringIO("\n".join(lines)), delimiter=detect_delimiter(lines[0])
    )
    columns = _columns(next(reader))
    missing = [c for c in ("category", "amount") if c not in columns]
    if missing:
        preview.errors.append(
            _("Missing columns: %(columns)s") % {"columns": ", ".join(missing)}
        )
        return preview
    if len(lines) - 1 > MAX_ROWS:
        preview.errors.append(
            _("The file has more than %(count)d lines.") % {"count": MAX_ROWS}
        )
        return preview

    tree = {_path_key(node.path): node for node in category_tree()}
    members = _members()
    missing_paths: dict[str, str] = {}
    for number, values in enumerate(reader, start=2):

        def value(column: str, values=values) -> str:
            index = columns.get(column)
            return (
                values[index].strip()
                if index is not None and index < len(values)
                else ""
            )

        path = PATH_SEPARATOR.join(
            " ".join(part.split()) for part in value("category").split(PATH_SEPARATOR)
        ).replace(PATH_SEPARATOR, f" {PATH_SEPARATOR} ")
        row = ImportRow(
            number=number,
            kind="",
            path=path,
            label=value("label") or path.rsplit(PATH_SEPARATOR, 1)[-1].strip(),
            amount=Decimal(0),
            person_id=None,
            person_label=_("Household"),
            notes=value("notes"),
        )
        preview.rows.append(row)
        try:
            row.amount = abs(parse_amount(value("amount")))
        except ValueError:
            row.errors.append(
                _("Invalid amount: %(value)s") % {"value": value("amount")}
            )

        raw_kind = value("kind")
        kind = _kind(raw_kind) if raw_kind else None
        if raw_kind and kind is None:
            row.errors.append(_("Unknown kind: %(value)s") % {"value": raw_kind})

        node = tree.get(_path_key(path)) if value("category") else None
        if not value("category"):
            row.errors.append(_("The category is missing."))
        elif node is not None:
            row.category = node.category
            if kind is not None and kind != node.category.kind:
                row.errors.append(
                    _("The category %(category)s is not of kind %(kind)s.")
                    % {"category": node.path, "kind": BudgetKind(kind).label}
                )
            kind = node.category.kind
        elif not create_missing:
            row.errors.append(_("Unknown category: %(path)s") % {"path": path})
        elif kind is None:
            row.errors.append(
                _("The kind is needed to create the category %(path)s.")
                % {"path": path}
            )
        elif path.count(PATH_SEPARATOR) >= BudgetCategory.MAX_DEPTH:
            row.errors.append(
                _("Categories are limited to %(depth)d levels.")
                % {"depth": BudgetCategory.MAX_DEPTH}
            )
        elif (ancestor := _deepest_ancestor(path, tree)) is not None and (
            ancestor.category.kind != kind
        ):
            row.errors.append(
                _("The category %(category)s is not of kind %(kind)s.")
                % {"category": ancestor.path, "kind": BudgetKind(kind).label}
            )
        else:
            keys = _path_key(path).split(PATH_SEPARATOR)
            prefixes = [PATH_SEPARATOR.join(keys[:n]) for n in range(1, len(keys) + 1)]
            if any(missing_paths.get(p, kind) != kind for p in prefixes):
                row.errors.append(
                    _("The category %(path)s is used with several kinds.")
                    % {"path": path}
                )
            else:
                if prefixes[-1] not in missing_paths:
                    preview.missing_categories.append(path)
                missing_paths.update(dict.fromkeys(prefixes, kind))
        row.kind = kind or ""

        person = value("person")
        if _key(person) not in _HOUSEHOLD_ALIASES:
            match = members.get(_key(person))
            if match is None:
                row.errors.append(_("Unknown person: %(value)s") % {"value": person})
            else:
                row.person_id, row.person_label = match
        if len(row.label) > LABEL_MAX_LENGTH:
            row.errors.append(_("The label is too long."))
    if not preview.rows:
        preview.errors.append(_("The file has no line."))
    return preview


def _deepest_ancestor(path: str, tree: dict[str, CategoryNode]) -> CategoryNode | None:
    """Deepest existing category among the parents of *path*."""
    keys = [_key(part) for part in path.split(PATH_SEPARATOR)][:-1]
    while keys:
        node = tree.get(PATH_SEPARATOR.join(keys))
        if node is not None:
            return node
        keys.pop()
    return None


def _category_for(
    path: str, kind: str, known: dict[str, BudgetCategory]
) -> BudgetCategory:
    """Category of *path*, created with its missing parents.

    *known* maps the path keys (see :func:`_path_key`) of the existing
    categories to them, and receives the created ones.
    """
    parent = None
    keys: list[str] = []
    for part in (p.strip() for p in path.split(PATH_SEPARATOR)):
        keys.append(_key(part))
        prefix = PATH_SEPARATOR.join(keys)
        if prefix not in known:
            known[prefix] = BudgetCategory.objects.create(
                parent=parent, name=part, kind=kind, position=99
            )
        parent = known[prefix]
    assert parent is not None
    return parent


@transaction.atomic
def import_lines(budget_year: BudgetYear, preview: ImportPreview, currency: str) -> int:
    """Add the valid lines of *preview* to *budget_year*; returns their number."""
    known = {_path_key(node.path): node.category for node in category_tree()}
    lines = []
    for row in preview.valid_rows:
        category = row.category or _category_for(row.path, row.kind, known)
        lines.append(
            BudgetLine(
                budget_year=budget_year,
                category=category,
                label=row.label,
                amount=Money(row.amount, currency),
                person_id=row.person_id,
                notes=row.notes,
            )
        )
    BudgetLine.objects.bulk_create(lines)
    return len(lines)


# ─── AI prompt ────────────────────────────────────────────────────────────────


def ai_prompt(budget_year: BudgetYear) -> str:
    """Instructions for an AI turning a bank export into an importable CSV file."""
    tree = category_tree()
    names = [display_name(user) for user in household_members()]
    sections = []
    for kind, label in BudgetKind.choices:
        paths = [f"- {node.path}" for node in tree if node.category.kind == kind]
        if paths:
            sections.append(f"{kind} ({label}):\n" + "\n".join(paths))
    return "\n".join(
        [
            _(
                "I am preparing the budget of my household for %(year)d. Attached is "
                "the export of the transactions of my bank account(s). Group these "
                "transactions into yearly budget lines and answer only with a CSV "
                "file, using ; as separator, with these columns:"
            )
            % {"year": budget_year.year},
            "",
            ";".join(COLUMNS),
            "",
            _("- kind: income, expense or saving"),
            _(
                "- category: one of the categories below, written exactly as listed "
                "(levels separated by >)"
            ),
            _(
                "- label: short description, such as the merchant or the kind of expense"
            ),
            _(
                "- amount: total for the whole year, positive, with a dot as decimal separator"
            ),
            _("- person: one of %(names)s, or empty for the whole household")
            % {"names": ", ".join(names)},
            _("- notes: optional"),
            "",
            _("Rules:"),
            _(
                "- Add up the transactions of a same category and label over the year, "
                "with at most one line per category, label and person."
            ),
            _(
                "- Leave out the transfers between my own accounts and the flows "
                "already tracked elsewhere: the installments of my property loans, "
                "the rents and charges of my properties, the deposits on my saving "
                "and investment accounts."
            ),
            _(
                "- If the export covers less than 12 months, extrapolate the amounts "
                "to a full year and say so in the notes column."
            ),
            "",
            _("Categories:"),
            "\n\n".join(sections),
        ]
    )
