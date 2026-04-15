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
M60 = months_ago(60)

LOAN_END = years_ahead(20, M24)


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


def generate_property() -> str:
    """Generate property.yaml with dynamic dates."""
    return f"""# generated with scripts/generate_fixtures.py
---
- model: property.property
  pk: 1
  fields:
    created_at: {dt(M60)}
    updated_at: {dt(RECENT)}
    property_type: HO
    name: Résidence principale
    address: 12 rue de la Liberté, 75014 Paris, France
    is_active: true
    buying_value: 200000.00
    buying_value_currency: EUR
    buying_date: {ds(M60)}
    selling_date: null
- model: property.propertyvalue
  pk: 1
  fields:
    created_at: {dt(M60)}
    updated_at: {dt(M60)}
    property: 1
    value: 200000.00
    valuation_date: {ds(M60)}
- model: property.propertyvalue
  pk: 2
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    property: 1
    value: 250000.00
    valuation_date: {ds(RECENT)}
- model: property.property
  pk: 2
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(RECENT)}
    property_type: AP
    name: Appartement locatif
    address: 8 avenue des Fleurs, 06000 Nice, France
    is_active: true
    buying_value: 130000.00
    buying_value_currency: EUR
    buying_date: {ds(M24)}
    selling_date: null
- model: property.propertyvalue
  pk: 3
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    property: 2
    value: 130000.00
    valuation_date: {ds(M24)}
- model: property.propertyvalue
  pk: 4
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    property: 2
    value: 130000.00
    valuation_date: {ds(RECENT)}
- model: property.propertyloan
  pk: 1
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    property: 2
    lender: Banque Populaire
    original_amount: 100000.00
    original_amount_currency: EUR
    interest_rate: "3.4"
    insurance_rate: "0.2"
    start_date: {ds(M24)}
    end_date: {ds(LOAN_END)}
    monthly_payment: 600.00
    monthly_payment_currency: EUR
- model: property.propertyledgerentry
  pk: 1
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    property: 2
    lease: null
    mandate: null
    flow_type: income
    amount: 1200.00
    amount_currency: EUR
    entry_date: {ds(M24)}
    reference_period: null
    tax_category: rent
    management_category: rent_collected
    description: Loyer mensuel
    notes: ""
    recurrence_type: monthly
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 2
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    property: 2
    lease: null
    mandate: null
    flow_type: income
    amount: 500.00
    amount_currency: EUR
    entry_date: {ds(M12)}
    reference_period: null
    tax_category: other_income
    management_category: other
    description: Remboursement de charges
    notes: ""
    recurrence_type: none
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 3
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    property: 2
    lease: null
    mandate: null
    flow_type: expense
    amount: 1200.00
    amount_currency: EUR
    entry_date: {ds(M24)}
    reference_period: null
    tax_category: taxes
    management_category: property_tax
    description: Taxe foncière
    notes: ""
    recurrence_type: yearly
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 4
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    property: 2
    lease: null
    mandate: null
    flow_type: expense
    amount: 850.00
    amount_currency: EUR
    entry_date: {ds(M18)}
    reference_period: null
    tax_category: maintenance_repairs
    management_category: maintenance
    description: Réparation plomberie
    notes: ""
    recurrence_type: none
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 5
  fields:
    created_at: {dt(M60)}
    updated_at: {dt(M60)}
    property: 1
    lease: null
    mandate: null
    flow_type: expense
    amount: 2500.00
    amount_currency: EUR
    entry_date: {ds(M60)}
    reference_period: null
    tax_category: taxes
    management_category: property_tax
    description: Taxe foncière
    notes: ""
    recurrence_type: yearly
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 6
  fields:
    created_at: {dt(M30)}
    updated_at: {dt(M30)}
    property: 1
    lease: null
    mandate: null
    flow_type: expense
    amount: 1800.00
    amount_currency: EUR
    entry_date: {ds(M30)}
    reference_period: null
    tax_category: maintenance_repairs
    management_category: maintenance
    description: Rénovation toiture
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
