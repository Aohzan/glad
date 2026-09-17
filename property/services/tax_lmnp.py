"""
LMNP réel tax engine.

The engine turns the ledger entries and the amortization assets of the LMNP
properties into the figures of the French tax forms (liasse fiscale):
2033-A (bilan), 2033-B (compte de résultat), 2033-C (immobilisations),
2031/2031-bis, SUIV39C and 2042-C PRO.

Reading guide
=============

The computation is a chronological forward pass over the fiscal years of the
activity, one ``LmnpYearInputs`` in, one ``LmnpYearResult`` out, with a
``FiscalCarry`` (deferred amortization and unused deficits) handed from one
year to the next. ``compute_year`` is a pure function with no database
access: it is the single place where the tax rules are written down and it is
tested against the reference LMNP workbook.

Every field of ``LmnpYearResult`` is named after its cerfa line (``_218``,
``_310``…) and documents its formula, so that the code can be cross-checked
against the official forms and against public sources:

- art. 39 C II CGI and BOI-BIC-AMT-20-40-10-20 § 40-70: the amortization
  deductible in a year is capped at the rents minus the other charges of the
  property (accounting fees excluded). The excess is carried forward without
  time limit (amortissements réputés différés, SUIV39C).
- art. 156 I 1° ter CGI: a BIC non professionnel deficit is only deductible
  from BIC non professionnel profits of the ten following years (2042-C PRO
  boxes 5GA to 5GJ).
- finance act 2025 art. 84: the amortization deducted is added back to the
  capital gain when the property is sold (not computed here).

Dated constants (thresholds, rates) live in ``property.services.lmnp_rules``.

2033-B cerfa line reference:
  218 = Production vendue (services): loyers et charges refacturées
  209 = Autres produits d'exploitation
  242 = Autres charges externes: gestion, copropriété, entretien, assurances…
  244 = Impôts, taxes et versements assimilés: taxe foncière, CFE
  243 = dont CFE (sous-ligne de 244)
  254 = Dotations aux amortissements (= 2033-C ligne 572)
  270 = Résultat d'exploitation
  294 = Charges financières: intérêts d'emprunt
  310 = Bénéfice ou perte (résultat comptable)
  318 = Réintégration: amortissements non déductibles (art. 39 C)
  350 = Déduction: amortissements différés antérieurs imputés (art. 39 C)
  352 = Résultat fiscal avant imputation des déficits antérieurs
  360 = Déficits antérieurs imputés
  370 = Résultat fiscal après imputation des déficits antérieurs
"""

import datetime
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

from property.models.ledger import ManagementCategory
from property.services.lmnp_rules import (
    CAP_39C_EXCLUDED_CATEGORIES,
    DEFICIT_CARRYFORWARD_YEARS,
)

ZERO = Decimal(0)

# 2042-C PRO boxes for the deficits of the previous years not yet deducted,
# from N-1 (5GJ) to N-10 (5GA).
DEFICIT_CASES_5G = (
    "5GJ",
    "5GI",
    "5GH",
    "5GG",
    "5GF",
    "5GE",
    "5GD",
    "5GC",
    "5GB",
    "5GA",
)


def _build_by_line_categories(by_category: dict[str, Decimal]) -> dict[str, list[dict]]:
    """
    Build a per-cerfa-line breakdown of all mapped categories with their amounts.

    All categories with a cerfa line are included, even if amount is zero, so that
    the template can display a complete list for each cerfa line.

    Also includes a virtual "recettes" key grouping all section="recettes" categories.

    Returns:
        dict mapping cerfa line (str) → list of {key, label, amount} sorted by label.
    """
    result: dict[str, list[dict]] = {}

    for cat in ManagementCategory:
        if not cat.lmnp_line:
            continue
        amount = by_category.get(str(cat), Decimal(0))
        result.setdefault(cat.lmnp_line, []).append(
            {"key": cat.value, "label": cat.lmnp_label, "amount": amount}
        )

    # Sort each line's categories alphabetically by label
    for value in result.values():
        value.sort(key=lambda x: x["label"])

    # Virtual "recettes" group: all section="recettes" categories (for 218/209 combined row)
    recettes_cats = sorted(
        [
            {
                "key": cat.value,
                "label": cat.lmnp_label,
                "amount": by_category.get(str(cat), Decimal(0)),
            }
            for cat in ManagementCategory
            if cat.lmnp_section == "recettes"
        ],
        key=lambda x: x["label"],
    )
    result["recettes"] = recettes_cats

    return result


# ─── Pure tax engine (no database access) ─────────────────────────────────────


@dataclass(frozen=True)
class LmnpYearInputs:
    """Everything the tax engine needs for one fiscal year, all properties combined.

    Amounts come from the ledger (``get_property_year_lines``) and from the
    amortization assets; field names carry the 2033-B line they feed.
    """

    year: int
    #: Loyers, charges refacturées, reversements (2033-B 218).
    revenue_218: Decimal = ZERO
    #: Autres produits (2033-B 209).
    other_income_209: Decimal = ZERO
    #: Autres charges externes (2033-B 242), accounting fees included.
    external_charges_242: Decimal = ZERO
    #: Part of line 242 that is not "afférente au bien" for the art. 39 C cap.
    accounting_fees: Decimal = ZERO
    #: Impôts et taxes (2033-B 244): taxe foncière + CFE.
    taxes_244: Decimal = ZERO
    #: dont CFE (2033-B 243).
    cfe_243: Decimal = ZERO
    #: Intérêts d'emprunt (2033-B 294).
    financial_charges_294: Decimal = ZERO
    #: Dotation aux amortissements de l'exercice (2033-B 254 = 2033-C 572).
    depreciation_254: Decimal = ZERO
    #: First day of the activity; drives the length of the first fiscal year (5CD).
    activity_start: datetime.date | None = None


@dataclass(frozen=True)
class FiscalCarry:
    """What one fiscal year hands over to the next."""

    #: Amortissements réputés différés (art. 39 C) not yet deducted, no time limit.
    deferred_depreciation: Decimal = ZERO
    #: Unused BIC non professionnel deficits, by year of origin (10-year limit).
    deficits: dict[int, Decimal] = field(default_factory=dict)


@dataclass(frozen=True)
class LmnpYearResult:
    """The tax figures of one fiscal year. One field per cerfa line."""

    year: int

    # ── 2033-B, A: résultat comptable ────────────────────────────────────────
    revenue_218: Decimal
    other_income_209: Decimal
    external_charges_242: Decimal
    accounting_fees: Decimal
    taxes_244: Decimal
    cfe_243: Decimal
    depreciation_254: Decimal
    #: 270 = 218 + 209 − 242 − 244 − 254
    operating_result_270: Decimal
    financial_charges_294: Decimal
    #: 310 = 270 − 294 (bénéfice ou perte comptable)
    accounting_result_310: Decimal

    # ── Art. 39 C: amortization cap ──────────────────────────────────────────
    #: max(0, 218 + 209 − (242 − frais de comptabilité) − 244 − 294)
    depreciation_cap_39c: Decimal
    #: min(254, cap): the part of this year's dotation that is deductible.
    depreciation_deducted: Decimal
    #: 318 = 254 − déduit: réintégration "amortissements non déductibles".
    depreciation_reintegrated_318: Decimal
    #: Stock of deferred amortization at the start of the year.
    deferred_depreciation_start: Decimal
    #: 350 = min(stock début, max(0, 310 + 318)): déduction des ARD antérieurs.
    deferred_depreciation_used_350: Decimal
    #: Stock at the end of the year = début + 318 − 350 (SUIV39C).
    deferred_depreciation_end: Decimal

    # ── 2033-B, B: résultat fiscal ───────────────────────────────────────────
    #: 352 = 310 + 318 − 350, signed (bénéfice > 0, déficit < 0).
    fiscal_result_352: Decimal
    #: Déficits antérieurs encore reportables au début de l'année (after the
    #: 10-year purge), by year of origin.
    prior_deficits_start: dict[int, Decimal]
    #: 360 = déficits antérieurs imputés = min(Σ disponibles, max(0, 352)).
    prior_deficits_used_360: Decimal
    #: Déficits reportables en fin d'année, by year of origin (includes this year).
    deficits_end: dict[int, Decimal]
    #: 370 = 352 − 360 when 352 > 0, else 352.
    fiscal_result_370: Decimal

    # ── 2042-C PRO ───────────────────────────────────────────────────────────
    #: 5NA revenus imposables, régime réel, cas général = max(0, 370).
    case_5na: Decimal
    #: 5NY déficit de l'année, régime réel, cas général = max(0, −352).
    case_5ny: Decimal
    #: 5CD durée de l'exercice en mois (12, or fewer for the first year).
    case_5cd: int
    #: (box, year of origin, remaining deficit) for 5GJ (N-1) … 5GA (N-10).
    deficit_cases: tuple[tuple[str, int, Decimal], ...]

    @property
    def is_profit(self) -> bool:
        return self.fiscal_result_352 >= ZERO

    @property
    def deficit_carryforward(self) -> Decimal:
        """Total deficit still reportable at the end of the year."""
        return sum(self.deficits_end.values(), ZERO)

    def as_dict(self) -> dict:
        """Plain dict (JSON-friendly after freezing) of every field."""
        data = asdict(self)
        data["is_profit"] = self.is_profit
        data["deficit_carryforward"] = self.deficit_carryforward
        return data


def exercise_months(year: int, activity_start: datetime.date | None) -> int:
    """Return the length of the fiscal year in months (2042-C PRO 5CD).

    The first fiscal year runs from the start of the activity to 31 December;
    every other year is a full 12-month year (Glad only handles calendar years).
    """
    if activity_start is not None and activity_start.year == year:
        return 12 - activity_start.month + 1
    return 12


def compute_year(
    inputs: LmnpYearInputs, carry: FiscalCarry | None = None
) -> tuple[LmnpYearResult, FiscalCarry]:
    """Compute the tax figures of one year and the carry for the next one.

    Pure function: this is the whole LMNP réel computation. Each step names
    the cerfa line it fills; see the module docstring for the sources.
    """
    carry = carry or FiscalCarry()
    year = inputs.year
    income = inputs.revenue_218 + inputs.other_income_209

    # A - Résultat comptable (2033-B)
    operating_result_270 = (
        income
        - inputs.external_charges_242
        - inputs.taxes_244
        - inputs.depreciation_254
    )
    accounting_result_310 = operating_result_270 - inputs.financial_charges_294

    # Art. 39 C: the dotation is deductible up to the rents minus the charges
    # "afférentes au bien" (interest and taxes included, accounting fees excluded).
    depreciation_cap_39c = max(
        ZERO,
        income
        - (inputs.external_charges_242 - inputs.accounting_fees)
        - inputs.taxes_244
        - inputs.financial_charges_294,
    )
    depreciation_deducted = min(inputs.depreciation_254, depreciation_cap_39c)
    depreciation_reintegrated_318 = inputs.depreciation_254 - depreciation_deducted

    # Deferred amortization of previous years is deducted (line 350) as soon as
    # the result before that deduction is a profit, without creating a deficit.
    result_before_deferred = accounting_result_310 + depreciation_reintegrated_318
    deferred_depreciation_used_350 = min(
        carry.deferred_depreciation, max(ZERO, result_before_deferred)
    )
    deferred_depreciation_end = (
        carry.deferred_depreciation
        + depreciation_reintegrated_318
        - deferred_depreciation_used_350
    )

    # B - Résultat fiscal avant imputation des déficits antérieurs (352)
    fiscal_result_352 = result_before_deferred - deferred_depreciation_used_350

    # Déficits antérieurs: a deficit born in year N is usable from N+1 to N+10.
    prior_deficits_start = {
        origin: amount
        for origin, amount in sorted(carry.deficits.items())
        if origin + DEFICIT_CARRYFORWARD_YEARS >= year and amount > ZERO
    }
    deficits_end = dict(prior_deficits_start)
    prior_deficits_used_360 = ZERO
    if fiscal_result_352 > ZERO:
        remaining_profit = fiscal_result_352
        for origin in sorted(deficits_end):  # oldest first
            if remaining_profit <= ZERO:
                break
            used = min(deficits_end[origin], remaining_profit)
            deficits_end[origin] -= used
            remaining_profit -= used
            prior_deficits_used_360 += used
        deficits_end = {o: d for o, d in deficits_end.items() if d > ZERO}
        fiscal_result_370 = fiscal_result_352 - prior_deficits_used_360
    else:
        if fiscal_result_352 < ZERO:
            deficits_end[year] = -fiscal_result_352
        fiscal_result_370 = fiscal_result_352

    result = LmnpYearResult(
        year=year,
        revenue_218=inputs.revenue_218,
        other_income_209=inputs.other_income_209,
        external_charges_242=inputs.external_charges_242,
        accounting_fees=inputs.accounting_fees,
        taxes_244=inputs.taxes_244,
        cfe_243=inputs.cfe_243,
        depreciation_254=inputs.depreciation_254,
        operating_result_270=operating_result_270,
        financial_charges_294=inputs.financial_charges_294,
        accounting_result_310=accounting_result_310,
        depreciation_cap_39c=depreciation_cap_39c,
        depreciation_deducted=depreciation_deducted,
        depreciation_reintegrated_318=depreciation_reintegrated_318,
        deferred_depreciation_start=carry.deferred_depreciation,
        deferred_depreciation_used_350=deferred_depreciation_used_350,
        deferred_depreciation_end=deferred_depreciation_end,
        fiscal_result_352=fiscal_result_352,
        prior_deficits_start=prior_deficits_start,
        prior_deficits_used_360=prior_deficits_used_360,
        deficits_end=deficits_end,
        fiscal_result_370=fiscal_result_370,
        case_5na=max(ZERO, fiscal_result_370),
        case_5ny=max(ZERO, -fiscal_result_352),
        case_5cd=exercise_months(year, inputs.activity_start),
        deficit_cases=tuple(
            (box, year - offset, deficits_end.get(year - offset, ZERO))
            for offset, box in enumerate(DEFICIT_CASES_5G, start=1)
        ),
    )
    next_carry = FiscalCarry(
        deferred_depreciation=deferred_depreciation_end, deficits=dict(deficits_end)
    )
    return result, next_carry


def compute_years(inputs_by_year: Iterable[LmnpYearInputs]) -> list[LmnpYearResult]:
    """Run ``compute_year`` chronologically over consecutive years."""
    results: list[LmnpYearResult] = []
    carry = FiscalCarry()
    for inputs in sorted(inputs_by_year, key=lambda i: i.year):
        result, carry = compute_year(inputs, carry)
        results.append(result)
    return results


# ─── Ledger aggregation ───────────────────────────────────────────────────────


def get_category_totals_for_year(property_id: int, year: int) -> dict[str, Decimal]:
    """
    Return per-management-category totals for ``property_id`` and ``year``.

    Handles recurring entries correctly: a recurring entry whose start date is
    before ``year`` (or whose occurrences span multiple years) is expanded and
    each occurrence falling within [year-01-01, year-12-31] is counted.

    For ``loan_interest`` and ``loan_insurance`` categories, ledger entries are
    used when present. When no manual ``loan_interest`` ledger entries exist for
    the year, the interest column of the loan amortization table is used instead
    (summed over all loans that have amortization entries for that year).
    """
    from property.models import (
        PropertyLedgerEntry,
        PropertyLoan,
        PropertyLoanAmortizationEntry,
    )

    year_start = datetime.date(year, 1, 1)
    year_end = datetime.date(year, 12, 31)
    base_filter = {"property_id": property_id, "amount_currency": "EUR"}

    # ── Non-recurring: entry_date within the year ──────────────────────────
    non_recurring_qs = PropertyLedgerEntry.objects.filter(
        **base_filter,
        recurrence_type=PropertyLedgerEntry.RecurrenceType.NONE,
        entry_date__gte=year_start,
        entry_date__lte=year_end,
    ).exclude(capitalized_as__isnull=False)

    by_category: dict[str, Decimal] = {}
    for row in non_recurring_qs.values("management_category").annotate(
        total=Sum("amount")
    ):
        by_category[row["management_category"]] = row["total"] or Decimal(0)

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

    for entry in recurring_qs:
        occurrences = entry.generate_occurrences(end_date=year_end)
        for occ in occurrences:
            if occ["date"] < year_start:
                continue
            cat = entry.management_category
            by_category[cat] = by_category.get(cat, Decimal(0)) + occ["amount"].amount

    # ── Fallback: use loan amortization entries for loan_interest ─────────
    # When no manual loan_interest ledger entries exist for the year, sum the
    # interest column from PropertyLoanAmortizationEntry for all property loans.
    loan_interest_key = str(ManagementCategory.LOAN_INTEREST)
    if not by_category.get(loan_interest_key):
        loans = PropertyLoan.objects.filter(property_id=property_id)
        amort_interest_total = Decimal(0)
        for loan in loans:
            result = PropertyLoanAmortizationEntry.objects.filter(
                loan=loan,
                date__gte=year_start,
                date__lte=year_end,
            ).aggregate(total=Sum("interest"))
            amort_interest_total += result["total"] or Decimal(0)
        if amort_interest_total > Decimal(0):
            by_category[loan_interest_key] = amort_interest_total

    return by_category


# ─── Database loaders ─────────────────────────────────────────────────────────


def _resolve_properties(properties: Sequence | int) -> list:
    """Accept Property instances, ids or a single id and return Property objects."""
    from property.models import Property

    if isinstance(properties, int):
        properties = [properties]
    ids = [p if isinstance(p, int) else p.pk for p in properties]
    found = {p.pk: p for p in Property.objects.filter(pk__in=ids)}
    return [found[i] for i in ids if i in found]


def get_activity_start_date(properties: Sequence) -> datetime.date | None:
    """Return the first day of the LMNP activity across ``properties``."""
    starts = [p.amortization_start_date for p in properties if p.buying_date]
    return min(starts) if starts else None


def get_first_fiscal_year(properties: Sequence, assets: Sequence) -> int | None:
    """Return the first fiscal year of the activity, or None without any data."""
    years = [p.amortization_start_date.year for p in properties if p.buying_date] + [
        a.beginning_date.year for a in assets if a.beginning_date
    ]
    return min(years) if years else None


def _total_dotation(assets: Iterable, year: int) -> Decimal:
    return sum((a.get_annual_amortization(year) for a in assets), ZERO)


def get_property_year_lines(
    property_id: int, year: int, assets: Sequence | None = None
) -> dict:
    """Return the 2033-B "A - résultat comptable" lines of one property for a year.

    This is the per-property detail shown on the dashboard; the fiscal layer
    (art. 39 C cap, deferred amortization, deficits) is computed once for the
    whole activity by ``compute_activity``.

    Keys: year, recettes (218 + 209), charges (242 + 244 + 294),
    charges_exploitation (242 + 244), charges_financieres (294),
    accounting_fees, result (recettes − charges), amortization_total (254),
    cerfa_310 (result − 254), by_category, by_line, by_line_categories.
    """
    from property.models import AmortizationAsset

    if assets is None:
        assets = list(AmortizationAsset.objects.filter(property_id=property_id))

    by_category = get_category_totals_for_year(property_id, year)

    recettes = charges = charges_exploitation = charges_financieres = ZERO
    accounting_fees = ZERO
    by_line: dict[str, Decimal] = {}
    for cat, total in by_category.items():
        try:
            cat_enum = ManagementCategory(cat)
        except ValueError:
            continue
        if cat_enum.lmnp_line:
            by_line[cat_enum.lmnp_line] = by_line.get(cat_enum.lmnp_line, ZERO) + total
        if cat_enum.lmnp_section == "recettes":
            recettes += total
        elif cat_enum.lmnp_section == "charges":
            charges += total
            if cat_enum.lmnp_line == "294":
                charges_financieres += total
            else:
                charges_exploitation += total
            if cat_enum.value in CAP_39C_EXCLUDED_CATEGORIES:
                accounting_fees += total

    cfe_total = by_category.get(str(ManagementCategory.CFE), ZERO)
    if cfe_total > ZERO:
        by_line["243"] = cfe_total

    amortization_total = _total_dotation(assets, year)
    result = recettes - charges
    if amortization_total > ZERO:
        by_line["254"] = amortization_total

    return {
        "year": year,
        "recettes": recettes,
        "charges": charges,
        "charges_exploitation": charges_exploitation,
        "charges_financieres": charges_financieres,
        "accounting_fees": accounting_fees,
        "result": result,
        "amortization_total": amortization_total,
        "cerfa_310": result - amortization_total,
        "by_category": by_category,
        "by_line": by_line,
        "by_line_categories": _build_by_line_categories(by_category),
    }


def build_year_inputs(
    year: int, lines: Iterable[dict], activity_start: datetime.date | None
) -> LmnpYearInputs:
    """Sum the per-property lines of a year into the engine inputs."""
    lines = list(lines)

    def total(key: str) -> Decimal:
        return sum((line[key] for line in lines), ZERO)

    def line_total(number: str) -> Decimal:
        return sum((line["by_line"].get(number, ZERO) for line in lines), ZERO)

    return LmnpYearInputs(
        year=year,
        revenue_218=line_total("218"),
        other_income_209=line_total("209"),
        external_charges_242=line_total("242"),
        accounting_fees=total("accounting_fees"),
        taxes_244=line_total("244"),
        cfe_243=line_total("243"),
        financial_charges_294=line_total("294"),
        depreciation_254=total("amortization_total"),
        activity_start=activity_start,
    )


def compute_activity(properties: Sequence | int, year: int) -> list[LmnpYearResult]:
    """Compute every fiscal year of the LMNP activity, from its start to ``year``.

    The activity groups all the given properties: French tax law knows one
    LMNP activity per taxpayer (one 2033-B, one 2042-C PRO), so the art. 39 C
    cap and the deficits are tracked globally, not per property.
    Returns an empty list when ``year`` precedes the start of the activity.
    """
    from property.models import AmortizationAsset

    props = _resolve_properties(properties)
    if not props:
        return []
    assets_by_property: dict[int, list] = {p.pk: [] for p in props}
    for asset in AmortizationAsset.objects.filter(property_id__in=assets_by_property):
        assets_by_property[asset.property_id].append(asset)  # ty: ignore[unresolved-attribute]
    all_assets = [a for assets in assets_by_property.values() for a in assets]

    first_year = get_first_fiscal_year(props, all_assets)
    if first_year is None or year < first_year:
        return []
    activity_start = get_activity_start_date(props)

    inputs = [
        build_year_inputs(
            y,
            (get_property_year_lines(p.pk, y, assets_by_property[p.pk]) for p in props),
            activity_start,
        )
        for y in range(first_year, year + 1)
    ]
    return compute_years(inputs)


def compute_activity_year(properties: Sequence | int, year: int) -> LmnpYearResult:
    """Return the ``LmnpYearResult`` of ``year`` (all zeros before the activity)."""
    results = compute_activity(properties, year)
    if results:
        return results[-1]
    props = _resolve_properties(properties)
    empty = LmnpYearInputs(year=year, activity_start=get_activity_start_date(props))
    return compute_year(empty)[0]


# ─── Backward-compatible wrappers ─────────────────────────────────────────────


def get_lmnp_summary(property_id: int, year: int) -> dict:
    """Return the annual LMNP summary of one property, as if it were alone.

    Combines ``get_property_year_lines`` with the fiscal layer computed on the
    property alone. Legacy keys kept for the tests and the per-property views:
    taxable_result (352), amortization_deductible, amortization_deferred (318),
    deferred_prior (deferred stock at start), deferred_balance (at end),
    cerfa_318, cerfa_350, cerfa_352, cerfa_370.
    """
    summary = get_property_year_lines(property_id, year)
    fiscal = compute_activity_year(property_id, year)
    summary.update(
        {
            "plafond_39c": fiscal.depreciation_cap_39c,
            "amortization_deductible": fiscal.depreciation_deducted,
            "amortization_deferred": fiscal.depreciation_reintegrated_318,
            "deferred_prior": fiscal.deferred_depreciation_start,
            "deferred_balance": fiscal.deferred_depreciation_end,
            "cerfa_318": fiscal.depreciation_reintegrated_318,
            "cerfa_350": fiscal.deferred_depreciation_used_350,
            "cerfa_352": fiscal.fiscal_result_352,
            "cerfa_370": fiscal.fiscal_result_370,
            "taxable_result": fiscal.fiscal_result_352,
        }
    )
    return summary


def get_deferred_amortization_balance(properties: Sequence | int, year: int) -> Decimal:
    """Return the deferred amortization (art. 39 C) still to deduct at the end of ``year``."""
    results = compute_activity(properties, year)
    return results[-1].deferred_depreciation_end if results else ZERO


def get_fiscal_deficit_history(
    properties: Sequence | int, year: int
) -> dict[int, Decimal]:
    """Return the deficits still reportable at the end of ``year``, by year of origin."""
    results = compute_activity(properties, year)
    return dict(results[-1].deficits_end) if results else {}


def get_fiscal_deficit_carryforward(properties: Sequence | int, year: int) -> Decimal:
    """Return the total deficit still reportable at the end of ``year``."""
    return sum(get_fiscal_deficit_history(properties, year).values(), ZERO)


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
        if setup_total and setup_total > Decimal(0):
            global_pct = (
                asset.value_total.amount / setup_total * Decimal(100)
            ).quantize(Decimal("0.1"))
        end_year = asset.amortization_end_year
        pct_amortized = (
            (cumul / base.amount * Decimal(100)).quantize(Decimal("0.1"))
            if base.amount > Decimal(0) and asset.is_depreciable
            else Decimal(0)
        )
        is_complete = end_year is not None and year >= end_year
        table.append(
            {
                "label": asset.label,
                "depreciable_base": base.amount,
                "value_total": asset.value_total.amount,
                "duration_years": asset.duration_years,
                "is_depreciable": asset.is_depreciable,
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
            "total_depreciable_base": Decimal(0),
            "amortized_to_date": Decimal(0),
            "remaining": Decimal(0),
            "end_year": None,
        }

    # Separate depreciable assets (not land) from non-depreciable ones
    depreciable_assets = [a for a in assets if a.is_depreciable]

    if not depreciable_assets:
        return {
            "rows": [],
            "asset_series": [],
            "total_depreciable_base": Decimal(0),
            "amortized_to_date": Decimal(0),
            "remaining": Decimal(0),
            "end_year": None,
        }

    first_year = min(a.beginning_date.year for a in depreciable_assets)
    last_year = max(
        end_year
        for a in depreciable_assets
        if (end_year := a.amortization_end_year) is not None
    )

    # Totals consider only depreciable assets (land is not amortized)
    total_base = sum(
        (a.depreciable_base().amount for a in depreciable_assets), Decimal(0)
    )

    # Pre-compute per-asset dotations for each year to avoid repeated queries
    # Only depreciable assets are included in the chart series
    asset_yearly: list[dict] = []
    for asset in depreciable_assets:
        yearly = {
            year: asset.get_annual_amortization(year)
            for year in range(first_year, last_year + 1)
        }
        asset_yearly.append({"label": asset.label, "pk": asset.pk, "yearly": yearly})

    rows = []
    for year in range(first_year, last_year + 1):
        dotation = sum((ay["yearly"][year] for ay in asset_yearly), Decimal(0))
        cumul = sum(
            (a.cumulative_amortization(year) for a in depreciable_assets), Decimal(0)
        )
        pct = (
            (cumul / total_base * Decimal(100)).quantize(Decimal("0.1"))
            if total_base > Decimal(0)
            else Decimal(0)
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

    # Build per-asset series for multi-line chart (terrains excluded — not depreciable)
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
        (a.cumulative_amortization(today_year) for a in depreciable_assets),
        Decimal(0),
    )
    amortized_to_date = min(amortized_to_date, total_base)
    remaining = max(Decimal(0), total_base - amortized_to_date)

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
    return sum((row["annual_dotation"] for row in table), Decimal(0))


# ─── 2033-A / 2033-C ──────────────────────────────────────────────────────────


def get_bilan_data(property_id: int, year: int) -> dict:
    """
    Return 2033-A Bilan simplifié data for a property at year-end.

    Returns:
      - immobilisations_brutes: sum of all asset value_total (incl. land if setup exists)
      - amortissements_cumules: sum of cumulative amortizations up to year
      - valeur_nette_comptable: brut - cumulé
      - emprunts: remaining loan balance at year-end
      - resultat_exercice: résultat comptable (2033-B 310) of the property
      - capital_individuel: net equity minus current result (ligne 120)
      - total_capitaux_propres: valeur_nette_comptable - emprunts (balance sheet equity)
      - cout_revient_acquisitions: gross value of assets acquired during the year
    """
    from property.models import AmortizationAsset, PropertyLoan

    assets = AmortizationAsset.objects.filter(property_id=property_id)
    brut = sum((a.value_total.amount for a in assets), Decimal(0))

    # Land is included as an AmortizationAsset (cerfa_category="terrains").

    cumul = sum((a.cumulative_amortization(year) for a in assets), Decimal(0))

    year_end = datetime.date(year, 12, 31)
    loans = PropertyLoan.objects.filter(property_id=property_id)
    emprunts = sum(
        (loan.remaining_balance(year_end).amount for loan in loans), Decimal(0)
    )

    summary = get_property_year_lines(property_id, year, list(assets))

    # On the 2033-A balance sheet the Passif must equal the Actif net.
    # Actif net = immobilisations brutes − amortissements cumulés = brut − cumul
    # Passif = Capitaux propres (I) + Dettes (II)
    # => Capitaux propres = Actif net − Dettes = (brut − cumul) − emprunts
    # Capital individuel (ligne 120) = Total capitaux propres − Résultat exercice
    # Résultat de l'exercice on the bilan = résultat COMPTABLE (cerfa_310), not fiscal result.
    valeur_nette = brut - cumul
    total_capitaux_propres = valeur_nette - emprunts
    resultat_comptable = summary["cerfa_310"]
    capital_individuel = total_capitaux_propres - resultat_comptable

    # Cost of assets acquired during this year (2033-A-182)
    cout_revient_acquisitions = sum(
        (
            a.value_total.amount
            for a in assets
            if a.beginning_date and a.beginning_date.year == year
        ),
        Decimal(0),
    )

    return {
        "immobilisations_brutes": brut,
        "amortissements_cumules": cumul,
        "valeur_nette_comptable": brut - cumul,
        "emprunts": emprunts,
        "resultat_exercice": resultat_comptable,  # 2033-A ligne 136: résultat COMPTABLE
        "capital_individuel": capital_individuel,
        "total_capitaux_propres": total_capitaux_propres,
        "cout_revient_acquisitions": cout_revient_acquisitions,
        "charges_constatees_avance": Decimal(0),  # actif circulant ligne 092
    }


def get_immobilisation_movements(property_id: int, year: int) -> dict:
    """
    Return 2033-C immobilisation movements for a property.

    Returns a dict with:
      - rows: per-asset movements
      - by_cerfa_category: aggregated by cerfa category (terrains/constructions/
            installations/autres) with keys: value_start, acquisitions, value_end,
            amort_start, dotation, amort_end
      - terrains_value: land value from terrain AmortizationAsset (0 if absent)
    Each row:
      - label, cerfa_category, value_start, acquisitions, value_end,
        amort_start, dotation, amort_end, asset_pk
    """
    from property.models import AmortizationAsset

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
                "value_start": value_total if acq_year < year else Decimal(0),
                "acquisitions": value_total if acq_year == year else Decimal(0),
                "value_end": value_total,
                "amort_start": amort_start,
                "dotation": dotation,
                "amort_end": amort_end,
                "asset_pk": asset.pk,
            }
        )

    # Aggregate by cerfa category
    _zero: Decimal = Decimal(0)
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
        cat: str = (
            str(row["cerfa_category"])
            if row["cerfa_category"] in categories
            else "autres"
        )
        by_cerfa[cat]["value_start"] += row["value_start"]
        by_cerfa[cat]["acquisitions"] += row["acquisitions"]
        by_cerfa[cat]["value_end"] += row["value_end"]
        by_cerfa[cat]["amort_start"] += row["amort_start"]
        by_cerfa[cat]["dotation"] += row["dotation"]
        by_cerfa[cat]["amort_end"] += row["amort_end"]

    # Land (terrains) value comes directly from the terrain AmortizationAsset.
    # No setup-based override — the asset row already populates by_cerfa["terrains"].
    terrains_value = by_cerfa["terrains"]["value_end"]

    # Compute totals across all categories (cerfa lines 490 / 570)
    _zero = Decimal(0)
    totals = {
        "value_start": sum(r["value_start"] for r in by_cerfa.values()),
        "acquisitions": sum(r["acquisitions"] for r in by_cerfa.values()),
        "diminutions": _zero,  # asset disposals not tracked yet
        "value_end": sum(r["value_end"] for r in by_cerfa.values()),
        "amort_start": sum(r["amort_start"] for r in by_cerfa.values()),
        "dotation": sum(r["dotation"] for r in by_cerfa.values()),
        "amort_end": sum(r["amort_end"] for r in by_cerfa.values()),
    }
    # Also add diminutions=0 to each category row for template consistency
    for cat_row in by_cerfa.values():
        cat_row.setdefault("diminutions", _zero)

    return {
        "rows": rows,
        "by_cerfa_category": by_cerfa,
        "terrains_value": terrains_value,
        "totals": totals,
    }


def get_accounting_data(properties: list, year: int) -> dict:
    """
    Aggregate the full LMNP liasse fiscale for a list of properties.

    Returns a dict with one key per cerfa form:
      - form_2033b: compte de résultat (activity totals + per-property lines)
      - form_2033a: bilan simplifié
      - form_2033c: immobilisations et amortissements
      - form_2031: résultat BIC (2031 / 2031-bis)
      - form_suiv39c: deferred amortization, one row per fiscal year
      - form_2042c: 2042-C PRO boxes 5NA / 5NY / 5CD / 5GA…5GJ
      - years: every ``LmnpYearResult`` of the activity as dicts (oldest first)
    """
    from property.models import AmortizationAsset

    years = compute_activity(properties, year)
    current = compute_activity_year(properties, year) if not years else years[-1]

    assets_by_property: dict[int, list] = {p.pk: [] for p in properties}
    for asset in AmortizationAsset.objects.filter(property_id__in=assets_by_property):
        assets_by_property[asset.property_id].append(asset)  # ty: ignore[unresolved-attribute]

    per_prop_summaries = [
        {
            "property": prop,
            "summary": get_property_year_lines(
                prop.pk, year, assets_by_property[prop.pk]
            ),
        }
        for prop in properties
    ]
    agg_by_line: dict[str, Decimal] = {}
    for item in per_prop_summaries:
        for line, amount in item["summary"]["by_line"].items():
            agg_by_line[line] = agg_by_line.get(line, ZERO) + amount

    # ── 2033-B ────────────────────────────────────────────────────────────────
    form_2033b = {
        "recettes": current.revenue_218 + current.other_income_209,
        "production_vendue_218": current.revenue_218,
        "autres_produits_209": current.other_income_209,
        "autres_charges_externes": current.external_charges_242,
        "impots_taxes": current.taxes_244,
        "cfe": current.cfe_243,
        "amortization_total": current.depreciation_254,
        "resultat_exploitation_270": current.operating_result_270,
        "charges_financieres": current.financial_charges_294,
        "cerfa_310": current.accounting_result_310,
        "plafond_39c": current.depreciation_cap_39c,
        "amortization_deductible": current.depreciation_deducted,
        "cerfa_318": current.depreciation_reintegrated_318,
        "amortization_deferred": current.depreciation_reintegrated_318,
        "deferred_prior": current.deferred_depreciation_start,
        "cerfa_350": current.deferred_depreciation_used_350,
        "deferred_balance": current.deferred_depreciation_end,
        "cerfa_352": current.fiscal_result_352,
        "taxable_result": current.fiscal_result_352,
        "deficits_anterieurs": sum(current.prior_deficits_start.values(), ZERO),
        "cerfa_360": current.prior_deficits_used_360,
        "cerfa_370": current.fiscal_result_370,
        "by_line": agg_by_line,
        "per_prop": per_prop_summaries,
    }

    # ── 2033-A ────────────────────────────────────────────────────────────────
    per_prop_bilan = [
        {"property": prop, "bilan": get_bilan_data(prop.pk, year)}
        for prop in properties
    ]
    bilan_keys = (
        "immobilisations_brutes",
        "amortissements_cumules",
        "emprunts",
        "capital_individuel",
        "total_capitaux_propres",
        "cout_revient_acquisitions",
    )
    form_2033a = {
        key: sum((item["bilan"][key] for item in per_prop_bilan), ZERO)
        for key in bilan_keys
    }
    form_2033a["valeur_nette_comptable"] = (
        form_2033a["immobilisations_brutes"] - form_2033a["amortissements_cumules"]
    )
    form_2033a["resultat_exercice"] = current.accounting_result_310  # ligne 136
    form_2033a["charges_constatees_avance"] = ZERO  # ligne 092
    form_2033a["per_prop"] = per_prop_bilan

    # ── 2033-C ────────────────────────────────────────────────────────────────
    movement_keys = (
        "value_start",
        "acquisitions",
        "diminutions",
        "value_end",
        "amort_start",
        "dotation",
        "amort_end",
    )
    categories_c = ("terrains", "constructions", "installations", "autres")
    per_prop_immobilisations = [
        {"property": prop, "movements": get_immobilisation_movements(prop.pk, year)}
        for prop in properties
    ]
    agg_by_cerfa = {
        cat: {
            key: sum(
                (
                    item["movements"]["by_cerfa_category"][cat].get(key, ZERO)
                    for item in per_prop_immobilisations
                ),
                ZERO,
            )
            for key in movement_keys
        }
        for cat in categories_c
    }
    form_2033c = {
        "per_prop": per_prop_immobilisations,
        "by_cerfa_category": agg_by_cerfa,
        "totals": {
            key: sum((row[key] for row in agg_by_cerfa.values()), ZERO)
            for key in movement_keys
        },
    }

    # ── 2031 / 2031-bis ───────────────────────────────────────────────────────
    form_2031 = {
        "resultat_fiscal_352": current.fiscal_result_352,
        "resultat_fiscal_370": current.fiscal_result_370,
        "benefice": current.case_5na,
        "deficit": current.case_5ny,
    }

    # ── SUIV39C ───────────────────────────────────────────────────────────────
    form_suiv39c = {
        "rows": [
            {
                "year": r.year,
                "deferred_start": r.deferred_depreciation_start,
                "dotation": r.depreciation_254,
                "deducted": r.depreciation_deducted,
                "reintegrated_318": r.depreciation_reintegrated_318,
                "used_350": r.deferred_depreciation_used_350,
                "deferred_end": r.deferred_depreciation_end,
            }
            for r in years
        ],
        "deferred_end": current.deferred_depreciation_end,
    }

    # ── 2042-C PRO ────────────────────────────────────────────────────────────
    form_2042c = {
        "case_5na": current.case_5na,
        "case_5ny": current.case_5ny,
        "case_5cd": current.case_5cd,
        "deficit_carryforward": current.deficit_carryforward,
        "deficit_history": dict(current.deficits_end),
        "deficit_cases_list": [
            {"label": box, "origin_year": origin, "amount": amount}
            for box, origin, amount in current.deficit_cases
        ],
        "is_benefice": current.is_profit,
    }

    return {
        "form_2033b": form_2033b,
        "form_2033a": form_2033a,
        "form_2033c": form_2033c,
        "form_2031": form_2031,
        "form_suiv39c": form_suiv39c,
        "form_2042c": form_2042c,
        "years": [r.as_dict() for r in years],
    }


# ─── Checklist categories (derived from ManagementCategory metadata) ──────────
#
# These frozensets are derived entirely from the ManagementCategory enum so they
# stay in sync automatically when categories are added or reclassified.
#
# Note: loan_insurance has lmnp_line="242" (exploitation charge per CERFA 2033-B)
# but is grouped with financial charges in the checklist for UX clarity.

_CHECKLIST_RECETTES = frozenset(
    c.value for c in ManagementCategory if c.lmnp_section == "recettes"
)
_CHECKLIST_CHARGES_EXPLOIT = frozenset(
    c.value
    for c in ManagementCategory
    if c.lmnp_section == "charges"
    and c.lmnp_line == "242"
    and c != ManagementCategory.LOAN_INSURANCE
)
_CHECKLIST_TAXES = frozenset(
    c.value
    for c in ManagementCategory
    if c.lmnp_section == "charges" and c.lmnp_line == "244"
)
_CHECKLIST_FINANCIERES = frozenset(
    c.value
    for c in ManagementCategory
    if c.lmnp_line == "294" or c == ManagementCategory.LOAN_INSURANCE
)


def _count_entries_in_year(property_id: int, year: int, categories: frozenset) -> int:
    """Count ledger entries (recurring or not) that have amounts in ``year``."""
    from property.models import PropertyLedgerEntry

    year_start = datetime.date(year, 1, 1)
    year_end = datetime.date(year, 12, 31)

    non_recurring_q = Q(
        recurrence_type=PropertyLedgerEntry.RecurrenceType.NONE,
        entry_date__gte=year_start,
        entry_date__lte=year_end,
    )
    recurring_q = (
        ~Q(recurrence_type=PropertyLedgerEntry.RecurrenceType.NONE)
        & Q(entry_date__lte=year_end)
        & (Q(recurrence_end_date__gte=year_start) | Q(recurrence_end_date__isnull=True))
    )

    return (
        PropertyLedgerEntry.objects.filter(
            property_id=property_id,
            management_category__in=list(categories),
            amount_currency="EUR",
        )
        .filter(non_recurring_q | recurring_q)
        .count()
    )


def get_lmnp_checklist(properties: list, year: int) -> dict:
    """
    Return a data completeness checklist for LMNP réel properties.

    For each property, runs a series of checks on required data for the
    LMNP fiscal declaration (liasse fiscale 2031 + 2033-A/B/C/D + SUIV39C).

    Each check has a status:
      - "ok"      : data is present and complete
      - "warning" : data may be absent but not strictly required (e.g. taxe foncière)
      - "missing"  : required data is absent
      - "na"      : not applicable (e.g. no loan → financial charges not required)

    Returns a dict with:
      - "properties": per-property check results
      - "forms": readiness summary per LMNP form
      - "total_issues": total count of warning + missing checks across all properties
      - "overall_status": "ok" | "warning" | "incomplete"
    """
    from property.models import AmortizationAsset, AmortizationSetup, PropertyLoan

    def _check(
        check_id: str,
        label: str | Promise,
        count: int,
        form_ref: str,
        required: bool = True,
        loan_active: bool | None = None,
    ) -> dict:
        """Build a single check result dict."""
        if check_id == "financial_charges":
            if loan_active is False:
                status = "na"
                detail = _("No active loan — not required.")
            elif count > 0:
                status = "ok"
                detail = _("%(count)d entry(ies) found.") % {"count": count}
            else:
                status = "warning"
                detail = _("Loan detected but no financial charge entries found.")
        elif count > 0:
            status = "ok"
            detail = _("%(count)d entry(ies) found.") % {"count": count}
        elif required:
            status = "missing"
            detail = _("No entry found — required for %(form)s.") % {"form": form_ref}
        else:
            status = "warning"
            detail = _("No entry found — recommended for %(form)s.") % {
                "form": form_ref
            }
        return {
            "id": check_id,
            "label": label,
            "status": status,
            "detail": detail,
            "count": count,
            "form_ref": form_ref,
        }

    prop_results: list[dict] = []
    all_checks: list[list[dict]] = []

    for prop in properties:
        year_start = datetime.date(year, 1, 1)
        year_end = datetime.date(year, 12, 31)

        # --- Revenues ---
        revenue_count = _count_entries_in_year(prop.pk, year, _CHECKLIST_RECETTES)

        # --- Operating charges ---
        charges_count = _count_entries_in_year(
            prop.pk, year, _CHECKLIST_CHARGES_EXPLOIT
        )

        # --- Taxes (taxe foncière / CFE) ---
        taxes_count = _count_entries_in_year(prop.pk, year, _CHECKLIST_TAXES)

        # --- Financial charges (only required if a loan is active this year) ---
        active_loans = list(
            PropertyLoan.objects.filter(
                property_id=prop.pk,
                start_date__lte=year_end,
                end_date__gte=year_start,
            )
        )
        has_active_loan = bool(active_loans)
        fin_count = _count_entries_in_year(prop.pk, year, _CHECKLIST_FINANCIERES)

        # --- Amortization setup ---
        has_setup = AmortizationSetup.objects.filter(property=prop).exists()

        # --- Amortization components ---
        asset_count = AmortizationAsset.objects.filter(property=prop).count()

        # --- Terrain asset (required for 2033-C) ---
        has_terrain_asset = AmortizationAsset.objects.filter(
            property=prop,
            cerfa_category=AmortizationAsset.CerfaCategory.TERRAINS,
        ).exists()

        # --- Acquisition value ---
        has_buying_value = (
            prop.buying_value is not None and prop.buying_value.amount > Decimal(0)
        )

        checks = [
            _check(
                "revenues",
                _("Revenue entries"),
                revenue_count,
                "2033-B",
                required=True,
            ),
            _check(
                "charges",
                _("Operating charge entries"),
                charges_count,
                "2033-B",
                required=False,
            ),
            _check(
                "taxes",
                _("Property tax / CFE entries"),
                taxes_count,
                "2033-B",
                required=False,
            ),
            _check(
                "financial_charges",
                _("Financial charge entries"),
                fin_count,
                "2033-B",
                loan_active=has_active_loan,
            ),
            {
                "id": "amortization_setup",
                "label": _("Amortization initialized"),
                "status": "ok" if has_setup else "missing",
                "detail": (
                    _("Amortization setup found.")
                    if has_setup
                    else _("No amortization setup — required for 2033-A and 2033-C.")
                ),
                "count": 1 if has_setup else 0,
                "form_ref": "2033-A / 2033-C",
            },
            {
                "id": "amortization_components",
                "label": _("Amortization components"),
                "status": (
                    "ok" if asset_count > 0 else ("warning" if has_setup else "missing")
                ),
                "detail": (
                    _("%(count)d component(s) found.") % {"count": asset_count}
                    if asset_count > 0
                    else (
                        _("Setup exists but no components — check initialization.")
                        if has_setup
                        else _("No components — initialize amortization first.")
                    )
                ),
                "count": asset_count,
                "form_ref": "2033-C",
            },
            {
                "id": "buying_value",
                "label": _("Acquisition value set"),
                "status": "ok" if has_buying_value else "missing",
                "detail": (
                    _("Buying value is set.")
                    if has_buying_value
                    else _("No buying value — required for 2033-A (bilan actif).")
                ),
                "count": 1 if has_buying_value else 0,
                "form_ref": "2033-A",
            },
            {
                "id": "terrain_asset",
                "label": _("Land component (terrain)"),
                "status": "ok" if has_terrain_asset else "missing",
                "detail": (
                    _("Land asset found.")
                    if has_terrain_asset
                    else _(
                        "No land (terrain) component — required for 2033-C. "
                        "Add an amortization asset with category 'terrains'."
                    )
                ),
                "count": 1 if has_terrain_asset else 0,
                "form_ref": "2033-C",
            },
        ]

        issue_count = sum(1 for c in checks if c["status"] in ("warning", "missing"))
        prop_results.append(
            {
                "property": prop,
                "checks": checks,
                "has_issues": issue_count > 0,
                "issue_count": issue_count,
            }
        )
        all_checks.append(checks)

    # ── Derive per-form readiness ─────────────────────────────────────────────
    def _form_status(check_ids: list[str]) -> str:
        """Return 'ok'/'warning'/'incomplete' based on matching checks across all props."""
        worst = "ok"
        for prop_checks in all_checks:
            for chk in prop_checks:
                if chk["id"] in check_ids:
                    if chk["status"] == "missing":
                        return "incomplete"
                    if chk["status"] == "warning":
                        worst = "warning"
        return worst

    forms = [
        {
            "id": "2031",
            "name": "2031-SD",
            "label": _("Déclaration de résultat BIC"),
            "status": _form_status(["revenues"]),
            "required": True,
        },
        {
            "id": "2033a",
            "name": "2033-A",
            "label": _("Bilan simplifié"),
            "status": _form_status(["buying_value", "amortization_setup"]),
            "required": True,
        },
        {
            "id": "2033b",
            "name": "2033-B",
            "label": _("Compte de résultat"),
            "status": _form_status(
                ["revenues", "charges", "taxes", "financial_charges"]
            ),
            "required": True,
        },
        {
            "id": "2033c",
            "name": "2033-C",
            "label": _("Immobilisations & amortissements"),
            "status": _form_status(
                ["amortization_setup", "amortization_components", "terrain_asset"]
            ),
            "required": True,
        },
        {
            "id": "2033d",
            "name": "2033-D",
            "label": _("Déficits reportables"),
            "status": "auto",
            "required": True,
        },
        {
            "id": "suiv39c",
            "name": "SUIV39C",
            "label": _("Amortissements différés art. 39C"),
            "status": _form_status(["amortization_setup"]),
            "required": True,
        },
        {
            "id": "2042c",
            "name": "2042-C PRO",
            "label": _("Déclaration complémentaire"),
            "status": _form_status(["revenues"]),
            "required": True,
        },
        {
            "id": "2033e",
            "name": "2033-E",
            "label": _("Valeur ajoutée (CVAE)"),
            "status": "na",
            "required": False,
        },
        {
            "id": "2033f",
            "name": "2033-F",
            "label": _("Composition du capital"),
            "status": "na",
            "required": False,
        },
        {
            "id": "2033g",
            "name": "2033-G",
            "label": _("Filiales et participations"),
            "status": "na",
            "required": False,
        },
    ]

    total_issues = sum(p["issue_count"] for p in prop_results)

    has_incomplete = any(
        f["status"] == "incomplete"
        for f in forms
        if f["required"] and f["status"] != "auto"
    )
    has_warning = any(
        f["status"] == "warning"
        for f in forms
        if f["required"] and f["status"] != "auto"
    )

    if has_incomplete:
        overall_status = "incomplete"
    elif has_warning:
        overall_status = "warning"
    else:
        overall_status = "ok"

    return {
        "properties": prop_results,
        "forms": forms,
        "total_issues": total_issues,
        "overall_status": overall_status,
    }
