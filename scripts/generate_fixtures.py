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
M2 = months_ago(2)
M3 = months_ago(3)
M4 = months_ago(4)
M5 = months_ago(5)
M6 = months_ago(6)
M7 = months_ago(7)
M8 = months_ago(8)
M9 = months_ago(9)
M10 = months_ago(10)
M11 = months_ago(11)
M12 = months_ago(12)
M13 = months_ago(13)
M14 = months_ago(14)
M15 = months_ago(15)
M18 = months_ago(18)
M21 = months_ago(21)
M24 = months_ago(24)
M25 = months_ago(25)
M27 = months_ago(27)
M28 = months_ago(28)
M30 = months_ago(30)
M33 = months_ago(33)
M36 = months_ago(36)
M47 = months_ago(47)
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

# SCPI dismemberment end date
SCPI3_RECO = years_ahead(10, M24)  # SCPI 3 bare ownership reconstitution in 10 years


# === Fixture generators ===


def generate_investmentaccount() -> str:
    """Generate investmentaccount.yaml with dynamic dates.

    Account 1: PEA (Plan d'épargne en actions) — ~100k€ total, 6 holdings (4 profit / 2 loss)
    Account 2: Assurance Vie — ~40k€ total, 5 holdings (3 profit / 2 loss)
    """
    return f"""# generated with scripts/generate_fixtures.py
---
# ── Account 1: PEA ────────────────────────────────────────────────────────────
- model: finance.investmentaccount
  pk: 1
  fields:
    created_at: {dt(M84)}
    updated_at: {dt(RECENT)}
    account_type_id: 1
    owner: Commun
    institution: TopBanque
    is_active: true
    is_favorite: true
    opening_date: {ds(M84)}
    opening_cash_value: 0
    opening_cash_value_currency: EUR
# ── Holding 1: ETF MSCI World (profit +42%) ───────────────────────────────────
- model: finance.investmentaccountholding
  pk: 1
  fields:
    created_at: {dt(M84)}
    updated_at: {dt(RECENT)}
    account_id: 1
    name: ETF MSCI World
    code: WRLD
    is_active: true
    initial_quantity: 200
    initial_value: 28000
    initial_value_currency: EUR
    initial_valuation_date: {ds(M84)}
- model: finance.investmentaccountholdinghistory
  pk: 1
  fields:
    created_at: {dt(M72)}
    updated_at: {dt(M72)}
    holding_id: 1
    value: 29500
    value_currency: EUR
    quantity: 200
    valuation_date: {ds(M72)}
- model: finance.investmentaccountholdinghistory
  pk: 2
  fields:
    created_at: {dt(M60)}
    updated_at: {dt(M60)}
    holding_id: 1
    value: 30500
    value_currency: EUR
    quantity: 200
    valuation_date: {ds(M60)}
- model: finance.investmentaccountholdinghistory
  pk: 3
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    holding_id: 1
    value: 32000
    value_currency: EUR
    quantity: 200
    valuation_date: {ds(M48)}
- model: finance.investmentaccountholdinghistory
  pk: 4
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(M36)}
    holding_id: 1
    value: 33500
    value_currency: EUR
    quantity: 200
    valuation_date: {ds(M36)}
- model: finance.investmentaccountholdinghistory
  pk: 5
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    holding_id: 1
    value: 35000
    value_currency: EUR
    quantity: 200
    valuation_date: {ds(M24)}
- model: finance.investmentaccountholdinghistory
  pk: 6
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    holding_id: 1
    value: 36500
    value_currency: EUR
    quantity: 200
    valuation_date: {ds(M18)}
- model: finance.investmentaccountholdinghistory
  pk: 7
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    holding_id: 1
    value: 38000
    value_currency: EUR
    quantity: 200
    valuation_date: {ds(M12)}
- model: finance.investmentaccountholdinghistory
  pk: 8
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    holding_id: 1
    value: 37200
    value_currency: EUR
    quantity: 200
    valuation_date: {ds(M6)}
- model: finance.investmentaccountholdinghistory
  pk: 9
  fields:
    created_at: {dt(M3)}
    updated_at: {dt(M3)}
    holding_id: 1
    value: 39000
    value_currency: EUR
    quantity: 200
    valuation_date: {ds(M3)}
- model: finance.investmentaccountholdinghistory
  pk: 10
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    holding_id: 1
    value: 40000
    value_currency: EUR
    quantity: 200
    valuation_date: {ds(RECENT)}
# ── Holding 2: ETF S&P 500 (profit +30%) ─────────────────────────────────────
- model: finance.investmentaccountholding
  pk: 2
  fields:
    created_at: {dt(M72)}
    updated_at: {dt(RECENT)}
    account_id: 1
    name: ETF S&P 500
    code: SP5
    is_active: true
    initial_quantity: 80
    initial_value: 20000
    initial_value_currency: EUR
    initial_valuation_date: {ds(M72)}
- model: finance.investmentaccountholdinghistory
  pk: 11
  fields:
    created_at: {dt(M60)}
    updated_at: {dt(M60)}
    holding_id: 2
    value: 21000
    value_currency: EUR
    quantity: 80
    valuation_date: {ds(M60)}
- model: finance.investmentaccountholdinghistory
  pk: 12
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    holding_id: 2
    value: 22000
    value_currency: EUR
    quantity: 80
    valuation_date: {ds(M48)}
- model: finance.investmentaccountholdinghistory
  pk: 13
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(M36)}
    holding_id: 2
    value: 23000
    value_currency: EUR
    quantity: 80
    valuation_date: {ds(M36)}
- model: finance.investmentaccountholdinghistory
  pk: 14
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    holding_id: 2
    value: 23500
    value_currency: EUR
    quantity: 80
    valuation_date: {ds(M24)}
- model: finance.investmentaccountholdinghistory
  pk: 15
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    holding_id: 2
    value: 24000
    value_currency: EUR
    quantity: 80
    valuation_date: {ds(M18)}
- model: finance.investmentaccountholdinghistory
  pk: 16
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    holding_id: 2
    value: 24500
    value_currency: EUR
    quantity: 80
    valuation_date: {ds(M12)}
- model: finance.investmentaccountholdinghistory
  pk: 17
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    holding_id: 2
    value: 25000
    value_currency: EUR
    quantity: 80
    valuation_date: {ds(M6)}
- model: finance.investmentaccountholdinghistory
  pk: 18
  fields:
    created_at: {dt(M3)}
    updated_at: {dt(M3)}
    holding_id: 2
    value: 25500
    value_currency: EUR
    quantity: 80
    valuation_date: {ds(M3)}
- model: finance.investmentaccountholdinghistory
  pk: 19
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    holding_id: 2
    value: 26000
    value_currency: EUR
    quantity: 80
    valuation_date: {ds(RECENT)}
# ── Holding 3: ETF Europe Stoxx 600 (profit +15%) ────────────────────────────
- model: finance.investmentaccountholding
  pk: 3
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(RECENT)}
    account_id: 1
    name: ETF Europe Stoxx 600
    code: EU6
    is_active: true
    initial_quantity: 150
    initial_value: 13000
    initial_value_currency: EUR
    initial_valuation_date: {ds(M48)}
- model: finance.investmentaccountholdinghistory
  pk: 20
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(M36)}
    holding_id: 3
    value: 13500
    value_currency: EUR
    quantity: 150
    valuation_date: {ds(M36)}
- model: finance.investmentaccountholdinghistory
  pk: 21
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    holding_id: 3
    value: 13800
    value_currency: EUR
    quantity: 150
    valuation_date: {ds(M24)}
- model: finance.investmentaccountholdinghistory
  pk: 22
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    holding_id: 3
    value: 14200
    value_currency: EUR
    quantity: 150
    valuation_date: {ds(M18)}
- model: finance.investmentaccountholdinghistory
  pk: 23
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    holding_id: 3
    value: 14500
    value_currency: EUR
    quantity: 150
    valuation_date: {ds(M12)}
- model: finance.investmentaccountholdinghistory
  pk: 24
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    holding_id: 3
    value: 14800
    value_currency: EUR
    quantity: 150
    valuation_date: {ds(M6)}
- model: finance.investmentaccountholdinghistory
  pk: 25
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    holding_id: 3
    value: 15000
    value_currency: EUR
    quantity: 150
    valuation_date: {ds(RECENT)}
# ── Holding 4: ETF Nasdaq Tech (profit +37%) ─────────────────────────────────
- model: finance.investmentaccountholding
  pk: 4
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(RECENT)}
    account_id: 1
    name: ETF Nasdaq Tech
    code: NSDQ
    is_active: true
    initial_quantity: 50
    initial_value: 8000
    initial_value_currency: EUR
    initial_valuation_date: {ds(M24)}
- model: finance.investmentaccountholdinghistory
  pk: 26
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    holding_id: 4
    value: 8800
    value_currency: EUR
    quantity: 50
    valuation_date: {ds(M18)}
- model: finance.investmentaccountholdinghistory
  pk: 27
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    holding_id: 4
    value: 9500
    value_currency: EUR
    quantity: 50
    valuation_date: {ds(M12)}
- model: finance.investmentaccountholdinghistory
  pk: 28
  fields:
    created_at: {dt(M9)}
    updated_at: {dt(M9)}
    holding_id: 4
    value: 9800
    value_currency: EUR
    quantity: 50
    valuation_date: {ds(M9)}
- model: finance.investmentaccountholdinghistory
  pk: 29
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    holding_id: 4
    value: 10200
    value_currency: EUR
    quantity: 50
    valuation_date: {ds(M6)}
- model: finance.investmentaccountholdinghistory
  pk: 30
  fields:
    created_at: {dt(M3)}
    updated_at: {dt(M3)}
    holding_id: 4
    value: 10800
    value_currency: EUR
    quantity: 50
    valuation_date: {ds(M3)}
- model: finance.investmentaccountholdinghistory
  pk: 31
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    holding_id: 4
    value: 11000
    value_currency: EUR
    quantity: 50
    valuation_date: {ds(RECENT)}
# ── Holding 5: ETF Énergie (LOSS -10%) ────────────────────────────────────────
- model: finance.investmentaccountholding
  pk: 5
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(RECENT)}
    account_id: 1
    name: ETF Énergie
    code: ENRG
    is_active: true
    initial_quantity: 100
    initial_value: 5000
    initial_value_currency: EUR
    initial_valuation_date: {ds(M12)}
- model: finance.investmentaccountholdinghistory
  pk: 32
  fields:
    created_at: {dt(M9)}
    updated_at: {dt(M9)}
    holding_id: 5
    value: 4850
    value_currency: EUR
    quantity: 100
    valuation_date: {ds(M9)}
- model: finance.investmentaccountholdinghistory
  pk: 33
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    holding_id: 5
    value: 4750
    value_currency: EUR
    quantity: 100
    valuation_date: {ds(M6)}
- model: finance.investmentaccountholdinghistory
  pk: 34
  fields:
    created_at: {dt(M3)}
    updated_at: {dt(M3)}
    holding_id: 5
    value: 4600
    value_currency: EUR
    quantity: 100
    valuation_date: {ds(M3)}
- model: finance.investmentaccountholdinghistory
  pk: 35
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    holding_id: 5
    value: 4500
    value_currency: EUR
    quantity: 100
    valuation_date: {ds(RECENT)}
# ── Holding 6: ETF Obligations (LOSS -7.5%) ──────────────────────────────────
- model: finance.investmentaccountholding
  pk: 6
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(RECENT)}
    account_id: 1
    name: ETF Obligations
    code: OBLIG
    is_active: true
    initial_quantity: 200
    initial_value: 4000
    initial_value_currency: EUR
    initial_valuation_date: {ds(M12)}
- model: finance.investmentaccountholdinghistory
  pk: 36
  fields:
    created_at: {dt(M9)}
    updated_at: {dt(M9)}
    holding_id: 6
    value: 3900
    value_currency: EUR
    quantity: 200
    valuation_date: {ds(M9)}
- model: finance.investmentaccountholdinghistory
  pk: 37
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    holding_id: 6
    value: 3800
    value_currency: EUR
    quantity: 200
    valuation_date: {ds(M6)}
- model: finance.investmentaccountholdinghistory
  pk: 38
  fields:
    created_at: {dt(M3)}
    updated_at: {dt(M3)}
    holding_id: 6
    value: 3750
    value_currency: EUR
    quantity: 200
    valuation_date: {ds(M3)}
- model: finance.investmentaccountholdinghistory
  pk: 39
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    holding_id: 6
    value: 3700
    value_currency: EUR
    quantity: 200
    valuation_date: {ds(RECENT)}
# ── Cash history: PEA ─────────────────────────────────────────────────────────
# Deposits flow: 25k(M84)+12k(M72)+12k(M60)+10k(M48)+8k(M36)+8k(M24)+5k(M12)+3k(M3)=83k
# Holdings bought: WRLD 28k(M84), SP5 20k(M72), EU6 13k(M48), NSDQ 8k(M24), ENRG+OBLIG 9k(M12)
- model: finance.investmentaccountcash
  pk: 1
  fields:
    created_at: {dt(M84)}
    updated_at: {dt(M84)}
    account_id: 1
    value: 25000
    value_currency: EUR
    value_date: {ds(M84)}
- model: finance.investmentaccountcash
  pk: 2
  fields:
    created_at: {dt(M72)}
    updated_at: {dt(M72)}
    account_id: 1
    value: 17000
    value_currency: EUR
    value_date: {ds(M72)}
- model: finance.investmentaccountcash
  pk: 3
  fields:
    created_at: {dt(M60)}
    updated_at: {dt(M60)}
    account_id: 1
    value: 21000
    value_currency: EUR
    value_date: {ds(M60)}
- model: finance.investmentaccountcash
  pk: 4
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    account_id: 1
    value: 18000
    value_currency: EUR
    value_date: {ds(M48)}
- model: finance.investmentaccountcash
  pk: 5
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(M36)}
    account_id: 1
    value: 13000
    value_currency: EUR
    value_date: {ds(M36)}
- model: finance.investmentaccountcash
  pk: 6
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    account_id: 1
    value: 13000
    value_currency: EUR
    value_date: {ds(M24)}
- model: finance.investmentaccountcash
  pk: 7
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    account_id: 1
    value: 9000
    value_currency: EUR
    value_date: {ds(M12)}
- model: finance.investmentaccountcash
  pk: 8
  fields:
    created_at: {dt(M3)}
    updated_at: {dt(M3)}
    account_id: 1
    value: 5000
    value_currency: EUR
    value_date: {ds(M3)}
- model: finance.investmentaccountcash
  pk: 9
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    account_id: 1
    value: 5000
    value_currency: EUR
    value_date: {ds(RECENT)}
# ── Deposits: PEA ─────────────────────────────────────────────────────────────
- model: finance.investmentaccountdeposit
  pk: 1
  fields:
    created_at: {dt(M84)}
    updated_at: {dt(M84)}
    account_id: 1
    amount: 25000
    amount_currency: EUR
    deposit_date: {ds(M84)}
    source: Virement bancaire
    update_account_cash: true
- model: finance.investmentaccountdeposit
  pk: 2
  fields:
    created_at: {dt(M72)}
    updated_at: {dt(M72)}
    account_id: 1
    amount: 12000
    amount_currency: EUR
    deposit_date: {ds(M72)}
    source: Virement bancaire
    update_account_cash: true
- model: finance.investmentaccountdeposit
  pk: 3
  fields:
    created_at: {dt(M60)}
    updated_at: {dt(M60)}
    account_id: 1
    amount: 12000
    amount_currency: EUR
    deposit_date: {ds(M60)}
    source: Virement bancaire
    update_account_cash: true
- model: finance.investmentaccountdeposit
  pk: 4
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    account_id: 1
    amount: 10000
    amount_currency: EUR
    deposit_date: {ds(M48)}
    source: Virement bancaire
    update_account_cash: true
- model: finance.investmentaccountdeposit
  pk: 5
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(M36)}
    account_id: 1
    amount: 8000
    amount_currency: EUR
    deposit_date: {ds(M36)}
    source: Virement bancaire
    update_account_cash: true
- model: finance.investmentaccountdeposit
  pk: 6
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    account_id: 1
    amount: 8000
    amount_currency: EUR
    deposit_date: {ds(M24)}
    source: Virement bancaire
    update_account_cash: true
- model: finance.investmentaccountdeposit
  pk: 7
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    account_id: 1
    amount: 5000
    amount_currency: EUR
    deposit_date: {ds(M12)}
    source: Virement bancaire
    update_account_cash: true
- model: finance.investmentaccountdeposit
  pk: 8
  fields:
    created_at: {dt(M3)}
    updated_at: {dt(M3)}
    account_id: 1
    amount: 3000
    amount_currency: EUR
    deposit_date: {ds(M3)}
    source: Virement bancaire
    update_account_cash: true
# ── Account 2: Assurance Vie ──────────────────────────────────────────────────
- model: finance.investmentaccount
  pk: 2
  fields:
    created_at: {dt(M60)}
    updated_at: {dt(RECENT)}
    account_type_id: 2
    owner: Mister
    institution: SuperAssur
    is_active: true
    opening_date: {ds(M60)}
    opening_cash_value: 0
    opening_cash_value_currency: EUR
# ── Holding 7: Fonds Euros (profit +10.7%) ────────────────────────────────────
- model: finance.investmentaccountholding
  pk: 7
  fields:
    created_at: {dt(M60)}
    updated_at: {dt(RECENT)}
    account_id: 2
    name: Fonds Euros
    code: FE
    is_active: true
    initial_quantity: 1
    initial_value: 14000
    initial_value_currency: EUR
    initial_valuation_date: {ds(M60)}
- model: finance.investmentaccountholdinghistory
  pk: 40
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    holding_id: 7
    value: 14200
    value_currency: EUR
    quantity: 1
    valuation_date: {ds(M48)}
- model: finance.investmentaccountholdinghistory
  pk: 41
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(M36)}
    holding_id: 7
    value: 14400
    value_currency: EUR
    quantity: 1
    valuation_date: {ds(M36)}
- model: finance.investmentaccountholdinghistory
  pk: 42
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    holding_id: 7
    value: 14600
    value_currency: EUR
    quantity: 1
    valuation_date: {ds(M24)}
- model: finance.investmentaccountholdinghistory
  pk: 43
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    holding_id: 7
    value: 14800
    value_currency: EUR
    quantity: 1
    valuation_date: {ds(M18)}
- model: finance.investmentaccountholdinghistory
  pk: 44
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    holding_id: 7
    value: 15000
    value_currency: EUR
    quantity: 1
    valuation_date: {ds(M12)}
- model: finance.investmentaccountholdinghistory
  pk: 45
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    holding_id: 7
    value: 15200
    value_currency: EUR
    quantity: 1
    valuation_date: {ds(M6)}
- model: finance.investmentaccountholdinghistory
  pk: 46
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    holding_id: 7
    value: 15500
    value_currency: EUR
    quantity: 1
    valuation_date: {ds(RECENT)}
# ── Holding 8: UC Actions Monde (profit +23%) ─────────────────────────────────
- model: finance.investmentaccountholding
  pk: 8
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(RECENT)}
    account_id: 2
    name: UC Actions Monde
    code: ACM
    is_active: true
    initial_quantity: 100
    initial_value: 8500
    initial_value_currency: EUR
    initial_valuation_date: {ds(M48)}
- model: finance.investmentaccountholdinghistory
  pk: 47
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(M36)}
    holding_id: 8
    value: 9000
    value_currency: EUR
    quantity: 100
    valuation_date: {ds(M36)}
- model: finance.investmentaccountholdinghistory
  pk: 48
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    holding_id: 8
    value: 9500
    value_currency: EUR
    quantity: 100
    valuation_date: {ds(M24)}
- model: finance.investmentaccountholdinghistory
  pk: 49
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    holding_id: 8
    value: 9800
    value_currency: EUR
    quantity: 100
    valuation_date: {ds(M18)}
- model: finance.investmentaccountholdinghistory
  pk: 50
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    holding_id: 8
    value: 10000
    value_currency: EUR
    quantity: 100
    valuation_date: {ds(M12)}
- model: finance.investmentaccountholdinghistory
  pk: 51
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    holding_id: 8
    value: 10200
    value_currency: EUR
    quantity: 100
    valuation_date: {ds(M6)}
- model: finance.investmentaccountholdinghistory
  pk: 52
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    holding_id: 8
    value: 10500
    value_currency: EUR
    quantity: 100
    valuation_date: {ds(RECENT)}
# ── Holding 9: UC Immobilier (profit +14%) ────────────────────────────────────
- model: finance.investmentaccountholding
  pk: 9
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(RECENT)}
    account_id: 2
    name: UC Immobilier
    code: IMM
    is_active: true
    initial_quantity: 50
    initial_value: 7000
    initial_value_currency: EUR
    initial_valuation_date: {ds(M36)}
- model: finance.investmentaccountholdinghistory
  pk: 53
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    holding_id: 9
    value: 7200
    value_currency: EUR
    quantity: 50
    valuation_date: {ds(M24)}
- model: finance.investmentaccountholdinghistory
  pk: 54
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    holding_id: 9
    value: 7400
    value_currency: EUR
    quantity: 50
    valuation_date: {ds(M18)}
- model: finance.investmentaccountholdinghistory
  pk: 55
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    holding_id: 9
    value: 7600
    value_currency: EUR
    quantity: 50
    valuation_date: {ds(M12)}
- model: finance.investmentaccountholdinghistory
  pk: 56
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    holding_id: 9
    value: 7800
    value_currency: EUR
    quantity: 50
    valuation_date: {ds(M6)}
- model: finance.investmentaccountholdinghistory
  pk: 57
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    holding_id: 9
    value: 8000
    value_currency: EUR
    quantity: 50
    valuation_date: {ds(RECENT)}
# ── Holding 10: UC Obligations (LOSS -8.6%) ───────────────────────────────────
- model: finance.investmentaccountholding
  pk: 10
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(RECENT)}
    account_id: 2
    name: UC Obligations
    code: OBLU
    is_active: true
    initial_quantity: 200
    initial_value: 3500
    initial_value_currency: EUR
    initial_valuation_date: {ds(M24)}
- model: finance.investmentaccountholdinghistory
  pk: 58
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    holding_id: 10
    value: 3400
    value_currency: EUR
    quantity: 200
    valuation_date: {ds(M18)}
- model: finance.investmentaccountholdinghistory
  pk: 59
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    holding_id: 10
    value: 3300
    value_currency: EUR
    quantity: 200
    valuation_date: {ds(M12)}
- model: finance.investmentaccountholdinghistory
  pk: 60
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    holding_id: 10
    value: 3250
    value_currency: EUR
    quantity: 200
    valuation_date: {ds(M6)}
- model: finance.investmentaccountholdinghistory
  pk: 61
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    holding_id: 10
    value: 3200
    value_currency: EUR
    quantity: 200
    valuation_date: {ds(RECENT)}
# ── Holding 11: UC Small Cap Europe (LOSS -8%) ────────────────────────────────
- model: finance.investmentaccountholding
  pk: 11
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(RECENT)}
    account_id: 2
    name: UC Small Cap Europe
    code: SCE
    is_active: true
    initial_quantity: 80
    initial_value: 2500
    initial_value_currency: EUR
    initial_valuation_date: {ds(M24)}
- model: finance.investmentaccountholdinghistory
  pk: 62
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    holding_id: 11
    value: 2450
    value_currency: EUR
    quantity: 80
    valuation_date: {ds(M18)}
- model: finance.investmentaccountholdinghistory
  pk: 63
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    holding_id: 11
    value: 2400
    value_currency: EUR
    quantity: 80
    valuation_date: {ds(M12)}
- model: finance.investmentaccountholdinghistory
  pk: 64
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    holding_id: 11
    value: 2350
    value_currency: EUR
    quantity: 80
    valuation_date: {ds(M6)}
- model: finance.investmentaccountholdinghistory
  pk: 65
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    holding_id: 11
    value: 2300
    value_currency: EUR
    quantity: 80
    valuation_date: {ds(RECENT)}
# ── Cash history: Assurance Vie ───────────────────────────────────────────────
# Deposits: 15k(M60)+8k(M48)+7k(M36)+6k(M24)+2k(M12)=38k
# Holdings bought: FE 14k(M60), ACM 8.5k(M48), IMM 7k(M36), OBLU+SCE 6k(M24)
- model: finance.investmentaccountcash
  pk: 10
  fields:
    created_at: {dt(M60)}
    updated_at: {dt(M60)}
    account_id: 2
    value: 1000
    value_currency: EUR
    value_date: {ds(M60)}
- model: finance.investmentaccountcash
  pk: 11
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    account_id: 2
    value: 500
    value_currency: EUR
    value_date: {ds(M48)}
- model: finance.investmentaccountcash
  pk: 12
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(M36)}
    account_id: 2
    value: 500
    value_currency: EUR
    value_date: {ds(M36)}
- model: finance.investmentaccountcash
  pk: 13
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    account_id: 2
    value: 500
    value_currency: EUR
    value_date: {ds(M24)}
- model: finance.investmentaccountcash
  pk: 14
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    account_id: 2
    value: 2500
    value_currency: EUR
    value_date: {ds(M12)}
- model: finance.investmentaccountcash
  pk: 15
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    account_id: 2
    value: 500
    value_currency: EUR
    value_date: {ds(RECENT)}
# ── Deposits: Assurance Vie ───────────────────────────────────────────────────
- model: finance.investmentaccountdeposit
  pk: 9
  fields:
    created_at: {dt(M60)}
    updated_at: {dt(M60)}
    account_id: 2
    amount: 15000
    amount_currency: EUR
    deposit_date: {ds(M60)}
    source: Virement bancaire
    update_account_cash: true
- model: finance.investmentaccountdeposit
  pk: 10
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    account_id: 2
    amount: 8000
    amount_currency: EUR
    deposit_date: {ds(M48)}
    source: Virement bancaire
    update_account_cash: true
- model: finance.investmentaccountdeposit
  pk: 11
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(M36)}
    account_id: 2
    amount: 7000
    amount_currency: EUR
    deposit_date: {ds(M36)}
    source: Virement bancaire
    update_account_cash: true
- model: finance.investmentaccountdeposit
  pk: 12
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    account_id: 2
    amount: 6000
    amount_currency: EUR
    deposit_date: {ds(M24)}
    source: Virement bancaire
    update_account_cash: true
- model: finance.investmentaccountdeposit
  pk: 13
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    account_id: 2
    amount: 2000
    amount_currency: EUR
    deposit_date: {ds(M12)}
    source: Virement bancaire
    update_account_cash: true
"""


def generate_savingaccount() -> str:
    """Generate savingaccount.yaml with dynamic dates.

    5 accounts totalling ~70k€:
      1 - Livret A Mister (Crédit Agricole):  ~24 000 € (opening 10 000)
      2 - LDDS Mister (Crédit Agricole):      ~12 800 € (opening 12 000)
      3 - Livret A Madame (Fortuneo):         ~17 600 € (opening 15 000)
      4 - PEL Commun (BNP Paribas):           ~ 8 200 € (opening  5 000)
      5 - CEL Commun (BNP Paribas):           ~ 7 500 € (opening  3 000)
    """
    return f"""# generated with scripts/generate_fixtures.py
---
# ── Account 1: Livret A — Mister ─────────────────────────────────────────────
- model: finance.savingaccount
  pk: 1
  fields:
    created_at: {dt(M60)}
    updated_at: {dt(RECENT)}
    account_type_id: 2
    name: Livret A
    owner: Mister
    institution: Crédit Apicole
    is_active: true
    opening_date: {ds(M60)}
    opening_value: 10000
    opening_value_currency: EUR
- model: finance.savingaccountvalue
  pk: 1
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(M36)}
    account_id: 1
    value: 12000
    value_currency: EUR
    value_date: {dt(M36)}
- model: finance.savingaccountvalue
  pk: 2
  fields:
    created_at: {dt(M30)}
    updated_at: {dt(M30)}
    account_id: 1
    value: 13500
    value_currency: EUR
    value_date: {dt(M30)}
- model: finance.savingaccountvalue
  pk: 3
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    account_id: 1
    value: 15500
    value_currency: EUR
    value_date: {dt(M24)}
- model: finance.savingaccountvalue
  pk: 4
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    account_id: 1
    value: 18000
    value_currency: EUR
    value_date: {dt(M18)}
- model: finance.savingaccountvalue
  pk: 5
  fields:
    created_at: {dt(M15)}
    updated_at: {dt(M15)}
    account_id: 1
    value: 19500
    value_currency: EUR
    value_date: {dt(M15)}
- model: finance.savingaccountvalue
  pk: 6
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    account_id: 1
    value: 21000
    value_currency: EUR
    value_date: {dt(M12)}
- model: finance.savingaccountvalue
  pk: 7
  fields:
    created_at: {dt(M9)}
    updated_at: {dt(M9)}
    account_id: 1
    value: 22200
    value_currency: EUR
    value_date: {dt(M9)}
- model: finance.savingaccountvalue
  pk: 8
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    account_id: 1
    value: 23000
    value_currency: EUR
    value_date: {dt(M6)}
- model: finance.savingaccountvalue
  pk: 9
  fields:
    created_at: {dt(M3)}
    updated_at: {dt(M3)}
    account_id: 1
    value: 23500
    value_currency: EUR
    value_date: {dt(M3)}
- model: finance.savingaccountvalue
  pk: 10
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    account_id: 1
    value: 24100
    value_currency: EUR
    value_date: {dt(RECENT)}
- model: finance.savingaccountdeposit
  pk: 1
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(M36)}
    account_id: 1
    amount: 2000
    amount_currency: EUR
    deposit_date: {dt(M36)}
    source: Virement mensuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 2
  fields:
    created_at: {dt(M30)}
    updated_at: {dt(M30)}
    account_id: 1
    amount: 1500
    amount_currency: EUR
    deposit_date: {dt(M30)}
    source: Virement mensuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 3
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    account_id: 1
    amount: 2000
    amount_currency: EUR
    deposit_date: {dt(M24)}
    source: Virement mensuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 4
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    account_id: 1
    amount: 2500
    amount_currency: EUR
    deposit_date: {dt(M18)}
    source: Virement mensuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 5
  fields:
    created_at: {dt(M15)}
    updated_at: {dt(M15)}
    account_id: 1
    amount: 1500
    amount_currency: EUR
    deposit_date: {dt(M15)}
    source: Virement mensuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 6
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    account_id: 1
    amount: 1500
    amount_currency: EUR
    deposit_date: {dt(M12)}
    source: Virement mensuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 7
  fields:
    created_at: {dt(M9)}
    updated_at: {dt(M9)}
    account_id: 1
    amount: 1200
    amount_currency: EUR
    deposit_date: {dt(M9)}
    source: Virement mensuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 8
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    account_id: 1
    amount: 800
    amount_currency: EUR
    deposit_date: {dt(M6)}
    source: Virement mensuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 9
  fields:
    created_at: {dt(M3)}
    updated_at: {dt(M3)}
    account_id: 1
    amount: 500
    amount_currency: EUR
    deposit_date: {dt(M3)}
    source: Virement mensuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 10
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    account_id: 1
    amount: 600
    amount_currency: EUR
    deposit_date: {dt(RECENT)}
    source: Virement mensuel
    update_account_value: true
# ── Account 2: LDDS — Mister ──────────────────────────────────────────────────
- model: finance.savingaccount
  pk: 2
  fields:
    created_at: {dt(M60)}
    updated_at: {dt(RECENT)}
    account_type_id: 4
    name: LDDS
    owner: Mister
    institution: Crédit Apicole
    is_active: true
    opening_date: {ds(M60)}
    opening_value: 12000
    opening_value_currency: EUR
- model: finance.savingaccountvalue
  pk: 11
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    account_id: 2
    value: 12000
    value_currency: EUR
    value_date: {dt(M18)}
- model: finance.savingaccountvalue
  pk: 12
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    account_id: 2
    value: 12200
    value_currency: EUR
    value_date: {dt(M12)}
- model: finance.savingaccountvalue
  pk: 13
  fields:
    created_at: {dt(M9)}
    updated_at: {dt(M9)}
    account_id: 2
    value: 12400
    value_currency: EUR
    value_date: {dt(M9)}
- model: finance.savingaccountvalue
  pk: 14
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    account_id: 2
    value: 12600
    value_currency: EUR
    value_date: {dt(M6)}
- model: finance.savingaccountvalue
  pk: 15
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    account_id: 2
    value: 12800
    value_currency: EUR
    value_date: {dt(RECENT)}
- model: finance.savingaccountdeposit
  pk: 11
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    account_id: 2
    amount: 200
    amount_currency: EUR
    deposit_date: {dt(M18)}
    source: Virement mensuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 12
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    account_id: 2
    amount: 200
    amount_currency: EUR
    deposit_date: {dt(M12)}
    source: Virement mensuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 13
  fields:
    created_at: {dt(M9)}
    updated_at: {dt(M9)}
    account_id: 2
    amount: 200
    amount_currency: EUR
    deposit_date: {dt(M9)}
    source: Virement mensuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 14
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    account_id: 2
    amount: 200
    amount_currency: EUR
    deposit_date: {dt(M6)}
    source: Virement mensuel
    update_account_value: true
# ── Account 3: Livret A — Madame ─────────────────────────────────────────────
- model: finance.savingaccount
  pk: 3
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(RECENT)}
    account_type_id: 2
    name: Livret A
    owner: Madame
    institution: FortuneBank
    is_active: true
    opening_date: {ds(M48)}
    opening_value: 15000
    opening_value_currency: EUR
- model: finance.savingaccountvalue
  pk: 16
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    account_id: 3
    value: 15000
    value_currency: EUR
    value_date: {dt(M24)}
- model: finance.savingaccountvalue
  pk: 17
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    account_id: 3
    value: 15800
    value_currency: EUR
    value_date: {dt(M18)}
- model: finance.savingaccountvalue
  pk: 18
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    account_id: 3
    value: 16400
    value_currency: EUR
    value_date: {dt(M12)}
- model: finance.savingaccountvalue
  pk: 19
  fields:
    created_at: {dt(M9)}
    updated_at: {dt(M9)}
    account_id: 3
    value: 16900
    value_currency: EUR
    value_date: {dt(M9)}
- model: finance.savingaccountvalue
  pk: 20
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    account_id: 3
    value: 17100
    value_currency: EUR
    value_date: {dt(M6)}
- model: finance.savingaccountvalue
  pk: 21
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    account_id: 3
    value: 17600
    value_currency: EUR
    value_date: {dt(RECENT)}
- model: finance.savingaccountdeposit
  pk: 15
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    account_id: 3
    amount: 500
    amount_currency: EUR
    deposit_date: {dt(M24)}
    source: Virement mensuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 16
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    account_id: 3
    amount: 800
    amount_currency: EUR
    deposit_date: {dt(M18)}
    source: Virement mensuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 17
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    account_id: 3
    amount: 600
    amount_currency: EUR
    deposit_date: {dt(M12)}
    source: Virement mensuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 18
  fields:
    created_at: {dt(M9)}
    updated_at: {dt(M9)}
    account_id: 3
    amount: 500
    amount_currency: EUR
    deposit_date: {dt(M9)}
    source: Virement mensuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 19
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    account_id: 3
    amount: 200
    amount_currency: EUR
    deposit_date: {dt(M6)}
    source: Virement mensuel
    update_account_value: true
# ── Account 4: PEL — Commun ───────────────────────────────────────────────────
- model: finance.savingaccount
  pk: 4
  fields:
    created_at: {dt(M72)}
    updated_at: {dt(RECENT)}
    account_type_id: 5
    name: PEL
    owner: Commun
    institution: FortuneBank
    is_active: true
    opening_date: {ds(M72)}
    opening_value: 5000
    opening_value_currency: EUR
- model: finance.savingaccountvalue
  pk: 22
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    account_id: 4
    value: 6800
    value_currency: EUR
    value_date: {dt(M24)}
- model: finance.savingaccountvalue
  pk: 23
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    account_id: 4
    value: 7200
    value_currency: EUR
    value_date: {dt(M18)}
- model: finance.savingaccountvalue
  pk: 24
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    account_id: 4
    value: 7600
    value_currency: EUR
    value_date: {dt(M12)}
- model: finance.savingaccountvalue
  pk: 25
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    account_id: 4
    value: 7900
    value_currency: EUR
    value_date: {dt(M6)}
- model: finance.savingaccountvalue
  pk: 26
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    account_id: 4
    value: 8200
    value_currency: EUR
    value_date: {dt(RECENT)}
- model: finance.savingaccountdeposit
  pk: 20
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(M36)}
    account_id: 4
    amount: 600
    amount_currency: EUR
    deposit_date: {dt(M36)}
    source: Virement annuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 21
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    account_id: 4
    amount: 600
    amount_currency: EUR
    deposit_date: {dt(M24)}
    source: Virement annuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 22
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    account_id: 4
    amount: 400
    amount_currency: EUR
    deposit_date: {dt(M18)}
    source: Virement annuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 23
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    account_id: 4
    amount: 400
    amount_currency: EUR
    deposit_date: {dt(M12)}
    source: Virement annuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 24
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    account_id: 4
    amount: 300
    amount_currency: EUR
    deposit_date: {dt(M6)}
    source: Virement annuel
    update_account_value: true
# ── Account 5: CEL — Commun ───────────────────────────────────────────────────
- model: finance.savingaccount
  pk: 5
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(RECENT)}
    account_type_id: 6
    name: CEL
    owner: Commun
    institution: FortuneBank
    is_active: true
    opening_date: {ds(M36)}
    opening_value: 3000
    opening_value_currency: EUR
- model: finance.savingaccountvalue
  pk: 27
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    account_id: 5
    value: 4000
    value_currency: EUR
    value_date: {dt(M24)}
- model: finance.savingaccountvalue
  pk: 28
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    account_id: 5
    value: 5000
    value_currency: EUR
    value_date: {dt(M18)}
- model: finance.savingaccountvalue
  pk: 29
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    account_id: 5
    value: 6000
    value_currency: EUR
    value_date: {dt(M12)}
- model: finance.savingaccountvalue
  pk: 30
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    account_id: 5
    value: 7000
    value_currency: EUR
    value_date: {dt(M6)}
- model: finance.savingaccountvalue
  pk: 31
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    account_id: 5
    value: 7500
    value_currency: EUR
    value_date: {dt(RECENT)}
- model: finance.savingaccountdeposit
  pk: 25
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    account_id: 5
    amount: 1000
    amount_currency: EUR
    deposit_date: {dt(M24)}
    source: Virement mensuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 26
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    account_id: 5
    amount: 1000
    amount_currency: EUR
    deposit_date: {dt(M18)}
    source: Virement mensuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 27
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    account_id: 5
    amount: 1000
    amount_currency: EUR
    deposit_date: {dt(M12)}
    source: Virement mensuel
    update_account_value: true
- model: finance.savingaccountdeposit
  pk: 28
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    account_id: 5
    amount: 1000
    amount_currency: EUR
    deposit_date: {dt(M6)}
    source: Virement mensuel
    update_account_value: true
"""


def generate_scpi() -> str:
    """Generate scpi.yaml with 3 SCPI investments.

    SCPI 1: PierPap Basic — 20k€, full ownership, 3 years ago, quarterly dividends 4-6%
    SCPI 2: PierPap Full — 10k€, full ownership, 18 months ago, monthly dividends 3-5%
    SCPI 3: NosBureaux — 15k€, bare ownership (nue-propriété), 2 years ago
    """
    return f"""# generated with scripts/generate_fixtures.py
---
# ── SCPI 1: PierPap (full ownership, quarterly dividends) ─────────────────
- model: property.scpi
  pk: 1
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(RECENT)}
    name: PierPap Basic
    management_company: PierPap
    entry_fee_rate: "9.1230"
    exit_fee_rate: "0.0000"
    management_fee_rate: "10.0000"
    notes: ""
    dividend_recurrence: quarterly
- model: property.scpishareprice
  pk: 1
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(M36)}
    scpi: 1
    date: {ds(M36)}
    subscription_value: 200.00
    subscription_value_currency: EUR
    withdrawal_value: null
    withdrawal_value_currency: EUR
- model: property.scpishareprice
  pk: 2
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    scpi: 1
    date: {ds(M18)}
    subscription_value: 202.00
    subscription_value_currency: EUR
    withdrawal_value: null
    withdrawal_value_currency: EUR
- model: property.scpishareprice
  pk: 3
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    scpi: 1
    date: {ds(RECENT)}
    subscription_value: 208.00
    subscription_value_currency: EUR
    withdrawal_value: null
    withdrawal_value_currency: EUR
# Investment: 100 shares × 200€ = 20 000€ total invested
- model: property.scpiinvestment
  pk: 1
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(RECENT)}
    scpi: 1
    subscription_date: {ds(M36)}
    shares_count: "100.0000"
    unit_purchase_price: 200.00
    unit_purchase_price_currency: EUR
    enjoyment_date: {ds(M33)}
    ownership_type: full
    dismemberment_start_date: null
    dismemberment_end_date: null
    bare_ownership_ratio: null
    notes: ""
# Quarterly dividends (11 payments) — ~5% annual = 100 × 200 × 5% / 4 = 250€/quarter
- model: property.scpidividend
  pk: 1
  fields:
    created_at: {dt(M33)}
    updated_at: {dt(M33)}
    scpi: 1
    payment_date: {ds(M33)}
    gross_amount: 285.00
    gross_amount_currency: EUR
    net_amount: 245.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 2
  fields:
    created_at: {dt(M30)}
    updated_at: {dt(M30)}
    scpi: 1
    payment_date: {ds(M30)}
    gross_amount: 293.00
    gross_amount_currency: EUR
    net_amount: 252.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 3
  fields:
    created_at: {dt(M27)}
    updated_at: {dt(M27)}
    scpi: 1
    payment_date: {ds(M27)}
    gross_amount: 298.00
    gross_amount_currency: EUR
    net_amount: 256.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 4
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    scpi: 1
    payment_date: {ds(M24)}
    gross_amount: 289.00
    gross_amount_currency: EUR
    net_amount: 248.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 5
  fields:
    created_at: {dt(M21)}
    updated_at: {dt(M21)}
    scpi: 1
    payment_date: {ds(M21)}
    gross_amount: 302.00
    gross_amount_currency: EUR
    net_amount: 260.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 6
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    scpi: 1
    payment_date: {ds(M18)}
    gross_amount: 293.00
    gross_amount_currency: EUR
    net_amount: 252.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 7
  fields:
    created_at: {dt(M15)}
    updated_at: {dt(M15)}
    scpi: 1
    payment_date: {ds(M15)}
    gross_amount: 285.00
    gross_amount_currency: EUR
    net_amount: 245.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 8
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    scpi: 1
    payment_date: {ds(M12)}
    gross_amount: 300.00
    gross_amount_currency: EUR
    net_amount: 258.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 9
  fields:
    created_at: {dt(M9)}
    updated_at: {dt(M9)}
    scpi: 1
    payment_date: {ds(M9)}
    gross_amount: 291.00
    gross_amount_currency: EUR
    net_amount: 250.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 10
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    scpi: 1
    payment_date: {ds(M6)}
    gross_amount: 297.00
    gross_amount_currency: EUR
    net_amount: 255.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 11
  fields:
    created_at: {dt(M3)}
    updated_at: {dt(M3)}
    scpi: 1
    payment_date: {ds(M3)}
    gross_amount: 289.00
    gross_amount_currency: EUR
    net_amount: 248.00
    net_amount_currency: EUR
    notes: ""
# ── SCPI 2: PierPap Full (full ownership, monthly dividends) ──────────────
- model: property.scpi
  pk: 2
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(RECENT)}
    name: PierPap Full
    management_company: PierPap
    entry_fee_rate: "9.00"
    exit_fee_rate: "0.00"
    management_fee_rate: "9.50"
    notes: ""
    dividend_recurrence: monthly
- model: property.scpishareprice
  pk: 4
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    scpi: 2
    date: {ds(M18)}
    subscription_value: 1000.00
    subscription_value_currency: EUR
    withdrawal_value: null
    withdrawal_value_currency: EUR
- model: property.scpishareprice
  pk: 5
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    scpi: 2
    date: {ds(RECENT)}
    subscription_value: 1020.00
    subscription_value_currency: EUR
    withdrawal_value: null
    withdrawal_value_currency: EUR
# Investment: 10 shares × 1000€ = 10 000€ total invested
- model: property.scpiinvestment
  pk: 2
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(RECENT)}
    scpi: 2
    subscription_date: {ds(M18)}
    shares_count: "10.0000"
    unit_purchase_price: 1000.00
    unit_purchase_price_currency: EUR
    enjoyment_date: {ds(M14)}
    ownership_type: full
    dismemberment_start_date: null
    dismemberment_end_date: null
    bare_ownership_ratio: null
    notes: ""
# Monthly dividends (14 payments from M14) — ~4% annual = 10000 × 4% / 12 ≈ 33€/month
- model: property.scpidividend
  pk: 12
  fields:
    created_at: {dt(M14)}
    updated_at: {dt(M14)}
    scpi: 2
    payment_date: {ds(M14)}
    gross_amount: 40.00
    gross_amount_currency: EUR
    net_amount: 34.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 13
  fields:
    created_at: {dt(M13)}
    updated_at: {dt(M13)}
    scpi: 2
    payment_date: {ds(M13)}
    gross_amount: 38.00
    gross_amount_currency: EUR
    net_amount: 33.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 14
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    scpi: 2
    payment_date: {ds(M12)}
    gross_amount: 42.00
    gross_amount_currency: EUR
    net_amount: 36.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 15
  fields:
    created_at: {dt(M11)}
    updated_at: {dt(M11)}
    scpi: 2
    payment_date: {ds(M11)}
    gross_amount: 39.00
    gross_amount_currency: EUR
    net_amount: 34.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 16
  fields:
    created_at: {dt(M10)}
    updated_at: {dt(M10)}
    scpi: 2
    payment_date: {ds(M10)}
    gross_amount: 41.00
    gross_amount_currency: EUR
    net_amount: 35.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 17
  fields:
    created_at: {dt(M9)}
    updated_at: {dt(M9)}
    scpi: 2
    payment_date: {ds(M9)}
    gross_amount: 38.00
    gross_amount_currency: EUR
    net_amount: 33.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 18
  fields:
    created_at: {dt(M8)}
    updated_at: {dt(M8)}
    scpi: 2
    payment_date: {ds(M8)}
    gross_amount: 43.00
    gross_amount_currency: EUR
    net_amount: 37.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 19
  fields:
    created_at: {dt(M7)}
    updated_at: {dt(M7)}
    scpi: 2
    payment_date: {ds(M7)}
    gross_amount: 40.00
    gross_amount_currency: EUR
    net_amount: 34.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 20
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    scpi: 2
    payment_date: {ds(M6)}
    gross_amount: 41.00
    gross_amount_currency: EUR
    net_amount: 36.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 21
  fields:
    created_at: {dt(M5)}
    updated_at: {dt(M5)}
    scpi: 2
    payment_date: {ds(M5)}
    gross_amount: 39.00
    gross_amount_currency: EUR
    net_amount: 34.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 22
  fields:
    created_at: {dt(M4)}
    updated_at: {dt(M4)}
    scpi: 2
    payment_date: {ds(M4)}
    gross_amount: 44.00
    gross_amount_currency: EUR
    net_amount: 38.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 23
  fields:
    created_at: {dt(M3)}
    updated_at: {dt(M3)}
    scpi: 2
    payment_date: {ds(M3)}
    gross_amount: 40.00
    gross_amount_currency: EUR
    net_amount: 34.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 24
  fields:
    created_at: {dt(M2)}
    updated_at: {dt(M2)}
    scpi: 2
    payment_date: {ds(M2)}
    gross_amount: 38.00
    gross_amount_currency: EUR
    net_amount: 33.00
    net_amount_currency: EUR
    notes: ""
- model: property.scpidividend
  pk: 25
  fields:
    created_at: {dt(M1)}
    updated_at: {dt(M1)}
    scpi: 2
    payment_date: {ds(M1)}
    gross_amount: 42.00
    gross_amount_currency: EUR
    net_amount: 36.00
    net_amount_currency: EUR
    notes: ""
# ── SCPI 3: NosBureaux (nue-propriété, no dividends) ────────────────────
- model: property.scpi
  pk: 3
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(RECENT)}
    name: NosBureaux
    management_company: NosBureaux
    entry_fee_rate: "10.00"
    exit_fee_rate: "0.00"
    management_fee_rate: "12.00"
    notes: ""
    dividend_recurrence: quarterly
- model: property.scpishareprice
  pk: 6
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    scpi: 3
    date: {ds(M24)}
    subscription_value: 200.00
    subscription_value_currency: EUR
    withdrawal_value: null
    withdrawal_value_currency: EUR
- model: property.scpishareprice
  pk: 7
  fields:
    created_at: {dt(RECENT)}
    updated_at: {dt(RECENT)}
    scpi: 3
    date: {ds(RECENT)}
    subscription_value: 202.00
    subscription_value_currency: EUR
    withdrawal_value: null
    withdrawal_value_currency: EUR
# Investment: 100 shares × 150€ (bare ownership = 75% of 200€) = 15 000€ total invested
- model: property.scpiinvestment
  pk: 3
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(RECENT)}
    scpi: 3
    subscription_date: {ds(M24)}
    shares_count: "100.0000"
    unit_purchase_price: 150.00
    unit_purchase_price_currency: EUR
    enjoyment_date: null
    ownership_type: bare
    dismemberment_start_date: {ds(M24)}
    dismemberment_end_date: {ds(SCPI3_RECO)}
    bare_ownership_ratio: "75.00"
    notes: "Démembrement 10 ans — reconstitution prévue en {SCPI3_RECO}"
"""


def generate_property() -> str:  # noqa: PLR0915
    """Generate property.yaml with dynamic dates.

    Properties:
      1 - Résidence principale (HO): 1 standard 20-year loan, typical owner expenses
      2 - Appartement locatif Nice (AP): 2 smoothed loans (prêt lisseur, 10y + 20y),
          active lease, full rental transactions, LMNP réel tax regime with amortization
      3 - Studio meublé Lyon (AP): 1 short loan ending in ~4 years, active lease,
          rental transactions with tenant and lease, LMNP réel tax regime with amortization
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
    notary_fees: 24000.00
    notary_fees_currency: EUR
    agency_fees: 10000.00
    agency_fees_currency: EUR
    other_fees: null
    other_fees_currency: EUR
    credit_fees: null
    credit_fees_currency: EUR
    buying_date: {ds(M96)}
    selling_date: null
    floor_area: "112.50"
    tax_regime: none
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
    is_favorite: true
    buying_value: 185000.00
    buying_value_currency: EUR
    notary_fees: 14000.00
    notary_fees_currency: EUR
    agency_fees: null
    agency_fees_currency: EUR
    other_fees: null
    other_fees_currency: EUR
    credit_fees: 800.00
    credit_fees_currency: EUR
    buying_date: {ds(M48)}
    selling_date: null
    floor_area: "42.00"
    tax_regime: lmnp_reel
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
# Amortization entries — Loan 2A (80 000 EUR, 2.95 %, 120 months)
- model: property.propertyloanamortizationentry
  pk: 1
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    loan: 2
    date: {ds(M48)}
    capital: 574.46
    capital_currency: EUR
    interest: 196.67
    interest_currency: EUR
    remaining_balance_amount: 79425.54
    remaining_balance_amount_currency: EUR
- model: property.propertyloanamortizationentry
  pk: 2
  fields:
    created_at: {dt(M47)}
    updated_at: {dt(M47)}
    loan: 2
    date: {ds(M47)}
    capital: 575.87
    capital_currency: EUR
    interest: 195.26
    interest_currency: EUR
    remaining_balance_amount: 78849.67
    remaining_balance_amount_currency: EUR
- model: property.propertyloanamortizationentry
  pk: 3
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    loan: 2
    date: {ds(M12)}
    capital: 626.86
    capital_currency: EUR
    interest: 144.27
    interest_currency: EUR
    remaining_balance_amount: 58065.14
    remaining_balance_amount_currency: EUR
- model: property.propertyloanamortizationentry
  pk: 4
  fields:
    created_at: {dt(M1)}
    updated_at: {dt(M1)}
    loan: 2
    date: {ds(M1)}
    capital: 643.03
    capital_currency: EUR
    interest: 128.10
    interest_currency: EUR
    remaining_balance_amount: 51473.11
    remaining_balance_amount_currency: EUR
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
# Amortization entries — Loan 2B (105 000 EUR, 3.10 %, 240 months)
- model: property.propertyloanamortizationentry
  pk: 5
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    loan: 3
    date: {ds(M48)}
    capital: 316.42
    capital_currency: EUR
    interest: 271.25
    interest_currency: EUR
    remaining_balance_amount: 104683.58
    remaining_balance_amount_currency: EUR
- model: property.propertyloanamortizationentry
  pk: 6
  fields:
    created_at: {dt(M47)}
    updated_at: {dt(M47)}
    loan: 3
    date: {ds(M47)}
    capital: 317.24
    capital_currency: EUR
    interest: 270.43
    interest_currency: EUR
    remaining_balance_amount: 104366.34
    remaining_balance_amount_currency: EUR
- model: property.propertyloanamortizationentry
  pk: 7
  fields:
    created_at: {dt(M12)}
    updated_at: {dt(M12)}
    loan: 3
    date: {ds(M12)}
    capital: 347.05
    capital_currency: EUR
    interest: 240.62
    interest_currency: EUR
    remaining_balance_amount: 92806.95
    remaining_balance_amount_currency: EUR
- model: property.propertyloanamortizationentry
  pk: 8
  fields:
    created_at: {dt(M1)}
    updated_at: {dt(M1)}
    loan: 3
    date: {ds(M1)}
    capital: 356.07
    capital_currency: EUR
    interest: 231.60
    interest_currency: EUR
    remaining_balance_amount: 89277.93
    remaining_balance_amount_currency: EUR
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
    is_favorite: true
    buying_value: 95000.00
    buying_value_currency: EUR
    notary_fees: 7500.00
    notary_fees_currency: EUR
    agency_fees: null
    agency_fees_currency: EUR
    other_fees: null
    other_fees_currency: EUR
    credit_fees: null
    credit_fees_currency: EUR
    buying_date: {ds(M48)}
    selling_date: null
    floor_area: "22.00"
    tax_regime: lmnp_reel
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
    notary_fees: null
    notary_fees_currency: EUR
    agency_fees: null
    agency_fees_currency: EUR
    other_fees: null
    other_fees_currency: EUR
    credit_fees: null
    credit_fees_currency: EUR
    buying_date: {ds(M72)}
    selling_date: null
    floor_area: "95.00"
    tax_regime: none
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
- model: property.propertyledgerentry
  pk: 28
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(M36)}
    property: 2
    lease: 1
    flow_type: expense
    amount: 950.00
    amount_currency: EUR
    entry_date: {ds(M36)}
    reference_period: null
    management_category: letting_fees
    description: Frais de mise en location
    notes: "Honoraires agence — entrée locataire"
    recurrence_type: none
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 29
  fields:
    created_at: {dt(M36)}
    updated_at: {dt(M36)}
    property: 2
    lease: null
    flow_type: expense
    amount: 180.00
    amount_currency: EUR
    entry_date: {ds(M36)}
    reference_period: null
    management_category: rental_guarantee
    description: Assurance loyers impayés (GLI)
    notes: ""
    recurrence_type: yearly
    recurrence_end_date: null
- model: property.propertyledgerentry
  pk: 30
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    property: 3
    lease: null
    flow_type: expense
    amount: 240.00
    amount_currency: EUR
    entry_date: {ds(M24)}
    reference_period: null
    management_category: coownership
    description: Charges de copropriété trimestrielles
    notes: ""
    recurrence_type: quarterly
    recurrence_end_date: null

# ─────────────────────────────────────────────────────────────────────────────
# LMNP RÉEL — Appartement locatif Nice (property 2)
#   AmortizationSetup: total_value = buying price, land = 15 %
#   Depreciable base = 85 % × 185 000 = 157 250 EUR
#   Standard components (% of depreciable base, duration in years):
#     structure      45 % × 157 250 = 70 762.50 EUR  /  75 ans
#     electrical      6 % × 157 250 =  9 435.00 EUR  /  30 ans
#     waterproofing   7 % × 157 250 = 11 007.50 EUR  /  25 ans
#     roof            8 % × 157 250 = 12 580.00 EUR  /  25 ans
#     fittings       19 % × 157 250 = 29 877.50 EUR  /  12 ans
#   Extra immobilisation: cuisine équipée (2 400 EUR / 10 ans)
# ─────────────────────────────────────────────────────────────────────────────
- model: property.amortizationsetup
  pk: 1
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 2
    total_value: 185000.00
    total_value_currency: EUR
    land_percentage: "15.00"
- model: property.amortizationasset
  pk: 1
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 2
    label: Gros œuvre
    beginning_date: {ds(M48)}
    value_total: 70762.50
    value_total_currency: EUR
    duration_years: 75
    is_initial_component: true
- model: property.amortizationasset
  pk: 2
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 2
    label: Installations électriques
    beginning_date: {ds(M48)}
    value_total: 9435.00
    value_total_currency: EUR
    duration_years: 30
    is_initial_component: true
- model: property.amortizationasset
  pk: 3
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 2
    label: Étanchéité
    beginning_date: {ds(M48)}
    value_total: 11007.50
    value_total_currency: EUR
    duration_years: 25
    is_initial_component: true
- model: property.amortizationasset
  pk: 4
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 2
    label: Toiture
    beginning_date: {ds(M48)}
    value_total: 12580.00
    value_total_currency: EUR
    duration_years: 25
    is_initial_component: true
- model: property.amortizationasset
  pk: 5
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 2
    label: Agencements intérieurs
    beginning_date: {ds(M48)}
    value_total: 29877.50
    value_total_currency: EUR
    duration_years: 12
    is_initial_component: true
- model: property.amortizationasset
  pk: 6
  fields:
    created_at: {dt(M24)}
    updated_at: {dt(M24)}
    property: 2
    label: Cuisine équipée
    beginning_date: {ds(M24)}
    value_total: 2400.00
    value_total_currency: EUR
    duration_years: 10
    is_initial_component: false

# ─────────────────────────────────────────────────────────────────────────────
# LMNP RÉEL — Studio meublé Lyon (property 3)
#   AmortizationSetup: total_value = buying price, land = 15 %
#   Depreciable base = 85 % × 95 000 = 80 750 EUR
#   Standard components (% of depreciable base, duration in years):
#     structure      45 % × 80 750 = 36 337.50 EUR  /  75 ans
#     electrical      6 % × 80 750 =  4 845.00 EUR  /  30 ans
#     waterproofing   7 % × 80 750 =  5 652.50 EUR  /  25 ans
#     roof            8 % × 80 750 =  6 460.00 EUR  /  25 ans
#     fittings       19 % × 80 750 = 15 342.50 EUR  /  12 ans
#   Extra immobilisation: mobilier et électroménager (3 800 EUR / 7 ans)
# ─────────────────────────────────────────────────────────────────────────────
- model: property.amortizationsetup
  pk: 2
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 3
    total_value: 95000.00
    total_value_currency: EUR
    land_percentage: "15.00"
- model: property.amortizationasset
  pk: 7
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 3
    label: Gros œuvre
    beginning_date: {ds(M48)}
    value_total: 36337.50
    value_total_currency: EUR
    duration_years: 75
    is_initial_component: true
- model: property.amortizationasset
  pk: 8
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 3
    label: Installations électriques
    beginning_date: {ds(M48)}
    value_total: 4845.00
    value_total_currency: EUR
    duration_years: 30
    is_initial_component: true
- model: property.amortizationasset
  pk: 9
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 3
    label: Étanchéité
    beginning_date: {ds(M48)}
    value_total: 5652.50
    value_total_currency: EUR
    duration_years: 25
    is_initial_component: true
- model: property.amortizationasset
  pk: 10
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 3
    label: Toiture
    beginning_date: {ds(M48)}
    value_total: 6460.00
    value_total_currency: EUR
    duration_years: 25
    is_initial_component: true
- model: property.amortizationasset
  pk: 11
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 3
    label: Agencements intérieurs
    beginning_date: {ds(M48)}
    value_total: 15342.50
    value_total_currency: EUR
    duration_years: 12
    is_initial_component: true
- model: property.amortizationasset
  pk: 12
  fields:
    created_at: {dt(M48)}
    updated_at: {dt(M48)}
    property: 3
    label: Mobilier et électroménager
    beginning_date: {ds(M48)}
    value_total: 3800.00
    value_total_currency: EUR
    duration_years: 7
    is_initial_component: false

# ─────────────────────────────────────────────────────────────────────────────
# LEDGER ENTRY EXCEPTIONS
#   Occurrence overrides for recurring entries
#   - Exception 1: entry 6 (monthly rent, property 2) — one month deleted (waived)
#   - Exception 2: entry 15 (monthly rent, property 3) — amount override (rent increase)
# ─────────────────────────────────────────────────────────────────────────────
- model: property.propertyledgerentryexception
  pk: 1
  fields:
    created_at: {dt(M18)}
    updated_at: {dt(M18)}
    parent_entry: 6
    occurrence_date: {ds(M18)}
    is_deleted: true
    amount_override: null
    amount_override_currency: EUR
    description_override: null
    notes_override: null
- model: property.propertyledgerentryexception
  pk: 2
  fields:
    created_at: {dt(M6)}
    updated_at: {dt(M6)}
    parent_entry: 15
    occurrence_date: {ds(M6)}
    is_deleted: false
    amount_override: 545.00
    amount_override_currency: EUR
    description_override: Loyer mensuel (indexé)
    notes_override: Revalorisation IRL janvier
"""


def main() -> None:
    """Generate all test fixture files."""
    print("Generating dynamic test fixtures...")
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    write_fixture("investmentaccount.yaml", generate_investmentaccount())
    write_fixture("savingaccount.yaml", generate_savingaccount())
    write_fixture("scpi.yaml", generate_scpi())
    write_fixture("property.yaml", generate_property())
    print("Done.")


if __name__ == "__main__":
    main()
