"""Estimate of the capital gain tax when selling a property (plus-value des particuliers).

Rules (art. 150 U to 150 VH and 1609 nonies G CGI):

- gain = net sale price − (purchase price + acquisition fees + works);
- acquisition fees: the actual fees (notary, agency paid by the buyer) or a
  flat 7.5 % of the purchase price, whichever is higher;
- works: the actual works not already deducted, or a flat 15 % of the
  purchase price after five years of holding, whichever is higher;
- finance act 2025 (sales since 15 February 2025): the amortization deducted
  under the LMNP régime réel lowers the purchase price, except for student,
  senior and care residences;
- allowances for the holding period: income tax (19 %) 6 % per year from the
  6th to the 21st year and 4 % the 22nd (exempt after 22 years); social
  charges (17.2 %) 1.65 % per year from the 6th to the 21st year, 1.60 % the
  22nd and 9 % per year from the 23rd (exempt after 30 years);
- surtax from 2 % to 6 % on a taxable gain (income tax base) above 50,000 €
  per seller, with a smoothing below each threshold;
- the main residence is exempt.

The LMNP amortization is taken from the fiscal years computed from the
ledger, up to the year before the sale, for this property alone.
"""

import datetime
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from dateutil.relativedelta import relativedelta

from property.models import AmortizationAsset, Property

INCOME_TAX_RATE = Decimal("0.19")
SOCIAL_CHARGES_RATE = Decimal("0.172")
FLAT_ACQUISITION_FEES = Decimal("0.075")
FLAT_WORKS = Decimal("0.15")
FLAT_WORKS_MIN_YEARS = 5
#: Components of the building whose deducted amortization is added back
#: (the furniture, "autres immobilisations corporelles", is not).
BUILDING_CATEGORIES = (
    AmortizationAsset.CerfaCategory.CONSTRUCTIONS,
    AmortizationAsset.CerfaCategory.INSTALLATIONS,
)
SURTAX_THRESHOLD = Decimal(50000)
#: (lower bound, upper bound, rate, smoothing coefficient) of art. 1609 nonies G:
#: within a smoothing band the surtax is rate × gain − coefficient × (upper − gain).
_SURTAX_BANDS = (
    (Decimal(50000), Decimal(60000), Decimal("0.02"), Decimal("0.05")),
    (Decimal(60000), Decimal(100000), Decimal("0.02"), None),
    (Decimal(100000), Decimal(110000), Decimal("0.03"), Decimal("0.10")),
    (Decimal(110000), Decimal(150000), Decimal("0.03"), None),
    (Decimal(150000), Decimal(160000), Decimal("0.04"), Decimal("0.15")),
    (Decimal(160000), Decimal(200000), Decimal("0.04"), None),
    (Decimal(200000), Decimal(210000), Decimal("0.05"), Decimal("0.20")),
    (Decimal(210000), Decimal(250000), Decimal("0.05"), None),
    (Decimal(250000), Decimal(260000), Decimal("0.06"), Decimal("0.25")),
)
_TOP_SURTAX_RATE = Decimal("0.06")
CENT = Decimal("0.01")


def _round(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def income_tax_allowance(years: int) -> Decimal:
    """Allowance on the income tax base, in percent, for *years* of holding."""
    if years < 6:
        return Decimal(0)
    if years <= 21:
        return Decimal(6 * (years - 5))
    return Decimal(100)


def social_charges_allowance(years: int) -> Decimal:
    """Allowance on the social charges base, in percent, for *years* of holding."""
    if years < 6:
        return Decimal(0)
    if years <= 21:
        return Decimal("1.65") * (years - 5)
    if years < 30:
        return Decimal(28) + 9 * (years - 22)
    return Decimal(100)


def surtax(taxable_gain: Decimal) -> Decimal:
    """Surtax of one seller on a taxable gain (income tax base)."""
    if taxable_gain <= SURTAX_THRESHOLD:
        return Decimal(0)
    for low, high, rate, smoothing in _SURTAX_BANDS:
        if low < taxable_gain <= high:
            tax = rate * taxable_gain
            if smoothing is not None:
                tax -= smoothing * (high - taxable_gain)
            return _round(tax)
    return _round(_TOP_SURTAX_RATE * taxable_gain)


def deducted_building_amortization(prop: Property, sale_year: int) -> Decimal:
    """LMNP amortization of the building deducted up to the year before the sale.

    Each year the deducted amortization (the dotation within the art. 39 C cap
    and the deferred amortization used) is split between the building and the
    furniture in proportion of their dotations.
    """
    from property.services.tax_lmnp import compute_activity

    if prop.tax_regime != Property.TaxRegime.LMNP_REEL:
        return Decimal(0)
    assets = list(AmortizationAsset.objects.filter(property=prop))
    total = Decimal(0)
    for result in compute_activity(prop.pk, sale_year - 1):
        dotations = [(a, a.get_annual_amortization(result.year)) for a in assets]
        all_dotations = sum((d for _a, d in dotations), Decimal(0))
        if not all_dotations:
            continue
        building = sum(
            (d for a, d in dotations if a.cerfa_category in BUILDING_CATEGORIES),
            Decimal(0),
        )
        deducted = result.depreciation_deducted + result.deferred_depreciation_used_350
        total += deducted * building / all_dotations
    return _round(total)


@dataclass(frozen=True)
class ResaleInputs:
    """Hypotheses of the sale."""

    sale_price: Decimal
    sale_date: datetime.date
    seller_fees: Decimal = Decimal(0)
    actual_works: Decimal = Decimal(0)
    main_residence: bool = False
    service_residence: bool = False
    #: Shares (in %) of each seller, for the surtax threshold.
    seller_shares: tuple[Decimal, ...] = (Decimal(100),)


@dataclass
class ResaleEstimate:
    """Capital gain and taxes of a simulated sale."""

    inputs: ResaleInputs
    purchase_price: Decimal
    actual_fees: Decimal
    acquisition_fees: Decimal
    flat_fees_used: bool
    works: Decimal
    flat_works_used: bool
    lmnp_reintegration: Decimal
    holding_years: int
    remaining_loans: Decimal
    gross_gain: Decimal = Decimal(0)
    income_tax_allowance: Decimal = Decimal(0)
    social_charges_allowance: Decimal = Decimal(0)
    taxable_income_tax: Decimal = Decimal(0)
    taxable_social_charges: Decimal = Decimal(0)
    income_tax: Decimal = Decimal(0)
    social_charges: Decimal = Decimal(0)
    surtax: Decimal = Decimal(0)
    surtax_by_seller: list[Decimal] = field(default_factory=list)

    @property
    def net_sale_price(self) -> Decimal:
        """Sale price minus the fees paid by the seller."""
        return self.inputs.sale_price - self.inputs.seller_fees

    @property
    def adjusted_cost(self) -> Decimal:
        """Purchase price increased by the fees and works, minus the LMNP reintegration."""
        return (
            self.purchase_price
            + self.acquisition_fees
            + self.works
            - self.lmnp_reintegration
        )

    @property
    def total_tax(self) -> Decimal:
        """Income tax, social charges and surtax."""
        return self.income_tax + self.social_charges + self.surtax

    @property
    def net_proceeds(self) -> Decimal:
        """Cash left after the taxes and the repayment of the loans."""
        return self.net_sale_price - self.total_tax - self.remaining_loans

    @property
    def is_exempt(self) -> bool:
        """True when no tax is due whatever the gain."""
        return self.inputs.main_residence


def _money_amount(value) -> Decimal:
    if value is None:
        return Decimal(0)
    return Decimal(getattr(value, "amount", value))


def estimate_resale(prop: Property, inputs: ResaleInputs) -> ResaleEstimate:
    """Capital gain tax of selling *prop* with the given hypotheses."""
    purchase_price = _money_amount(prop.buying_value)
    actual_fees = _money_amount(prop.notary_fees) + _money_amount(prop.agency_fees)
    flat_fees = _round(purchase_price * FLAT_ACQUISITION_FEES)
    holding_years = relativedelta(inputs.sale_date, prop.buying_date).years
    flat_works = (
        _round(purchase_price * FLAT_WORKS)
        if holding_years > FLAT_WORKS_MIN_YEARS
        else Decimal(0)
    )
    reintegration = (
        Decimal(0)
        if inputs.service_residence or inputs.main_residence
        else deducted_building_amortization(prop, inputs.sale_date.year)
    )
    estimate = ResaleEstimate(
        inputs=inputs,
        purchase_price=purchase_price,
        actual_fees=actual_fees,
        acquisition_fees=max(actual_fees, flat_fees),
        flat_fees_used=flat_fees > actual_fees,
        works=max(inputs.actual_works, flat_works),
        flat_works_used=flat_works > inputs.actual_works,
        lmnp_reintegration=reintegration,
        holding_years=holding_years,
        remaining_loans=prop.total_remaining_loans_at_date(inputs.sale_date).amount,
    )
    estimate.gross_gain = estimate.net_sale_price - estimate.adjusted_cost
    if estimate.is_exempt or estimate.gross_gain <= 0:
        return estimate

    estimate.income_tax_allowance = income_tax_allowance(holding_years)
    estimate.social_charges_allowance = social_charges_allowance(holding_years)
    estimate.taxable_income_tax = _round(
        estimate.gross_gain * (100 - estimate.income_tax_allowance) / 100
    )
    estimate.taxable_social_charges = _round(
        estimate.gross_gain * (100 - estimate.social_charges_allowance) / 100
    )
    estimate.income_tax = _round(estimate.taxable_income_tax * INCOME_TAX_RATE)
    estimate.social_charges = _round(
        estimate.taxable_social_charges * SOCIAL_CHARGES_RATE
    )
    estimate.surtax_by_seller = [
        surtax(estimate.taxable_income_tax * share / 100)
        for share in inputs.seller_shares
    ]
    estimate.surtax = sum(estimate.surtax_by_seller, Decimal(0))
    return estimate
