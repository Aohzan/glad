"""
LMNP réel tax service.

Provides the mapping from TaxCategory values to cerfa 2033-B line numbers,
and aggregation helpers for annual tax preparation.

Architecture note: This module is intentionally isolated from the models.
To support a different tax regime (micro-BIC, SCI IS, etc.), add a new
mapping dict (e.g. MICRO_BIC_MAPPING) and a corresponding get_*_summary()
function — no model changes required.
"""

import csv
import io
from decimal import Decimal

from django.db.models import Sum

# ─── Mapping TaxCategory → cerfa 2033-B (LMNP réel) ─────────────────────────
#
# Each entry: {"section": "recettes"|"charges"|None, "line": str|None, "label": str}
# section=None means the category is off the tax result (deposits, capital repayment).

LMNP_TAX_MAPPING: dict[str, dict] = {
    # Recettes
    "rent": {
        "section": "recettes",
        "line": "213",
        "label": "Loyers meublés",
    },
    "charges_recovered": {
        "section": "recettes",
        "line": "213",
        "label": "Charges refacturées",
    },
    "other_income": {
        "section": "recettes",
        "line": "209",
        "label": "Autres produits",
    },
    # Charges déductibles
    "management_fees": {
        "section": "charges",
        "line": "218",
        "label": "Frais de gestion",
    },
    "other_general_fees": {
        "section": "charges",
        "line": "220",
        "label": "Autres frais généraux",
    },
    "maintenance_repairs": {
        "section": "charges",
        "line": "222",
        "label": "Entretien et réparations",
    },
    "insurance": {
        "section": "charges",
        "line": "224",
        "label": "Primes d'assurance",
    },
    "taxes": {
        "section": "charges",
        "line": "226",
        "label": "Impôts et taxes (foncière, CFE)",
    },
    "misc_deductible": {
        "section": "charges",
        "line": "228",
        "label": "Charges diverses déductibles",
    },
    "loan_interest": {
        "section": "charges",
        "line": "230",
        "label": "Charges financières (intérêts)",
    },
    # Hors résultat fiscal
    "loan_repayment": {
        "section": None,
        "line": None,
        "label": "Capital remboursé (non déductible)",
    },
    "deposit_in": {
        "section": None,
        "line": None,
        "label": "Dépôt de garantie encaissé",  # codespell:ignore garantie
    },
    "deposit_out": {
        "section": None,
        "line": None,
        "label": "Dépôt de garantie restitué",  # codespell:ignore garantie
    },
    "non_deductible": {
        "section": None,
        "line": None,
        "label": "Charge non déductible",
    },
}


def get_lmnp_summary(property_id: int, year: int) -> dict:
    """
    Return an annual LMNP réel summary for a property.

    Returns a dict with:
      - recettes: total income (loyers + charges refacturées + other)
      - charges: total deductible expenses (per cerfa line)
      - result: recettes - charges (before amortissements)
      - by_category: breakdown by tax_category
      - by_line: breakdown by cerfa line number
    """
    from property.models import PropertyLedgerEntry  # avoid circular at module level

    entries = PropertyLedgerEntry.objects.filter(
        property_id=property_id,
        entry_date__year=year,
        amount_currency="EUR",
    )

    by_category: dict[str, Decimal] = {}
    for row in entries.values("tax_category").annotate(total=Sum("amount")):
        by_category[row["tax_category"]] = row["total"] or Decimal("0")

    recettes = Decimal("0")
    charges = Decimal("0")
    by_line: dict[str, Decimal] = {}

    for cat, total in by_category.items():
        mapping = LMNP_TAX_MAPPING.get(cat)
        if not mapping:
            continue
        section = mapping["section"]
        line = mapping["line"]
        if section == "recettes":
            recettes += total
        elif section == "charges":
            charges += total
        if line:
            by_line[line] = by_line.get(line, Decimal("0")) + total

    return {
        "year": year,
        "recettes": recettes,
        "charges": charges,
        "result": recettes - charges,
        "by_category": by_category,
        "by_line": by_line,
    }


def export_lmnp_csv(property_id: int, year: int) -> str:
    """
    Generate a CSV string for LMNP réel annual declaration.

    Columns: property_name, entry_date, flow_type, tax_category,
             lmnp_line, lmnp_label, description, amount_eur
    """
    from property.models import PropertyLedgerEntry

    entries = (
        PropertyLedgerEntry.objects.filter(
            property_id=property_id,
            entry_date__year=year,
        )
        .select_related("property")
        .order_by("entry_date")
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "property",
            "entry_date",
            "flow_type",
            "tax_category",
            "lmnp_line",
            "lmnp_label",
            "description",
            "amount",
            "currency",
        ]
    )
    for entry in entries:
        mapping = LMNP_TAX_MAPPING.get(entry.tax_category, {})
        writer.writerow(
            [
                entry.property.name,
                entry.entry_date.isoformat(),
                entry.flow_type,
                entry.tax_category,
                mapping.get("line", ""),
                mapping.get("label", ""),
                entry.description,
                entry.amount.amount,
                entry.amount.currency,
            ]
        )
    return output.getvalue()
