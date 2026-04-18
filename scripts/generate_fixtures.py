#!/usr/bin/env python3
"""Generate test fixtures with dates relative to today.

The newest data points are 5 days ago, and earlier points are spaced
approximately 1 month apart going back, ensuring progression graphs
always show relevant recent data on each database reset.
"""

import calendar
import datetime
import os

TODAY = datetime.date.today()
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
FIXTURES_DIR = os.path.join(PROJECT_DIR, "tests", "fixtures")


# === Date helpers ===


def months_ago(n: int, ref: datetime.date | None = None) -> datetime.date:
    """Return a date n months before the reference date (default: today)."""
    ref = ref or TODAY
    total_months = ref.year * 12 + ref.month - 1 - n
    year = total_months // 12
    month = total_months % 12 + 1
    max_day = calendar.monthrange(year, month)[1]
    day = min(ref.day, max_day)
    return datetime.date(year, month, day)


def days_ago(n: int) -> datetime.date:
    """Return a date n days before today."""
    return TODAY - datetime.timedelta(days=n)


def years_ahead(n: int, ref: datetime.date) -> datetime.date:
    """Return a date n years after the reference date."""
    try:
        return ref.replace(year=ref.year + n)
    except ValueError:
        return ref.replace(year=ref.year + n, day=28)


def dt(d: datetime.date) -> str:
    """Format as YAML datetime string."""
    return f"{d} 00:00:00.000000"


def ds(d: datetime.date) -> str:
    """Format as YAML date string."""
    return str(d)


def write_fixture(filename: str, content: str) -> None:
    """Write a fixture YAML file."""
    path = os.path.join(FIXTURES_DIR, filename)
    with open(path, "w") as f:
        f.write(content)
    print(f"  Generated {os.path.relpath(path, PROJECT_DIR)}")


# === Anchor dates ===
RECENT = days_ago(5)  # Most recent data point
M1 = months_ago(1)
M3 = months_ago(3)
M5 = months_ago(5)
M6 = months_ago(6)
M7 = months_ago(7)
M8 = months_ago(8)
M9 = months_ago(9)
M10 = months_ago(10)
M11 = months_ago(11)
M12 = months_ago(12)
M15 = months_ago(15)
M18 = months_ago(18)
M24 = months_ago(24)
M25 = months_ago(25)
M28 = months_ago(28)
M30 = months_ago(30)
M36 = months_ago(36)
M48 = months_ago(48)
M60 = months_ago(60)
M72 = months_ago(72)
M84 = months_ago(84)
M96 = months_ago(96)

# Property loan end dates
LOAN1_END = years_ahead(20, M96)  # Property 1 — 20-year loan started 8 years ago
LOAN2A_END = years_ahead(
    10, M48
)  # Property 2 — smoothed 10-year loan started 4 years ago
LOAN2B_END = years_ahead(
    20, M48
)  # Property 2 — smoothed 20-year loan started 4 years ago
LOAN3_END = years_ahead(
    8, M48
)  # Property 3 — 8-year loan started 4 years ago (ends in ~4y)


# === Fixture generators ===


def generate_investmentaccount() -> str:
    """Generate investmentaccount.yaml with dynamic dates."""
    return f"""# generated with scripts/generate_fixtures.py
---
- model: finance.investmentaccount
  pk: 1
  fields:
    created_at: {dt(M30)}
    updated_at: {dt(RECENT)}
    account_type_id: 1
    owner: Commun
    institution: Bourse Direct
    is_active: true
    opening_date: {ds(M30)}
    opening_cash_value: 0
    opening_cash_value_currency: EUR
- model: finance.investmentaccountholding
  pk: 1
  fields:
    created_at: {dt(M30)}
    updated_at: {dt(RECENT)}
    account_id: 1
    name: MSCI World
    code: DCAM
    is_active: true
    initial_quantity: 10
    initial_value: 3401
    initial_value_currency: EUR
    initial_valuation_date: {ds(M30)}
- model: finance.investmentaccountholdinghistory
  pk: 1
  fields:
    created_at: {dt(M28)}
    updated_at: {dt(M28)}
    holding_id: 1
    value: 3450
    value_currency: EUR
    quantity: 10
    valuation_date: {ds(M28)}
- model: finance.investmentaccountholdinghistory
  pk: 2
  fields:
    created_at: {dt(M25)}
    updated_at: {dt(M25)}
    holding_id: 1
    value: 3500
    value_currency: EUR
    quantity: 10
    valuation_date: {ds(M25)}
- model: finance.investmentaccountholding
  pk: 2
  fields:
    created_at: {dt(M30)}
    updated_at: {dt(RECENT)}
    account_id: 1
    name: CAC40
    code: CAC
    is_active: true
    initial_quantity: 5
    initial_value: 3500
    initial_value_currency: EUR
    initial_valuation_date: {ds(M30)}
- model: finance.investmentaccountholdinghistory
  pk: 3
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    holding_id: 2
    value: 3500
    value_currency: EUR
    quantity: 5
    valuation_date: {ds(M12)}
- model: finance.investmentaccountholdinghistory
  pk: 4
  fields:
    created_at: {dt(M11)}
    updated_at: {dt(M11)}
    holding_id: 2
    value: 3400
    value_currency: EUR
    quantity: 5
    valuation_date: {ds(M11)}
- model: finance.investmentaccountholdinghistory
  pk: 5
  fields:
    created_at: {dt(M10)}
    updated_at: {dt(M10)}
    holding_id: 2
    value: 3450
    value_currency: EUR
    quantity: 5
    valuation_date: {ds(M10)}
- model: finance.investmentaccountholdinghistory
  pk: 6
  fields:
    created_at: {dt(M9)}
    updated_at: {dt(M9)}
    holding_id: 2
    value: 3550
    value_currency: EUR
    quantity: 5
    valuation_date: {ds(M9)}
- model: finance.investmentaccountholdinghistory
  pk: 7
  fields:
    created_at: {dt(M8)}
    updated_at: {dt(M8)}
    holding_id: 2
    value: 3600
    value_currency: EUR
    quantity: 5
    valuation_date: {ds(M8)}
- model: finance.investmentaccountholdinghistory
  pk: 8
  fields:
    created_at: {dt(M7)}
    updated_at: {dt(M7)}
    holding_id: 2
    value: 3550
    value_currency: EUR
    quantity: 5
    valuation_date: {ds(M7)}
- model: finance.investmentaccountholdinghistory
  pk: 9
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    holding_id: 2
    value: 3500
    value_currency: EUR
    quantity: 5
    valuation_date: {ds(M6)}
- model: finance.investmentaccountholdinghistory
  pk: 10
  fields:
    created_at: {dt(M5)}
    updated_at: {dt(M5)}
    holding_id: 2
    value: 3650
    value_currency: EUR
    quantity: 5
    valuation_date: {ds(M5)}
- model: finance.investmentaccountholdinghistory
  pk: 11
  fields:
    created_at: {dt(M3)}
    updated_at: {dt(M3)}
    holding_id: 2
    value: 3700
    value_currency: EUR
    quantity: 5
    valuation_date: {ds(M3)}
- model: finance.investmentaccountholdinghistory
  pk: 12
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    holding_id: 2
    value: 3650
    value_currency: EUR
    quantity: 5
    valuation_date: {ds(RECENT)}
- model: finance.investmentaccount
  pk: 2
  fields:
    created_at: {dt(M30)}
    updated_at: {dt(RECENT)}
    account_type_id: 3
    owner: Commun
    institution: Bourse Direct
    is_active: true
    opening_date: {ds(M30)}
    opening_cash_value: 0
    opening_cash_value_currency: EUR
- model: finance.investmentaccountholding
  pk: 3
  fields:
    created_at: {dt(M30)}
    updated_at: {dt(RECENT)}
    account_id: 2
    name: Apple
    code: AAPL
    is_active: true
    initial_quantity: 3
    initial_value: 500
    initial_value_currency: USD
    initial_valuation_date: {ds(M30)}
- model: finance.investmentaccountholding
  pk: 4
  fields:
    created_at: {dt(M30)}
    updated_at: {dt(RECENT)}
    account_id: 2
    name: Nvidia
    code: NVDA
    is_active: true
    initial_quantity: 2
    initial_value: 700
    initial_value_currency: USD
    initial_valuation_date: {ds(M30)}
- model: finance.investmentaccountholdinghistory
  pk: 13
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    holding_id: 3
    value: 500
    value_currency: USD
    quantity: 3
    valuation_date: {ds(M12)}
- model: finance.investmentaccountholdinghistory
  pk: 14
  fields:
    created_at: {dt(M11)}
    updated_at: {dt(M11)}
    holding_id: 3
    value: 520
    value_currency: USD
    quantity: 3
    valuation_date: {ds(M11)}
- model: finance.investmentaccountholdinghistory
  pk: 15
  fields:
    created_at: {dt(M10)}
    updated_at: {dt(M10)}
    holding_id: 3
    value: 510
    value_currency: USD
    quantity: 3
    valuation_date: {ds(M10)}
- model: finance.investmentaccountholdinghistory
  pk: 16
  fields:
    created_at: {dt(M9)}
    updated_at: {dt(M9)}
    holding_id: 3
    value: 530
    value_currency: USD
    quantity: 3
    valuation_date: {ds(M9)}
- model: finance.investmentaccountholdinghistory
  pk: 17
  fields:
    created_at: {dt(M8)}
    updated_at: {dt(M8)}
    holding_id: 3
    value: 540
    value_currency: USD
    quantity: 3
    valuation_date: {ds(M8)}
- model: finance.investmentaccountholdinghistory
  pk: 18
  fields:
    created_at: {dt(M7)}
    updated_at: {dt(M7)}
    holding_id: 3
    value: 530
    value_currency: USD
    quantity: 3
    valuation_date: {ds(M7)}
- model: finance.investmentaccountholdinghistory
  pk: 19
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    holding_id: 3
    value: 525
    value_currency: USD
    quantity: 3
    valuation_date: {ds(M6)}
- model: finance.investmentaccountholdinghistory
  pk: 20
  fields:
    created_at: {dt(M5)}
    updated_at: {dt(M5)}
    holding_id: 3
    value: 550
    value_currency: USD
    quantity: 3
    valuation_date: {ds(M5)}
- model: finance.investmentaccountholdinghistory
  pk: 21
  fields:
    created_at: {dt(M3)}
    updated_at: {dt(M3)}
    holding_id: 3
    value: 560
    value_currency: USD
    quantity: 3
    valuation_date: {ds(M3)}
- model: finance.investmentaccountholdinghistory
  pk: 22
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    holding_id: 3
    value: 555
    value_currency: USD
    quantity: 3
    valuation_date: {ds(RECENT)}
- model: finance.investmentaccountholdinghistory
  pk: 23
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    holding_id: 4
    value: 700
    value_currency: USD
    quantity: 2
    valuation_date: {ds(M12)}
- model: finance.investmentaccountholdinghistory
  pk: 24
  fields:
    created_at: {dt(M11)}
    updated_at: {dt(M11)}
    holding_id: 4
    value: 720
    value_currency: USD
    quantity: 2
    valuation_date: {ds(M11)}
- model: finance.investmentaccountholdinghistory
  pk: 25
  fields:
    created_at: {dt(M10)}
    updated_at: {dt(M10)}
    holding_id: 4
    value: 710
    value_currency: USD
    quantity: 2
    valuation_date: {ds(M10)}
- model: finance.investmentaccountholdinghistory
  pk: 26
  fields:
    created_at: {dt(M9)}
    updated_at: {dt(M9)}
    holding_id: 4
    value: 730
    value_currency: USD
    quantity: 2
    valuation_date: {ds(M9)}
- model: finance.investmentaccountholdinghistory
  pk: 27
  fields:
    created_at: {dt(M8)}
    updated_at: {dt(M8)}
    holding_id: 4
    value: 740
    value_currency: USD
    quantity: 2
    valuation_date: {ds(M8)}
- model: finance.investmentaccountholdinghistory
  pk: 28
  fields:
    created_at: {dt(M7)}
    updated_at: {dt(M7)}
    holding_id: 4
    value: 735
    value_currency: USD
    quantity: 2
    valuation_date: {ds(M7)}
- model: finance.investmentaccountholdinghistory
  pk: 29
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    holding_id: 4
    value: 730
    value_currency: USD
    quantity: 2
    valuation_date: {ds(M6)}
- model: finance.investmentaccountholdinghistory
  pk: 30
  fields:
    created_at: {dt(M5)}
    updated_at: {dt(M5)}
    holding_id: 4
    value: 750
    value_currency: USD
    quantity: 2
    valuation_date: {ds(M5)}
- model: finance.investmentaccountholdinghistory
  pk: 31
  fields:
    created_at: {dt(M3)}
    updated_at: {dt(M3)}
    holding_id: 4
    value: 760
    value_currency: USD
    quantity: 2
    valuation_date: {ds(M3)}
- model: finance.investmentaccountholdinghistory
  pk: 32
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    holding_id: 4
    value: 755
    value_currency: USD
    quantity: 2
    valuation_date: {ds(RECENT)}
"""


def generate_savingaccount() -> str:
    """Generate savingaccount.yaml with dynamic dates."""
    return f"""# generated with scripts/generate_fixtures.py
---
- model: finance.savingaccount
  pk: 1
  fields:
    created_at: {dt(M60)}
    updated_at: {dt(RECENT)}
    account_type_id: 2
    name: Livret A
    owner: Mister
    institution: Credit Agricole
    is_active: true
    opening_date: {ds(M60)}
    opening_value: 10000
    opening_value_currency: EUR
- model: finance.savingaccountvalue
  pk: 1
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    account_id: 1
    value: 10000
    value_currency: EUR
    value_date: {ds(M18)}
- model: finance.savingaccountvalue
  pk: 2
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    account_id: 1
    value: 11000
    value_currency: EUR
    value_date: {ds(RECENT)}
- model: finance.savingaccount
  pk: 2
  fields:
    created_at: {dt(M60)}
    updated_at: {dt(RECENT)}
    account_type_id: 4
    name: LDDS
    owner: Mister
    institution: Credit Agricole
    is_active: true
    opening_date: {ds(M60)}
    opening_value: 12000
    opening_value_currency: EUR
- model: finance.savingaccountvalue
  pk: 3
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    account_id: 2
    value: 12000
    value_currency: EUR
    value_date: {ds(RECENT)}
- model: finance.savingaccount
  pk: 3
  fields:
    created_at: {dt(M60)}
    updated_at: {dt(RECENT)}
    account_type_id: 2
    name: Livret A
    owner: Madame
    institution: BoursoBank
    is_active: true
    opening_date: {ds(M60)}
    opening_value: 22950
    opening_value_currency: EUR
- model: finance.savingaccountvalue
  pk: 4
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    account_id: 3
    value: 22950
    value_currency: EUR
    value_date: {ds(RECENT)}
- model: finance.savingaccountvalue
  pk: 5
  fields:
    created_at: {dt(M15)}
    updated_at: {dt(M15)}
    account_id: 1
    value: 10300
    value_currency: EUR
    value_date: {ds(M15)}
- model: finance.savingaccountvalue
  pk: 6
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    account_id: 1
    value: 10600
    value_currency: EUR
    value_date: {ds(M12)}
- model: finance.savingaccountvalue
  pk: 7
  fields:
    created_at: {dt(M9)}
    updated_at: {dt(M9)}
    account_id: 1
    value: 10900
    value_currency: EUR
    value_date: {ds(M9)}
- model: finance.savingaccountvalue
  pk: 8
  fields:
    created_at: {dt(M15)}
    updated_at: {dt(M15)}
    account_id: 2
    value: 12200
    value_currency: EUR
    value_date: {ds(M15)}
- model: finance.savingaccountvalue
  pk: 9
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    account_id: 2
    value: 12400
    value_currency: EUR
    value_date: {ds(M12)}
- model: finance.savingaccountvalue
  pk: 10
  fields:
    created_at: {dt(M9)}
    updated_at: {dt(M9)}
    account_id: 2
    value: 12600
    value_currency: EUR
    value_date: {ds(M9)}
- model: finance.savingaccountvalue
  pk: 11
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    account_id: 3
    value: 23250
    value_currency: EUR
    value_date: {ds(M12)}
- model: finance.savingaccountvalue
  pk: 12
  fields:
    created_at: {dt(M9)}
    updated_at: {dt(M9)}
    account_id: 3
    value: 23550
    value_currency: EUR
    value_date: {ds(M9)}
- model: finance.savingaccountvalue
  pk: 13
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    account_id: 3
    value: 23850
    value_currency: EUR
    value_date: {ds(M6)}
"""


def generate_property() -> str:  # noqa: PLR0915
    """Generate property.yaml with dynamic dates.

    Properties:
      1 - Résidence principale (HO): 1 standard 20-year loan, typical owner expenses
      2 - Appartement locatif Nice (AP): 2 smoothed loans (prêt lisseur, 10y + 20y),
          active lease, full rental transactions
      3 - Studio meublé Lyon (AP): 1 short loan ending in ~4 years, active lease,
          rental transactions with tenant and lease
      4 - Maison de campagne (HO): no loan, no lease, expenses + punctual Airbnb income
    """
    return f"""# generated with scripts/generate_fixtures.py
---
# ─────────────────────────────────────────────────────────────────────────────
# PROPERTY 1 — Résidence principale (House, bought 8 years ago)
#   Loan: 1 standard 20-year mortgage
# ─────────────────────────────────────────────────────────────────────────────
- model: property.property
  pk: 1
  fields:
    created_at: {dt(M96)}
    updated_at: {dt(RECENT)}
    property_type: HO
    name: Résidence principale
    address: 12 rue de la Liberté, 75014 Paris, France
    is_active: true
    buying_value: 320000.00
    buying_value_currency: EUR
    buying_date: {ds(M96)}
    selling_date: null
    floor_area: "112.50"
    is_furnished: false
- model: property.propertyvalue
  pk: 1
  fields:
    created_at: {dt(M96)}
    updated_at: {dt(M96)}
    property: 1
    value: 320000.00
    valuation_date: {ds(M96)}
- model: property.propertyvalue
  pk: 2
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 1
    value: 345000.00
    valuation_date: {ds(M48)}
- model: property.propertyvalue
  pk: 3
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    property: 1
    value: 375000.00
    valuation_date: {ds(RECENT)}
# Loan 1 — standard 20-year mortgage at 1.85 %
- model: property.propertyloan
  pk: 1
  fields:
    created_at: {dt(M96)}
    updated_at: {dt(M96)}
    property: 1
    name: Prêt immobilier principal
    lender: Crédit Agricole
    original_amount: 256000
    original_amount_currency: EUR
    interest_rate: "1.85"
    insurance_rate: "0.18"
    start_date: {ds(M96)}
    end_date: {ds(LOAN1_END)}
    monthly_payment: 1285.00
    monthly_payment_currency: EUR
    insurance: 38.40
    insurance_currency: EUR
# Transactions — Property 1
- model: property.propertyledgerentry
  pk: 1
  fields:
    created_at: {dt(M96)}
    updated_at: {dt(M96)}
    property: 1
    lease: null
    flow_type: expense
    amount: 2800.00
    amount_currency: EUR
    entry_date: {ds(M96)}
    reference_period: null
    management_category: property_tax
    description: Taxe foncière
    notes: ""
    recurrence_type: yearly
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 2
  fields:
    created_at: {dt(M96)}
    updated_at: {dt(M96)}
    property: 1
    lease: null
    flow_type: expense
    amount: 65.00
    amount_currency: EUR
    entry_date: {ds(M96)}
    reference_period: null
    management_category: insurance
    description: Assurance habitation
    notes: ""
    recurrence_type: monthly
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 3
  fields:
    created_at: {dt(M30)}
    updated_at: {dt(M30)}
    property: 1
    lease: null
    flow_type: expense
    amount: 4200.00
    amount_currency: EUR
    entry_date: {ds(M30)}
    reference_period: null
    management_category: works
    description: Rénovation salle de bain
    notes: "Remplacement baignoire, carrelage et robinetterie"
    recurrence_type: none
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 4
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    property: 1
    lease: null
    flow_type: expense
    amount: 850.00
    amount_currency: EUR
    entry_date: {ds(M12)}
    reference_period: null
    management_category: maintenance
    description: Remplacement chaudière
    notes: ""
    recurrence_type: none
    recurrence_end_date: null

# ─────────────────────────────────────────────────────────────────────────────
# PROPERTY 2 — Appartement locatif Nice (Apartment, bought 4 years ago)
#   Loans: 2 smoothed loans (prêt lisseur) — 10-year + 20-year
#   Lease: active furnished lease with tenant
# ─────────────────────────────────────────────────────────────────────────────
- model: property.property
  pk: 2
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(RECENT)}
    property_type: AP
    name: Appartement locatif Nice
    address: 8 avenue des Fleurs, 06000 Nice, France
    is_active: true
    buying_value: 185000.00
    buying_value_currency: EUR
    buying_date: {ds(M48)}
    selling_date: null
    floor_area: "42.00"
    is_furnished: true
- model: property.propertyvalue
  pk: 4
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 2
    value: 185000.00
    valuation_date: {ds(M48)}
- model: property.propertyvalue
  pk: 5
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    property: 2
    value: 190000.00
    valuation_date: {ds(M24)}
- model: property.propertyvalue
  pk: 6
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    property: 2
    value: 195000.00
    valuation_date: {ds(RECENT)}
# Loan 2A — smoothed 10-year
#   Schedule total: 1×834.00 + 59×667.00 + 60×666.67 = 834.00 + 39353.00 + 40000.20 ≈ 80000
#   Tranches: first month higher (setup fee), then two equal halves
#   sum = 1×834 + 59×667 + 60×666.67 = 834 + 39353 + 40000.20 = 80187.20 → adjust last tranche
#   Simpler: 1×800 + 119×666.39 + 1×600.59 = 800 + 79300.41 + 600.59 = 80701 → too high
#   Use: 1×800.00 + 118×666.00 + 1×666.52 = 800 + 78588 + 666.52 = 80054.52 → close
#   Exact: 1×800.00 + 118×666.00 + 1×612.00 = 800 + 78588 + 612 = 80000
- model: property.propertyloan
  pk: 2
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 2
    name: Prêt lissé
    lender: Crédit Mutuel
    original_amount: 80000
    original_amount_currency: EUR
    interest_rate: "2.95"
    insurance_rate: "0.00"
    start_date: {ds(M48)}
    end_date: {ds(LOAN2A_END)}
    monthly_payment: null
    monthly_payment_currency: EUR
    insurance: null
    insurance_currency: EUR
- model: property.propertyloanschedule
  pk: 1
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    loan: 2
    order: 1
    count: 1
    amount: 800.00
    amount_currency: EUR
- model: property.propertyloanschedule
  pk: 2
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    loan: 2
    order: 2
    count: 118
    amount: 666.00
    amount_currency: EUR
- model: property.propertyloanschedule
  pk: 3
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    loan: 2
    order: 3
    count: 1
    amount: 612.00
    amount_currency: EUR
# Loan 2B — smoothed 20-year
#   Schedule total: 1×1050.00 + 238×437.00 + 1×437.40 = 1050 + 103906 + 437.40 = 105393.40 → adjust
#   Exact: 1×1050.00 + 238×437.00 + 1×44.00 = 1050 + 103906 + 44 = 105000
- model: property.propertyloan
  pk: 3
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 2
    name: Prêt
    lender: Crédit Mutuel
    original_amount: 105000
    original_amount_currency: EUR
    interest_rate: "3.10"
    insurance_rate: "0.00"
    start_date: {ds(M48)}
    end_date: {ds(LOAN2B_END)}
    monthly_payment: null
    monthly_payment_currency: EUR
    insurance: null
    insurance_currency: EUR
- model: property.propertyloanschedule
  pk: 6
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    loan: 3
    order: 1
    count: 1
    amount: 1050.00
    amount_currency: EUR
- model: property.propertyloanschedule
  pk: 7
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    loan: 3
    order: 2
    count: 238
    amount: 437.00
    amount_currency: EUR
- model: property.propertyloanschedule
  pk: 8
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    loan: 3
    order: 3
    count: 1
    amount: 44.00
    amount_currency: EUR
# Lease 1 — Nice apartment (active furnished)
- model: property.lease
  pk: 1
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(M36)}
    property: 2
    first_name: Sophie
    last_name: Martin
    email: sophie.martin@example.com
    phone: "0612345678"
    lease_type: furnished
    status: active
    start_date: {ds(M36)}
    end_date: null
    notice_date: null
    rent_amount: 750.00
    rent_amount_currency: EUR
    charges_amount: 80.00
    charges_amount_currency: EUR
    deposit_amount: 1500.00
    deposit_amount_currency: EUR
    periodicity: monthly
    notes: "Bail meublé 1 an renouvelable"
# Transactions — Property 2
- model: property.propertyledgerentry
  pk: 5
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(M36)}
    property: 2
    lease: 1
    flow_type: income
    amount: 1500.00
    amount_currency: EUR
    entry_date: {ds(M36)}
    reference_period: null
    management_category: deposit_in
    description: Dépôt de garantie
    notes: ""
    recurrence_type: none
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 6
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(M36)}
    property: 2
    lease: 1
    flow_type: income
    amount: 750.00
    amount_currency: EUR
    entry_date: {ds(M36)}
    reference_period: null
    management_category: rent_collected
    description: Loyer mensuel
    notes: ""
    recurrence_type: monthly
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 7
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(M36)}
    property: 2
    lease: 1
    flow_type: income
    amount: 80.00
    amount_currency: EUR
    entry_date: {ds(M36)}
    reference_period: null
    management_category: charges_collected
    description: Provision pour charges
    notes: ""
    recurrence_type: monthly
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 8
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 2
    lease: null
    flow_type: expense
    amount: 980.00
    amount_currency: EUR
    entry_date: {ds(M48)}
    reference_period: null
    management_category: property_tax
    description: Taxe foncière
    notes: ""
    recurrence_type: yearly
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 9
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 2
    lease: null
    flow_type: expense
    amount: 145.00
    amount_currency: EUR
    entry_date: {ds(M48)}
    reference_period: null
    management_category: coownership
    description: Charges de copropriété
    notes: ""
    recurrence_type: monthly
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 10
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 2
    lease: null
    flow_type: expense
    amount: 28.00
    amount_currency: EUR
    entry_date: {ds(M48)}
    reference_period: null
    management_category: insurance
    description: Assurance propriétaire non-occupant (PNO)
    notes: ""
    recurrence_type: monthly
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 11
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    property: 2
    lease: null
    flow_type: expense
    amount: 1250.00
    amount_currency: EUR
    entry_date: {ds(M18)}
    reference_period: null
    management_category: maintenance
    description: Réparation plomberie — fuite salle de bain
    notes: "Intervention plombier + remplacement joint"
    recurrence_type: none
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 12
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    property: 2
    lease: null
    flow_type: expense
    amount: 320.00
    amount_currency: EUR
    entry_date: {ds(M12)}
    reference_period: null
    management_category: cfe
    description: CFE (Cotisation Foncière des Entreprises)
    notes: ""
    recurrence_type: none
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 13
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    property: 2
    lease: 1
    flow_type: income
    amount: 240.00
    amount_currency: EUR
    entry_date: {ds(M6)}
    reference_period: null
    management_category: charges_collected
    description: Régularisation charges annuelle
    notes: "Solde positif en faveur du propriétaire"
    recurrence_type: none
    recurrence_end_date: null

# ─────────────────────────────────────────────────────────────────────────────
# PROPERTY 3 — Studio meublé Lyon (Apartment, bought 4 years ago)
#   Loan: 1 standard 8-year loan finishing in ~4 years
#   Lease: active furnished lease with tenant
# ─────────────────────────────────────────────────────────────────────────────
- model: property.property
  pk: 3
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(RECENT)}
    property_type: AP
    name: Studio meublé Lyon
    address: 3 rue Mercière, 69002 Lyon, France
    is_active: true
    buying_value: 95000.00
    buying_value_currency: EUR
    buying_date: {ds(M48)}
    selling_date: null
    floor_area: "22.00"
    is_furnished: true
- model: property.propertyvalue
  pk: 7
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 3
    value: 95000.00
    valuation_date: {ds(M48)}
- model: property.propertyvalue
  pk: 8
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    property: 3
    value: 102000.00
    valuation_date: {ds(RECENT)}
# Loan 3 — standard 8-year loan at 2.40 % (started 4 years ago, ends in ~4 years)
- model: property.propertyloan
  pk: 4
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 3
    name: Prêt immobilier studio
    lender: BNP Paribas
    original_amount: 72000
    original_amount_currency: EUR
    interest_rate: "2.40"
    insurance_rate: "0.22"
    start_date: {ds(M48)}
    end_date: {ds(LOAN3_END)}
    monthly_payment: 870.00
    monthly_payment_currency: EUR
    insurance: 13.20
    insurance_currency: EUR
# Lease 2 — Lyon studio (active furnished)
- model: property.lease
  pk: 2
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    property: 3
    first_name: Lucas
    last_name: Dupont
    email: lucas.dupont@example.com
    phone: "0698765432"
    lease_type: furnished
    status: active
    start_date: {ds(M24)}
    end_date: null
    notice_date: null
    rent_amount: 520.00
    rent_amount_currency: EUR
    charges_amount: 50.00
    charges_amount_currency: EUR
    deposit_amount: 1040.00
    deposit_amount_currency: EUR
    periodicity: monthly
    notes: "Bail meublé étudiant"
# Transactions — Property 3
- model: property.propertyledgerentry
  pk: 14
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    property: 3
    lease: 2
    flow_type: income
    amount: 1040.00
    amount_currency: EUR
    entry_date: {ds(M24)}
    reference_period: null
    management_category: deposit_in
    description: Dépôt de garantie
    notes: ""
    recurrence_type: none
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 15
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    property: 3
    lease: 2
    flow_type: income
    amount: 520.00
    amount_currency: EUR
    entry_date: {ds(M24)}
    reference_period: null
    management_category: rent_collected
    description: Loyer mensuel
    notes: ""
    recurrence_type: monthly
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 16
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    property: 3
    lease: 2
    flow_type: income
    amount: 50.00
    amount_currency: EUR
    entry_date: {ds(M24)}
    reference_period: null
    management_category: charges_collected
    description: Provision pour charges
    notes: ""
    recurrence_type: monthly
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 17
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 3
    lease: null
    flow_type: expense
    amount: 420.00
    amount_currency: EUR
    entry_date: {ds(M48)}
    reference_period: null
    management_category: property_tax
    description: Taxe foncière
    notes: ""
    recurrence_type: yearly
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 18
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 3
    lease: null
    flow_type: expense
    amount: 18.00
    amount_currency: EUR
    entry_date: {ds(M48)}
    reference_period: null
    management_category: insurance
    description: Assurance PNO
    notes: ""
    recurrence_type: monthly
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 19
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    property: 3
    lease: null
    flow_type: expense
    amount: 185.00
    amount_currency: EUR
    entry_date: {ds(M12)}
    reference_period: null
    management_category: cfe
    description: CFE
    notes: ""
    recurrence_type: none
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 20
  fields:
    created_at: {dt(M9)}
    updated_at: {dt(M9)}
    property: 3
    lease: null
    flow_type: expense
    amount: 380.00
    amount_currency: EUR
    entry_date: {ds(M9)}
    reference_period: null
    management_category: maintenance
    description: Remplacement électroménager (lave-linge)
    notes: ""
    recurrence_type: none
    recurrence_end_date: null

# ─────────────────────────────────────────────────────────────────────────────
# PROPERTY 4 — Maison de campagne (House, bought 6 years ago)
#   No loan, no lease — punctual Airbnb income + owner expenses
# ─────────────────────────────────────────────────────────────────────────────
- model: property.property
  pk: 4
  fields:
    created_at: {dt(M72)}
    updated_at: {dt(RECENT)}
    property_type: HO
    name: Maison de campagne
    address: Le Bourg, 24200 Sarlat-la-Canéda, France
    is_active: true
    buying_value: 145000.00
    buying_value_currency: EUR
    buying_date: {ds(M72)}
    selling_date: null
    floor_area: "95.00"
    is_furnished: true
- model: property.propertyvalue
  pk: 9
  fields:
    created_at: {dt(M72)}
    updated_at: {dt(M72)}
    property: 4
    value: 145000.00
    valuation_date: {ds(M72)}
- model: property.propertyvalue
  pk: 10
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(M36)}
    property: 4
    value: 155000.00
    valuation_date: {ds(M36)}
- model: property.propertyvalue
  pk: 11
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    property: 4
    value: 162000.00
    valuation_date: {ds(RECENT)}
# Transactions — Property 4
- model: property.propertyledgerentry
  pk: 21
  fields:
    created_at: {dt(M72)}
    updated_at: {dt(M72)}
    property: 4
    lease: null
    flow_type: expense
    amount: 1650.00
    amount_currency: EUR
    entry_date: {ds(M72)}
    reference_period: null
    management_category: property_tax
    description: Taxe foncière
    notes: ""
    recurrence_type: yearly
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 22
  fields:
    created_at: {dt(M72)}
    updated_at: {dt(M72)}
    property: 4
    lease: null
    flow_type: expense
    amount: 55.00
    amount_currency: EUR
    entry_date: {ds(M72)}
    reference_period: null
    management_category: insurance
    description: Assurance habitation résidence secondaire
    notes: ""
    recurrence_type: monthly
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 23
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 4
    lease: null
    flow_type: expense
    amount: 8500.00
    amount_currency: EUR
    entry_date: {ds(M48)}
    reference_period: null
    management_category: works
    description: Rénovation cuisine et terrasse
    notes: "Travaux réalisés par entreprise locale"
    recurrence_type: none
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 24
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    property: 4
    lease: null
    flow_type: income
    amount: 1800.00
    amount_currency: EUR
    entry_date: {ds(M18)}
    reference_period: null
    management_category: rent_collected
    description: Location Airbnb — été
    notes: "Juillet-août, 3 semaines"
    recurrence_type: none
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 25
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    property: 4
    lease: null
    flow_type: income
    amount: 2100.00
    amount_currency: EUR
    entry_date: {ds(M12)}
    reference_period: null
    management_category: rent_collected
    description: Location Airbnb — été
    notes: "Juillet-août, 4 semaines"
    recurrence_type: none
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 26
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    property: 4
    lease: null
    flow_type: income
    amount: 650.00
    amount_currency: EUR
    entry_date: {ds(M6)}
    reference_period: null
    management_category: rent_collected
    description: Location Airbnb — vacances de Noël
    notes: "2 semaines"
    recurrence_type: none
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 27
  fields:
    created_at: {dt(M3)}
    updated_at: {dt(M3)}
    property: 4
    lease: null
    flow_type: expense
    amount: 420.00
    amount_currency: EUR
    entry_date: {ds(M3)}
    reference_period: null
    management_category: maintenance
    description: Entretien jardin et piscine
    notes: ""
    recurrence_type: none
    recurrence_end_date: null
"""


def main() -> None:
    """Generate all test fixture files."""
    print("Generating dynamic test fixtures...")
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    write_fixture("investmentaccount.yaml", generate_investmentaccount())
    write_fixture("savingaccount.yaml", generate_savingaccount())
    write_fixture("property.yaml", generate_property())
    print("Done.")


if __name__ == "__main__":
    main()
