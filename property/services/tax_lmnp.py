"""
LMNP réel tax service.

Provides the mapping from ManagementCategory values to cerfa 2033-B line numbers,
and aggregation helpers for annual tax preparation.

Architecture note: This module is intentionally isolated from the models.
To support a different tax regime (micro-BIC, SCI IS, etc.), add a new
mapping dict (e.g. MICRO_BIC_MAPPING) and a corresponding get_*_summary()
function — no model changes required.

Art. 39C (CGI): Amortization cannot create or increase an operating deficit.
Any unused amortization in a given year is deferred to subsequent years
when the operating result allows it.

LMNP fiscal deficits (from charges > recettes) are reportable against future
LMNP profits for up to 10 years (art. 156 I-1° bis CGI).

Depuis la loi de finances 2025 : les amortissements déduits sont réintégrés dans
le calcul de la plus-value lors de la revente du bien (art. 150 VB bis du CGI).

2033-B cerfa line reference:
  218 = Production vendue (services) — loyers et charges refacturées
  209 = Autres produits d'exploitation
  242 = Autres charges externes — gestion, charges, travaux, assurance, etc.
  243 = dont TP/CFE/CVAE (sous-ligne de 244)
  244 = Impôts, taxes et versements assimilés — taxe foncière, CFE
  254 = Dotations aux amortissements
  270 = Résultat d'exploitation (1)
  294 = Charges financières — intérêts et assurance emprunteur
  310 = Bénéfices ou pertes (résultat comptable)
  318 = Réintégrations : amortissements reportés art. 39C
  352 = Résultat fiscal avant imputation des déficits antérieurs
  360 = Déficits antérieurs reportables imputés
  370 = Résultat fiscal après imputation des déficits antérieurs
"""

import datetime
from decimal import Decimal

from django.db.models import Q, Sum

# ─── Mapping ManagementCategory → cerfa 2033-B (LMNP réel) ──────────────────
#
# Each entry: {"section": "recettes"|"charges"|None, "line": str|None, "label": str}
# section=None means the category is off the tax result (deposits, capital repayment).
#
# Charges financières (loan_interest, loan_insurance) map to line 294 and are
# excluded from the exploitation result (270) but included in the overall result (310).
_CHARGES_FINANCIERES = {"loan_interest", "loan_insurance"}

LMNP_TAX_MAPPING: dict[str, dict] = {
    # Recettes (line 218: Production vendue – services)
    "rent_collected": {
        "section": "recettes",
        "line": "218",
        "label": "Loyers meublés",
    },
    "charges_collected": {
        "section": "recettes",
        "line": "218",
        "label": "Charges refacturées",
    },
    "other_income": {
        "section": "recettes",
        "line": "209",
        "label": "Autres produits",
    },
    "manager_reversal": {
        "section": "recettes",
        "line": "218",
        "label": "Reversement gestionnaire",
    },
    # Charges d'exploitation (line 242: Autres charges externes)
    "management_fees": {
        "section": "charges",
        "line": "242",
        "label": "Frais de gestion",
    },
    "other_general_fees": {
        "section": "charges",
        "line": "242",
        "label": "Autres frais généraux",
    },
    "coownership": {
        "section": "charges",
        "line": "242",
        "label": "Charges de copropriété",
    },
    "maintenance": {
        "section": "charges",
        "line": "242",
        "label": "Entretien et réparations",
    },
    "works": {
        "section": "charges",
        "line": "242",
        "label": "Travaux",
    },
    "insurance": {
        "section": "charges",
        "line": "242",
        "label": "Primes d'assurance",
    },
    "misc_deductible": {
        "section": "charges",
        "line": "242",
        "label": "Charges diverses déductibles",
    },
    # Impôts et taxes (line 244; CFE also tracked separately on line 243)
    "property_tax": {
        "section": "charges",
        "line": "244",
        "label": "Taxe foncière",
    },
    "cfe": {
        "section": "charges",
        "line": "244",
        "label": "CFE",
    },
    # Charges financières (line 294)
    "loan_interest": {
        "section": "charges",
        "line": "294",
        "label": "Charges financières (intérêts)",
    },
    "loan_insurance": {
        "section": "charges",
        "line": "294",
        "label": "Assurance emprunteur",
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
      - charges: total deductible expenses (per cerfa line, incl. financial charges)
      - charges_exploitation: deductible charges excluding financial charges
      - charges_financieres: financial charges only (loan interest + insurance)
      - result: recettes - charges (before amortissements)
      - amortization_total: total dotation for the year
      - deferred_prior: deferred amortization balance carried from prior years
      - amortization_deductible: amortization actually deducted (art. 39C capped)
      - amortization_deferred: new deferral created this year (art. 39C)
      - deferred_balance: total deferred amortization balance at end of year
      - taxable_result: fiscal result before deficit carryforward imputation.
            Can be negative (LMNP fiscal deficit); amortization only deferred,
            not creating extra deficit per art. 39C CGI.
      - by_category: breakdown by management_category
      - by_line: breakdown by cerfa line number (includes amortization on line 254)
      Cerfa 2033-B computed lines:
      - cerfa_310: résultat comptable = recettes - charges - amort_total
      - cerfa_318: réintégration art. 39C = amort_total - amort_deductible
    """
    raw = _get_lmnp_summary_raw(property_id, year)
    recettes = raw["recettes"]
    charges = raw["charges"]
    charges_exploitation = raw["charges_exploitation"]
    charges_financieres = raw["charges_financieres"]
    result_before_amort = recettes - charges

    # Re-compute by_category and by_line for external consumers
    by_category = _get_category_totals_for_year(property_id, year)

    by_line: dict[str, Decimal] = {}
    for cat, total in by_category.items():
        mapping = LMNP_TAX_MAPPING.get(cat)
        if not mapping:
            continue
        line = mapping["line"]
        if line:
            by_line[line] = by_line.get(line, Decimal("0")) + total

    # Line 243: CFE sub-total (subset of line 244)
    cfe_total = by_category.get("cfe", Decimal("0"))
    if cfe_total > Decimal("0"):
        by_line["243"] = cfe_total

    # Art. 39C: compute deferred balance from prior years
    deferred_prior = get_deferred_amortization_balance(property_id, year - 1)
    amortization_total = get_total_amortization(property_id, year)
    available_amort = amortization_total + deferred_prior

    if result_before_amort <= Decimal("0"):
        # Operating deficit: art. 39C — amortization cannot worsen the deficit
        amortization_deductible = Decimal("0")
        amortization_deferred = (
            amortization_total  # current year dotation fully deferred
        )
        deferred_balance = deferred_prior + amortization_total
        # taxable_result = actual deficit (NOT zero — art. 39C only prevents amort
        # from creating/deepening a deficit, but charges can still cause one)
        taxable_result = result_before_amort
    else:
        amortization_deductible = min(available_amort, result_before_amort)
        amortization_deferred = available_amort - amortization_deductible
        deferred_balance = amortization_deferred
        taxable_result = result_before_amort - amortization_deductible

    # Cerfa 2033-B line 254: dotation déduite
    if amortization_deductible > Decimal("0"):
        by_line["254"] = amortization_deductible

    # Cerfa 2033-B computed lines
    cerfa_310 = result_before_amort - amortization_total  # résultat comptable
    cerfa_318 = amortization_total - amortization_deductible  # réintégration art. 39C

    return {
        "year": year,
        "recettes": recettes,
        "charges": charges,
        "charges_exploitation": charges_exploitation,
        "charges_financieres": charges_financieres,
        "result": result_before_amort,
        "amortization_total": amortization_total,
        "deferred_prior": deferred_prior,
        "amortization_deductible": amortization_deductible,
        "amortization_deferred": amortization_deferred,
        "deferred_balance": deferred_balance,
        "taxable_result": taxable_result,
        "by_category": by_category,
        "by_line": by_line,
        "cerfa_310": cerfa_310,
        "cerfa_318": cerfa_318,
    }


# ─── Fiscal deficit carryforward helpers ──────────────────────────────────────


def get_fiscal_deficit_history(property_id: int, year: int) -> dict[int, Decimal]:
    """
    Return remaining LMNP fiscal deficit by origin year at end of ``year``.

    LMNP fiscal deficits (result_before_amort - amort_deductible < 0) are
    reportable against future LMNP profits for up to 10 years (art. 156 CGI).
    Profits reduce the oldest outstanding deficits first.

    Returns:
        dict mapping origin_year → remaining_deficit_amount (> 0).
    """
    from property.models import AmortizationAsset, Property

    # Determine start year from first asset or property buying_date
    qs = AmortizationAsset.objects.filter(property_id=property_id).order_by(
        "beginning_date"
    )
    if qs.exists():
        first_year = qs.first().beginning_date.year  # ty: ignore[unresolved-attribute]
    else:
        try:
            prop = Property.objects.get(pk=property_id)
            first_year = prop.buying_date.year if prop.buying_date else year
        except Property.DoesNotExist:
            return {}

    if year < first_year:
        return {}

    deficits: dict[int, Decimal] = {}

    for y in range(first_year, year + 1):
        # Remove expired deficits (older than 10 years: oy < y - 10 means expired)
        # A deficit from year oy is reportable in years oy+1 to oy+10 inclusive.
        cutoff = y - 10
        deficits = {oy: d for oy, d in deficits.items() if oy >= cutoff}

        # Get fiscal result before deficit imputation (after art. 39C amort deferral)
        summary = get_lmnp_summary(property_id, y)
        fiscal_result = summary["taxable_result"]

        if fiscal_result < Decimal("0"):
            deficits[y] = abs(fiscal_result)
        elif fiscal_result > Decimal("0"):
            # Apply oldest deficits first
            profit_remaining = fiscal_result
            for deficit_year in sorted(deficits.keys()):
                if profit_remaining <= Decimal("0"):
                    break
                use = min(deficits[deficit_year], profit_remaining)
                deficits[deficit_year] -= use
                profit_remaining -= use
            deficits = {oy: d for oy, d in deficits.items() if d > Decimal("0")}

    return deficits


def get_fiscal_deficit_carryforward(property_id: int, year: int) -> Decimal:
    """Return the total cumulative LMNP fiscal deficit carryforward at end of ``year``."""
    return sum(get_fiscal_deficit_history(property_id, year).values(), Decimal("0"))


# ─── Amortization helpers ────────────────────────────────────────────────────


def get_amortization_table(property_id: int, year: int) -> list[dict]:
    """
    Return the amortization table for all AmortizationAsset items of a property
    for a given fiscal year.

    Each dict contains:
      - label: str
      - depreciable_base: Decimal
      - value_total: Decimal
      - duration_years: int
      - annual_dotation: Decimal
      - cumulative: Decimal  (from acquisition up to and including `year`)
      - property_name: str
      - asset_pk: int
      - is_initial: bool
      - global_pct: Decimal | None  (value_total / setup.total_value * 100)
    """
    from property.models import AmortizationAsset, AmortizationSetup

    assets = (
        AmortizationAsset.objects.filter(property_id=property_id)
        .select_related("property")
        .prefetch_related("source_transactions")
        .order_by("-is_initial_component", "beginning_date")
    )

    try:
        setup = AmortizationSetup.objects.get(property_id=property_id)
        setup_total = setup.total_value.amount if setup.total_value.amount else None
    except AmortizationSetup.DoesNotExist:
        setup_total = None

    table = []
    for asset in assets:
        base = asset.depreciable_base()
        dotation = asset.get_annual_amortization(year)
        cumul = asset.cumulative_amortization(year)
        global_pct = None
        if setup_total and setup_total > Decimal("0"):
            global_pct = (
                asset.value_total.amount / setup_total * Decimal("100")
            ).quantize(Decimal("0.1"))
        end_year = (
            asset.beginning_date.year + asset.duration_years
            if asset.beginning_date and asset.duration_years
            else None
        )
        pct_amortized = (
            (cumul / base.amount * Decimal("100")).quantize(Decimal("0.1"))
            if base.amount > Decimal("0")
            else Decimal("0")
        )
        is_complete = end_year is not None and year >= end_year
        table.append(
            {
                "label": asset.label,
                "depreciable_base": base.amount,
                "value_total": asset.value_total.amount,
                "duration_years": asset.duration_years,
                "beginning_date": asset.beginning_date,
                "end_year": end_year,
                "pct_amortized": pct_amortized,
                "is_complete": is_complete,
                "annual_dotation": dotation,
                "cumulative": cumul,
                "property_name": asset.property.name,
                "asset_pk": asset.pk,
                "is_initial": asset.is_initial_component,
                "global_pct": global_pct,
                "source_transactions": list(asset.source_transactions.all()),
            }
        )
    return table


def get_amortization_schedule(property_id: int) -> dict:
    """
    Return the full year-by-year amortization evolution for a property.

    Covers from the earliest asset acquisition year to the last asset end year.

    Returns a dict with:
      - rows: list of {year, annual_dotation (float), cumulative (float), pct_complete (float)}
      - total_depreciable_base: Decimal
      - amortized_to_date: Decimal  (cumulative up to current year)
      - remaining: Decimal
      - end_year: int | None  (last year any dotation > 0)
    """
    from property.models import AmortizationAsset

    today_year = datetime.date.today().year
    assets = list(AmortizationAsset.objects.filter(property_id=property_id))

    if not assets:
        return {
            "rows": [],
            "asset_series": [],
            "total_depreciable_base": Decimal("0"),
            "amortized_to_date": Decimal("0"),
            "remaining": Decimal("0"),
            "end_year": None,
        }

    first_year = min(a.beginning_date.year for a in assets)
    last_year = max(a.beginning_date.year + a.duration_years - 1 for a in assets)

    total_base = sum((a.depreciable_base().amount for a in assets), Decimal("0"))

    # Pre-compute per-asset dotations for each year to avoid repeated queries
    asset_yearly: list[dict] = []
    for asset in assets:
        yearly = {
            year: asset.get_annual_amortization(year)
            for year in range(first_year, last_year + 1)
        }
        asset_yearly.append({"label": asset.label, "pk": asset.pk, "yearly": yearly})

    rows = []
    for year in range(first_year, last_year + 1):
        dotation = sum((ay["yearly"][year] for ay in asset_yearly), Decimal("0"))
        cumul = sum((a.cumulative_amortization(year) for a in assets), Decimal("0"))
        pct = (
            (cumul / total_base * Decimal("100")).quantize(Decimal("0.1"))
            if total_base > Decimal("0")
            else Decimal("0")
        )
        per_asset = {ay["label"]: float(ay["yearly"][year]) for ay in asset_yearly}
        rows.append(
            {
                "year": year,
                "annual_dotation": float(dotation),
                "per_asset": per_asset,
                "cumulative": float(cumul),
                "pct_complete": float(pct),
            }
        )

    # Build per-asset series for multi-line chart
    asset_series = [
        {
            "label": ay["label"],
            "pk": ay["pk"],
            "data": [
                {"year": year, "dotation": float(ay["yearly"][year])}
                for year in range(first_year, last_year + 1)
            ],
        }
        for ay in asset_yearly
    ]

    amortized_to_date = sum(
        (a.cumulative_amortization(today_year) for a in assets), Decimal("0")
    )
    amortized_to_date = min(amortized_to_date, total_base)
    remaining = max(Decimal("0"), total_base - amortized_to_date)

    return {
        "rows": rows,
        "asset_series": asset_series,
        "total_depreciable_base": total_base,
        "amortized_to_date": amortized_to_date,
        "remaining": remaining,
        "end_year": last_year,
    }


def get_total_amortization(property_id: int, year: int) -> Decimal:
    """Return the total amortization dotation for a property in a given year."""
    table = get_amortization_table(property_id, year)
    return sum((row["annual_dotation"] for row in table), Decimal("0"))


def get_deferred_amortization_balance(property_id: int, year: int) -> Decimal:
    """
    Compute the cumulative deferred amortization balance at the end of `year`.

    Deferred amortization from prior years is used in subsequent years when the
    operating result (recettes - charges) allows it (art. 39C CGI).

    This function iterates from the first acquisition year of any asset up to
    `year`, applying the art. 39C rule each year to derive the carryforward.
    """
    from property.models import AmortizationAsset

    earliest_qs = AmortizationAsset.objects.filter(property_id=property_id).order_by(
        "beginning_date"
    )
    if not earliest_qs.exists():
        return Decimal("0")

    first_year = earliest_qs.first().beginning_date.year  # ty: ignore[unresolved-attribute]
    if year < first_year:
        return Decimal("0")

    deferred_balance = Decimal("0")

    for y in range(first_year, year + 1):
        summary = _get_lmnp_summary_raw(property_id, y)
        result_before_amort = summary["recettes"] - summary["charges"]
        total_dotation = get_total_amortization(property_id, y)
        available_amort = total_dotation + deferred_balance

        if result_before_amort <= Decimal("0"):
            # Operating deficit: cannot deduct any amortization
            deferred_balance += total_dotation
        else:
            deductible = min(available_amort, result_before_amort)
            deferred_balance = available_amort - deductible

    return max(Decimal("0"), deferred_balance)


def _get_category_totals_for_year(property_id: int, year: int) -> dict[str, Decimal]:
    """
    Return per-management-category totals for ``property_id`` and ``year``.

    Handles recurring entries correctly: a recurring entry whose start date is
    before ``year`` (or whose occurrences span multiple years) is expanded and
    each occurrence falling within [year-01-01, year-12-31] is counted.

    For ``loan_interest`` and ``loan_insurance`` categories, loan-level
    ``PropertyLoanAnnualStatement`` values take priority over ledger entries on a
    per-loan basis:
      - Loans that have a statement for this year → their amounts are summed
        directly and the corresponding ledger entries are excluded for those loans.
      - Loans without a statement → fallback to ledger entries (existing behaviour).
    """
    from property.models import PropertyLedgerEntry, PropertyLoanAnnualStatement

    year_start = datetime.date(year, 1, 1)
    year_end = datetime.date(year, 12, 31)
    base_filter = {"property_id": property_id, "amount_currency": "EUR"}

    # ── Loan annual statements: sum up interest/insurance from bank figures ──
    statements = PropertyLoanAnnualStatement.objects.filter(
        loan__property_id=property_id,
        year=year,
    ).select_related("loan")

    statement_interest = Decimal("0")
    statement_insurance = Decimal("0")
    has_statement = statements.exists()

    for stmt in statements:
        if stmt.interest_amount is not None:
            statement_interest += stmt.interest_amount.amount
        if stmt.insurance_amount is not None:
            statement_insurance += stmt.insurance_amount.amount

    # ── Non-recurring: entry_date within the year ──────────────────────────
    non_recurring_qs = PropertyLedgerEntry.objects.filter(
        **base_filter,
        recurrence_type=PropertyLedgerEntry.RecurrenceType.NONE,
        entry_date__gte=year_start,
        entry_date__lte=year_end,
    ).exclude(capitalized_as__isnull=False)

    # When statements exist, exclude loan_interest / loan_insurance ledger entries
    # entirely (they would double-count with the bank-provided figures).
    if has_statement:
        non_recurring_qs = non_recurring_qs.exclude(
            management_category__in=_CHARGES_FINANCIERES
        )

    by_category: dict[str, Decimal] = {}
    for row in non_recurring_qs.values("management_category").annotate(
        total=Sum("amount")
    ):
        by_category[row["management_category"]] = row["total"] or Decimal("0")

    # ── Recurring: entries that overlap the year ───────────────────────────
    recurring_qs = (
        PropertyLedgerEntry.objects.filter(**base_filter)
        .exclude(recurrence_type=PropertyLedgerEntry.RecurrenceType.NONE)
        .exclude(capitalized_as__isnull=False)
        .filter(
            entry_date__lte=year_end,
        )
        .filter(
            Q(recurrence_end_date__gte=year_start) | Q(recurrence_end_date__isnull=True)
        )
        .prefetch_related("exceptions")
    )
    if has_statement:
        recurring_qs = recurring_qs.exclude(
            management_category__in=_CHARGES_FINANCIERES
        )

    for entry in recurring_qs:
        occurrences = entry.generate_occurrences(end_date=year_end)
        for occ in occurrences:
            if occ["date"] < year_start:
                continue
            cat = entry.management_category
            by_category[cat] = by_category.get(cat, Decimal("0")) + occ["amount"].amount

    # ── Inject bank-provided loan charges ──────────────────────────────────
    if statement_interest > Decimal("0"):
        by_category["loan_interest"] = (
            by_category.get("loan_interest", Decimal("0")) + statement_interest
        )
    if statement_insurance > Decimal("0"):
        by_category["loan_insurance"] = (
            by_category.get("loan_insurance", Decimal("0")) + statement_insurance
        )

    return by_category


def _get_lmnp_summary_raw(property_id: int, year: int) -> dict:
    """Internal: return recettes and charges from ledger entries (no amortization)."""
    by_category = _get_category_totals_for_year(property_id, year)

    recettes = Decimal("0")
    charges = Decimal("0")
    charges_exploitation = Decimal("0")
    charges_financieres = Decimal("0")
    for cat, total in by_category.items():
        mapping = LMNP_TAX_MAPPING.get(cat)
        if not mapping:
            continue
        if mapping["section"] == "recettes":
            recettes += total
        elif mapping["section"] == "charges":
            charges += total
            if cat in _CHARGES_FINANCIERES:
                charges_financieres += total
            else:
                charges_exploitation += total
    return {
        "recettes": recettes,
        "charges": charges,
        "charges_exploitation": charges_exploitation,
        "charges_financieres": charges_financieres,
    }


# ─── Multi-property aggregation (liasse fiscale complète) ─────────────────────


def get_bilan_data(property_id: int, year: int) -> dict:
    """
    Return 2033-A Bilan simplifié data for a property at year-end.

    Returns:
      - immobilisations_brutes: sum of all asset value_total (incl. land if setup exists)
      - amortissements_cumules: sum of cumulative amortizations up to year
      - valeur_nette_comptable: brut - cumulé
      - emprunts: remaining loan balance at year-end
      - resultat_exercice: taxable_result from LMNP summary
      - capital_individuel: cumulative equity (buying_value_gross + cumulative results)
      - total_capitaux_propres: capital + results retained
      - cout_revient_acquisitions: gross value of assets acquired during the year
    """
    from property.models import (
        AmortizationAsset,
        AmortizationSetup,
        Property,
        PropertyLoan,
    )

    assets = AmortizationAsset.objects.filter(property_id=property_id)
    brut = sum((a.value_total.amount for a in assets), Decimal("0"))

    # Add land value from setup (non-amortizable but must appear in bilan)
    try:
        setup = AmortizationSetup.objects.get(property_id=property_id)
        land_value = (
            setup.total_value.amount * setup.land_percentage / Decimal("100")
        ).quantize(Decimal("0.01"))
        brut += land_value
    except AmortizationSetup.DoesNotExist:
        land_value = Decimal("0")

    cumul = sum((a.cumulative_amortization(year) for a in assets), Decimal("0"))

    year_end = datetime.date(year, 12, 31)
    loans = PropertyLoan.objects.filter(property_id=property_id)
    emprunts = sum(
        (loan.remaining_balance(year_end).amount for loan in loans), Decimal("0")
    )

    summary = get_lmnp_summary(property_id, year)

    # Cumulative taxable results from start of activity through this year
    try:
        prop = Property.objects.get(pk=property_id)
        start_year = prop.buying_date.year if prop.buying_date else year
    except Property.DoesNotExist:
        start_year = year
    cumulative_results = sum(
        (
            get_lmnp_summary(property_id, y)["taxable_result"]
            for y in range(start_year, year + 1)
        ),
        Decimal("0"),
    )

    # Gross buying value (frais d'acquisition inclus)
    capital_base = Decimal("0")
    try:
        prop = Property.objects.get(pk=property_id)
        buying = prop.buying_value_gross or prop.buying_value
        capital_base = buying.amount
    except Property.DoesNotExist:
        pass

    capital_individuel = capital_base + cumulative_results
    total_capitaux_propres = capital_individuel  # simplified (no reserves for LMNP)

    # Cost of assets acquired during this year (2033-A-182)
    cout_revient_acquisitions = sum(
        (
            a.value_total.amount
            for a in assets
            if a.beginning_date and a.beginning_date.year == year
        ),
        Decimal("0"),
    )
    if land_value > Decimal("0") and start_year == year:
        cout_revient_acquisitions += land_value

    return {
        "immobilisations_brutes": brut,
        "amortissements_cumules": cumul,
        "valeur_nette_comptable": brut - cumul,
        "emprunts": emprunts,
        "resultat_exercice": summary["taxable_result"],
        "capital_individuel": capital_individuel,
        "total_capitaux_propres": total_capitaux_propres,
        "cout_revient_acquisitions": cout_revient_acquisitions,
    }


def get_immobilisation_movements(property_id: int, year: int) -> dict:
    """
    Return 2033-C immobilisation movements for a property.

    Returns a dict with:
      - rows: per-asset movements
      - by_cerfa_category: aggregated by cerfa category (terrains/constructions/
            installations/autres) with keys: value_start, acquisitions, value_end,
            amort_start, dotation, amort_end
      - terrains: land value from AmortizationSetup (non-amortizable)
    Each row:
      - label, cerfa_category, value_start, acquisitions, value_end,
        amort_start, dotation, amort_end, asset_pk
    """
    from property.models import AmortizationAsset, AmortizationSetup

    assets = AmortizationAsset.objects.filter(property_id=property_id).select_related(
        "property"
    )
    rows = []
    for asset in assets:
        acq_year = asset.beginning_date.year if asset.beginning_date else year
        value_total = asset.value_total.amount
        amort_start = asset.cumulative_amortization(year - 1)
        dotation = asset.get_annual_amortization(year)
        amort_end = asset.cumulative_amortization(year)
        rows.append(
            {
                "label": asset.label,
                "cerfa_category": getattr(asset, "cerfa_category", None) or "autres",
                "value_start": value_total if acq_year < year else Decimal("0"),
                "acquisitions": value_total if acq_year == year else Decimal("0"),
                "value_end": value_total,
                "amort_start": amort_start,
                "dotation": dotation,
                "amort_end": amort_end,
                "asset_pk": asset.pk,
            }
        )

    # Aggregate by cerfa category
    _zero: Decimal = Decimal("0")
    categories = ["terrains", "constructions", "installations", "autres"]
    by_cerfa: dict[str, dict] = {
        cat: {
            "value_start": _zero,
            "acquisitions": _zero,
            "value_end": _zero,
            "amort_start": _zero,
            "dotation": _zero,
            "amort_end": _zero,
        }
        for cat in categories
    }
    for row in rows:
        cat = row["cerfa_category"] if row["cerfa_category"] in categories else "autres"
        by_cerfa[cat]["value_start"] += row["value_start"]
        by_cerfa[cat]["acquisitions"] += row["acquisitions"]
        by_cerfa[cat]["value_end"] += row["value_end"]
        by_cerfa[cat]["amort_start"] += row["amort_start"]
        by_cerfa[cat]["dotation"] += row["dotation"]
        by_cerfa[cat]["amort_end"] += row["amort_end"]

    # Land (terrains) from AmortizationSetup — non-amortizable
    terrains_value = Decimal("0")
    try:
        setup = AmortizationSetup.objects.get(property_id=property_id)
        terrains_value = (
            setup.total_value.amount * setup.land_percentage / Decimal("100")
        ).quantize(Decimal("0.01"))
    except AmortizationSetup.DoesNotExist:
        pass

    if terrains_value > Decimal("0"):
        by_cerfa["terrains"]["value_end"] = terrains_value
        by_cerfa["terrains"]["value_start"] = (
            terrains_value
            if year
            > (
                AmortizationAsset.objects.filter(property_id=property_id)
                .order_by("beginning_date")
                .values_list("beginning_date__year", flat=True)
                .first()
                or year
            )
            else Decimal("0")
        )
        by_cerfa["terrains"]["acquisitions"] = (
            terrains_value - by_cerfa["terrains"]["value_start"]
        )

    return {
        "rows": rows,
        "by_cerfa_category": by_cerfa,
        "terrains_value": terrains_value,
    }


def get_accounting_data(properties: list, year: int) -> dict:
    """
    Aggregate the full LMNP liasse fiscale for a list of properties.

    Returns a dict with keys for each cerfa form:
      - form_2033b: 2033-B Compte de résultat (aggregated + per-property breakdown)
      - form_2033a: 2033-A Bilan simplifié (aggregated)
      - form_2033c: 2033-C Immobilisations (per-property)
      - form_2031: 2031 résultat BIC summary
      - form_2031bis: 2031-BIS annex (charges by category, deferred amort)
      - form_2042c: 2042-C PRO cases 5NK/5NZ + deficit carryforward 5GJ..5GA
    """
    # ── 2033-B: aggregate by cerfa line ──────────────────────────────────────
    agg_recettes = Decimal("0")
    agg_charges = Decimal("0")
    agg_charges_exploitation = Decimal("0")
    agg_charges_financieres = Decimal("0")
    agg_amort_total = Decimal("0")
    agg_amort_deductible = Decimal("0")
    agg_amort_deferred = Decimal("0")
    agg_deferred_prior = Decimal("0")
    agg_taxable_result = Decimal("0")
    agg_result_before = Decimal("0")
    agg_cerfa_310 = Decimal("0")
    agg_cerfa_318 = Decimal("0")

    # Aggregated cerfa line amounts
    agg_by_line: dict[str, Decimal] = {}
    # Per-property breakdown: {line: [{property_name, amount}]}
    per_prop_by_line: dict[str, list[dict]] = {}

    # Per-property summaries for other forms
    per_prop_summaries: list[dict] = []

    for prop in properties:
        summary = get_lmnp_summary(prop.pk, year)
        agg_recettes += summary["recettes"]
        agg_charges += summary["charges"]
        agg_charges_exploitation += summary["charges_exploitation"]
        agg_charges_financieres += summary["charges_financieres"]
        agg_amort_total += summary["amortization_total"]
        agg_amort_deductible += summary["amortization_deductible"]
        agg_amort_deferred += summary["amortization_deferred"]
        agg_deferred_prior += summary["deferred_prior"]
        agg_taxable_result += summary["taxable_result"]
        agg_result_before += summary["result"]
        agg_cerfa_310 += summary["cerfa_310"]
        agg_cerfa_318 += summary["cerfa_318"]

        for line, amount in summary["by_line"].items():
            agg_by_line[line] = agg_by_line.get(line, Decimal("0")) + amount
            per_prop_by_line.setdefault(line, []).append(
                {"name": prop.name, "amount": amount}
            )
        per_prop_summaries.append({"property": prop, "summary": summary})

    # Cerfa 2033-B: résultat d'exploitation (270) = recettes - charges_exploitation - amort_deductible
    agg_result_exploitation = (
        agg_recettes - agg_charges_exploitation - agg_amort_deductible
    )
    # Cerfa 2033-B line 352: résultat fiscal avant déficits = max(0, taxable_result)
    agg_cerfa_352 = max(Decimal("0"), agg_taxable_result)
    # Cerfa 2033-B line 370: résultat fiscal final (after deficit imputation, always >= 0)
    # Computed from 2042-C PRO data below

    form_2033b = {
        "recettes": agg_recettes,
        "charges": agg_charges,
        "charges_exploitation": agg_charges_exploitation,
        "charges_financieres": agg_charges_financieres,
        "result": agg_result_before,
        "result_exploitation": agg_result_exploitation,
        "amortization_total": agg_amort_total,
        "deferred_prior": agg_deferred_prior,
        "amortization_deductible": agg_amort_deductible,
        "amortization_deferred": agg_amort_deferred,
        "taxable_result": agg_taxable_result,
        "cerfa_310": agg_cerfa_310,
        "cerfa_318": agg_cerfa_318,
        "cerfa_352": agg_cerfa_352,
        "by_line": agg_by_line,
        "per_prop_by_line": per_prop_by_line,
        "per_prop": per_prop_summaries,
    }

    # ── 2033-A: aggregate bilan ───────────────────────────────────────────────
    agg_brut = Decimal("0")
    agg_cumul = Decimal("0")
    agg_emprunts = Decimal("0")
    agg_capital = Decimal("0")
    agg_capitaux_propres = Decimal("0")
    agg_cout_revient = Decimal("0")
    per_prop_bilan: list[dict] = []

    for prop in properties:
        bilan = get_bilan_data(prop.pk, year)
        agg_brut += bilan["immobilisations_brutes"]
        agg_cumul += bilan["amortissements_cumules"]
        agg_emprunts += bilan["emprunts"]
        agg_capital += bilan["capital_individuel"]
        agg_capitaux_propres += bilan["total_capitaux_propres"]
        agg_cout_revient += bilan["cout_revient_acquisitions"]
        per_prop_bilan.append({"property": prop, "bilan": bilan})

    form_2033a = {
        "immobilisations_brutes": agg_brut,
        "amortissements_cumules": agg_cumul,
        "valeur_nette_comptable": agg_brut - agg_cumul,
        "emprunts": agg_emprunts,
        "resultat_exercice": agg_taxable_result,
        "capital_individuel": agg_capital,
        "total_capitaux_propres": agg_capitaux_propres,
        "cout_revient_acquisitions": agg_cout_revient,
        "per_prop": per_prop_bilan,
    }

    # ── 2033-C: immobilisation movements per property ─────────────────────────
    per_prop_immobilisations: list[dict] = []
    for prop in properties:
        movements = get_immobilisation_movements(prop.pk, year)
        per_prop_immobilisations.append({"property": prop, "movements": movements})

    form_2033c = {"per_prop": per_prop_immobilisations}

    # ── 2031: BIC result summary ──────────────────────────────────────────────
    form_2031 = {
        "recettes": agg_recettes,
        "charges": agg_charges,
        "amortization_deductible": agg_amort_deductible,
        "taxable_result": agg_taxable_result,
        "regime": "Réel simplifié",
        "activite": "Location meublée non professionnelle",
    }

    # ── 2031-BIS: annex ──────────────────────────────────────────────────────
    agg_by_category: dict[str, Decimal] = {}
    for entry in per_prop_summaries:
        for cat, amt in entry["summary"].get("by_category", {}).items():
            agg_by_category[cat] = agg_by_category.get(cat, Decimal("0")) + amt

    charges_detail = []
    for cat, total in agg_by_category.items():
        mapping = LMNP_TAX_MAPPING.get(cat)
        if mapping and mapping["section"] == "charges":
            charges_detail.append(
                {"category": cat, "label": mapping["label"], "amount": total}
            )

    form_2031bis = {
        "charges_detail": charges_detail,
        "amort_total": agg_amort_total,
        "amort_deductible": agg_amort_deductible,
        "amort_deferred_balance": agg_amort_deferred,
        "taxable_result": agg_taxable_result,
    }

    # ── 2042-C PRO ────────────────────────────────────────────────────────────
    # Aggregate deficit carryforward across all properties
    agg_deficit_history: dict[int, Decimal] = {}
    for prop in properties:
        prop_history = get_fiscal_deficit_history(prop.pk, year)
        for origin_year, deficit in prop_history.items():
            agg_deficit_history[origin_year] = (
                agg_deficit_history.get(origin_year, Decimal("0")) + deficit
            )

    # Total available deficit carryforward
    total_deficit_carryforward = sum(agg_deficit_history.values(), Decimal("0"))

    if agg_taxable_result >= Decimal("0"):
        # Benefice: impute prior deficits
        case_5nk = max(Decimal("0"), agg_taxable_result - total_deficit_carryforward)
        case_5nz = Decimal("0")
    else:
        # Deficit year
        case_5nk = Decimal("0")
        case_5nz = abs(agg_taxable_result)

    # Cerfa 2033-B line 370: result after deficit imputation
    agg_cerfa_370 = case_5nk

    form_2033b["cerfa_370"] = agg_cerfa_370

    # Per-year deficit amounts (for 2042-C PRO cases 5GJ to 5GA: N-1..N-10)
    deficit_cases: dict[str, Decimal] = {}
    case_labels = ["5GJ", "5GI", "5GH", "5GG", "5GF", "5GE", "5GD", "5GC", "5GB", "5GA"]
    for i, label in enumerate(case_labels, start=1):
        origin_year = year - i
        deficit_cases[label] = agg_deficit_history.get(origin_year, Decimal("0"))

    # Duration of exercise in months (standard = 12)
    today = datetime.date.today()
    if today.year == year:
        exercise_months = today.month
    else:
        exercise_months = 12

    form_2042c = {
        "case_5nk": case_5nk,  # résultat bénéficiaire après imputation déficits
        "case_5nz": case_5nz,  # résultat déficitaire de l'année
        "deficit_carryforward": total_deficit_carryforward,
        "deficit_history": agg_deficit_history,
        "case_5cd": exercise_months,
        "is_benefice": agg_taxable_result >= Decimal("0"),
        **deficit_cases,
    }

    return {
        "form_2033b": form_2033b,
        "form_2033a": form_2033a,
        "form_2033c": form_2033c,
        "form_2031": form_2031,
        "form_2031bis": form_2031bis,
        "form_2042c": form_2042c,
    }
