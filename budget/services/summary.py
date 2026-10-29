"""The budget of a year as three trees (resources, expenses, savings) and indicators.

Each tree mixes the budget lines, grouped by category, and the flows read
from the rest of the application (properties, SCPI, accounts). Every node has
a key stable from one year to the next, so two years can be compared node by
node.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import NamedTuple

from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import pgettext

from base.models import display_name
from base.services.ownership import HolderResolver
from budget.models import BudgetCategory, BudgetKind, BudgetLine, BudgetYear
from budget.services.finance_flows import (
    AccountFlows,
    FinanceFlows,
    Movement,
    account_year_flows,
)
from budget.services.perspective import Perspective
from budget.services.property_flows import (
    PropertyFlows,
    SCPIFlows,
    property_year_flows,
    scpi_year_flows,
)
from finance.models.base import DepositOrigin
from property.models.ledger import ManagementCategory

#: Share of the rents and SCPI dividends banks count as income in the debt
#: ratio (HCSF recommendation).
RENT_WEIGHT = Decimal("0.7")
#: Highest debt ratio recommended by the HCSF, in percent.
DEBT_RATIO_LIMIT = Decimal(35)
#: Keys of the groups of the account flows: deposits on the saving and on the
#: investment accounts, withdrawals, exceptional and employer deposits.
ACCOUNT_DEPOSITS = "auto:accounts:deposits"
ACCOUNT_INVESTMENTS = "auto:accounts:investments"
ACCOUNT_WITHDRAWALS = "auto:accounts:withdrawals"
ACCOUNT_EXCEPTIONAL = "auto:accounts:exceptional"
ACCOUNT_EMPLOYER = "auto:accounts:employer"


@dataclass
class BudgetNode:
    """A category, a budget line or an automatic flow of the budget."""

    key: str
    label: str
    kind: str
    #: "category", "line", "auto" (property, SCPI, account flows) or "balance".
    source: str
    amount: Decimal = Decimal(0)
    children: list[BudgetNode] = field(default_factory=list)
    url: str = ""
    line: BudgetLine | None = None
    person: str = ""
    #: Total of the same node in the previous year, set by the comparison.
    previous: Decimal | None = None

    @property
    def total(self) -> Decimal:
        """Own amount plus the total of the children."""
        return self.amount + sum((c.total for c in self.children), Decimal(0))

    @property
    def monthly(self) -> Decimal:
        """Total divided by 12."""
        return self.total / 12

    @property
    def delta(self) -> Decimal | None:
        """Change from the previous year, None without previous year."""
        if self.previous is None:
            return None
        return self.total - self.previous

    @property
    def delta_percent(self) -> Decimal | None:
        """Change from the previous year in percent, None without base."""
        if not self.previous:
            return None
        return (self.total - self.previous) / self.previous * 100

    @property
    def delta_tone(self) -> str:
        """CSS class of the change: a rise is good for income and savings only."""
        delta = self.delta
        if not delta:
            return ""
        good = delta < 0 if self.kind == BudgetKind.EXPENSE else delta > 0
        return "g-pos" if good else "g-neg"

    def walk(self):
        """This node and every node below it."""
        yield self
        for child in self.children:
            yield from child.walk()

    def prune(self) -> None:
        """Drop the children whose total is zero, recursively."""
        for child in self.children:
            child.prune()
        self.children = [c for c in self.children if c.total or c.line is not None]


@dataclass
class Indicators:
    """Key figures of a budget."""

    income: Decimal
    expenses: Decimal
    savings: Decimal
    withdrawals: Decimal
    principal: Decimal
    debt_payments: Decimal
    debt_income: Decimal
    #: Exceptional deposits (sale, inheritance, gift) spent by the household,
    #: outside the income.
    exceptional: Decimal = Decimal(0)

    @property
    def monthly_income(self) -> Decimal:
        """Income divided by 12."""
        return self.income / 12

    @property
    def monthly_expenses(self) -> Decimal:
        """Expenses divided by 12."""
        return self.expenses / 12

    @property
    def capacity(self) -> Decimal:
        """Income left after the expenses, available to save."""
        return self.income - self.expenses

    @property
    def balance(self) -> Decimal:
        """Money left once the savings are made (negative for a deficit)."""
        return (
            self.income
            + self.withdrawals
            + self.exceptional
            - self.expenses
            - self.savings
        )

    @property
    def savings_rate(self) -> Decimal | None:
        """Savings capacity in percent of the income."""
        return self.capacity / self.income * 100 if self.income else None

    @property
    def enrichment_rate(self) -> Decimal | None:
        """Savings capacity plus the loan principal repaid, in percent of the income."""
        if not self.income:
            return None
        return (self.capacity + self.principal) / self.income * 100

    @property
    def debt_ratio(self) -> Decimal | None:
        """Loan installments in percent of the income as banks count it."""
        if not self.debt_income:
            return None
        return self.debt_payments / self.debt_income * 100

    @property
    def debt_ratio_exceeded(self) -> bool:
        """True above the HCSF limit."""
        ratio = self.debt_ratio
        return ratio is not None and ratio > DEBT_RATIO_LIMIT

    @property
    def monthly_left_to_live(self) -> Decimal:
        """Monthly income left after the loan installments."""
        return (self.income - self.debt_payments) / 12


@dataclass
class BudgetSummary:
    """The budget of a year seen from a perspective."""

    budget_year: BudgetYear
    perspective: Perspective
    currency: str
    resources: list[BudgetNode]
    expenses: list[BudgetNode]
    savings: list[BudgetNode]
    indicators: Indicators
    #: Remaining money (positive) or deficit (negative) node, if any.
    balance: BudgetNode | None = None
    has_previous: bool = False
    #: Account movements of unknown origin, whose origin was guessed.
    guesses: list[Movement] = field(default_factory=list)

    @property
    def guessed_transfers(self) -> int:
        """Movements of unknown origin taken as transfers between accounts."""
        return sum(1 for m in self.guesses if m.guessed == DepositOrigin.TRANSFER)

    @property
    def guessed_income(self) -> int:
        """Movements of unknown origin taken as savings from the income."""
        return len(self.guesses) - self.guessed_transfers

    def nodes(self):
        """Every node of the three trees."""
        for root in [*self.resources, *self.expenses, *self.savings]:
            yield from root.walk()
        if self.balance is not None:
            yield self.balance

    @property
    def resources_total(self) -> Decimal:
        """Income plus the withdrawals from savings and the exceptional deposits."""
        return sum((n.total for n in self.resources), Decimal(0))

    @property
    def expenses_total(self) -> Decimal:
        """Every expense."""
        return sum((n.total for n in self.expenses), Decimal(0))

    @property
    def savings_total(self) -> Decimal:
        """Every saving."""
        return sum((n.total for n in self.savings), Decimal(0))


# ─── Budget lines ─────────────────────────────────────────────────────────────


def _category_nodes(
    categories: list[BudgetCategory],
    lines: list[BudgetLine],
    perspective: Perspective,
    names: dict[int, str],
) -> dict[str, list[BudgetNode]]:
    """Root category nodes of each kind, holding their sub-categories and lines."""
    nodes = {
        c.pk: BudgetNode(
            key=f"category:{c.pk}", label=c.name, kind=c.kind, source="category"
        )
        for c in categories
    }
    for line in lines:
        ratio = perspective.line_ratio(line.person_id)
        if not ratio:
            continue
        parent = nodes[line.category_id]
        person = names.get(line.person_id, "") if line.person_id else ""
        parent.children.append(
            BudgetNode(
                key=f"line:{line.category_id}:{line.label.strip().lower()}:{line.person_id or ''}",
                label=line.label,
                kind=parent.kind,
                source="line",
                amount=line.amount.amount * ratio,
                line=line,
                person=person or _("Household"),
            )
        )
    roots: dict[str, list[BudgetNode]] = {kind: [] for kind in BudgetKind.values}
    for category in sorted(categories, key=lambda c: (c.position, c.name.lower())):
        node = nodes[category.pk]
        if category.parent_id is None:
            roots[category.kind].append(node)
        else:
            nodes[category.parent_id].children.insert(
                sum(
                    1
                    for c in nodes[category.parent_id].children
                    if c.source == "category"
                ),
                node,
            )
    return roots


# ─── Automatic flows ──────────────────────────────────────────────────────────


def _property_nodes(flows: list[PropertyFlows]) -> tuple[BudgetNode, BudgetNode]:
    """Income and expense groups of the properties."""
    income = BudgetNode(
        key="auto:properties:income",
        label=_("Real estate"),
        kind=BudgetKind.INCOME,
        source="auto",
    )
    expenses = BudgetNode(
        key="auto:properties:expense",
        label=_("Real estate"),
        kind=BudgetKind.EXPENSE,
        source="auto",
    )
    for item in flows:
        prop = item.property
        url = reverse("property:detail", kwargs={"pk": prop.pk})
        income_node = BudgetNode(
            key=f"auto:property:{prop.pk}:income",
            label=prop.name,
            kind=BudgetKind.INCOME,
            source="auto",
            url=url,
            children=[
                BudgetNode(
                    key=f"auto:property:{prop.pk}:income:{cat}",
                    label=ManagementCategory(cat).label,
                    kind=BudgetKind.INCOME,
                    source="auto",
                    amount=amount,
                )
                for cat, amount in sorted(item.income.items(), key=lambda kv: -kv[1])
            ],
        )
        loan_parts = [
            ("principal", _("Loan principal"), item.loan.principal),
            ("interest", _("Loan interest"), item.loan.interest),
            ("insurance", _("Loan insurance"), item.loan.insurance),
        ]
        expense_node = BudgetNode(
            key=f"auto:property:{prop.pk}:expense",
            label=prop.name,
            kind=BudgetKind.EXPENSE,
            source="auto",
            url=url,
            children=[
                BudgetNode(
                    key=f"auto:property:{prop.pk}:loan:{part}",
                    label=label,
                    kind=BudgetKind.EXPENSE,
                    source="auto",
                    amount=amount,
                )
                for part, label, amount in loan_parts
            ]
            + [
                BudgetNode(
                    key=f"auto:property:{prop.pk}:expense:{cat}",
                    label=ManagementCategory(cat).label,
                    kind=BudgetKind.EXPENSE,
                    source="auto",
                    amount=amount,
                )
                for cat, amount in sorted(item.expenses.items(), key=lambda kv: -kv[1])
            ],
        )
        income.children.append(income_node)
        expenses.children.append(expense_node)
    return income, expenses


def _scpi_nodes(flows: list[SCPIFlows]) -> tuple[BudgetNode, BudgetNode]:
    """Dividends (income) and subscriptions (savings) of the SCPI funds."""
    dividends = BudgetNode(
        key="auto:scpi:dividends",
        label=_("SCPI dividends"),
        kind=BudgetKind.INCOME,
        source="auto",
    )
    subscriptions = BudgetNode(
        key="auto:scpi:subscriptions",
        label=_("SCPI subscriptions"),
        kind=BudgetKind.SAVING,
        source="auto",
    )
    for item in flows:
        url = reverse("property:scpi_fund_detail", kwargs={"scpi_pk": item.scpi.pk})
        dividends.children.append(
            BudgetNode(
                key=f"auto:scpi:{item.scpi.pk}:dividends",
                label=item.scpi.name,
                kind=BudgetKind.INCOME,
                source="auto",
                amount=item.dividends,
                url=url,
            )
        )
        subscriptions.children.append(
            BudgetNode(
                key=f"auto:scpi:{item.scpi.pk}:subscriptions",
                label=item.scpi.name,
                kind=BudgetKind.SAVING,
                source="auto",
                amount=item.subscriptions,
                url=url,
            )
        )
    return dividends, subscriptions


class AccountGroups(NamedTuple):
    """Groups of the account flows, each holding one node per account."""

    #: Deposits on the saving accounts.
    savings: BudgetNode
    #: Deposits on the investment accounts.
    investments: BudgetNode
    withdrawals: BudgetNode
    #: Exceptional deposits spent by the household.
    exceptional: BudgetNode
    #: Deposits of the employer, income saved on the account.
    employer: BudgetNode


def _account_nodes(flows: list[AccountFlows]) -> AccountGroups:
    """Deposits (savings) and withdrawals, exceptional and employer deposits (resources).

    Each account counts for its net flow of the year: the deposits from the
    income and from the employer minus the withdrawals for the household. An
    exceptional deposit kept on its account moves wealth without passing
    through the budget, so only the part the household spent shows, as an
    exceptional resource, before any withdrawal from the savings.
    """

    def group(key: str, label: str, kind: str) -> BudgetNode:
        return BudgetNode(key=key, label=label, kind=kind, source="auto")

    groups = AccountGroups(
        savings=group(
            ACCOUNT_DEPOSITS, pgettext("budget", "Savings"), BudgetKind.SAVING
        ),
        investments=group(
            ACCOUNT_INVESTMENTS, _("Financial investments"), BudgetKind.SAVING
        ),
        withdrawals=group(
            ACCOUNT_WITHDRAWALS, _("Withdrawals from savings"), BudgetKind.INCOME
        ),
        exceptional=group(
            ACCOUNT_EXCEPTIONAL, _("Exceptional deposits"), BudgetKind.INCOME
        ),
        employer=group(ACCOUNT_EMPLOYER, _("Employee savings"), BudgetKind.INCOME),
    )
    for item in flows:
        saved = item.amount + item.employer
        spent = max(-saved, Decimal(0))
        exceptional = min(item.exceptional, spent)
        deposits = groups.savings if item.kind == "saving" else groups.investments
        parts = (
            (deposits, item.key, max(saved, Decimal(0))),
            (groups.withdrawals, item.key, spent - exceptional),
            (groups.exceptional, f"{item.key}:exceptional", exceptional),
            (groups.employer, f"{item.key}:employer", item.employer),
        )
        for parent, key, amount in parts:
            if amount:
                parent.children.append(
                    BudgetNode(
                        key=key,
                        label=str(item.account),
                        kind=parent.kind,
                        source="auto",
                        amount=amount,
                        url=item.url,
                    )
                )
    return groups


# ─── Summary ──────────────────────────────────────────────────────────────────


def _debt_categories(categories: list[BudgetCategory]) -> set[int]:
    """Categories flagged as loan repayments, with every category below them."""
    flagged = {c.pk for c in categories if c.counts_as_debt}
    parents = {c.pk: c.parent_id for c in categories}
    result = set()
    for pk in parents:
        node: int | None = pk
        while node is not None:
            if node in flagged:
                result.add(pk)
                break
            node = parents.get(node)
    return result


def build_budget(
    budget_year: BudgetYear,
    perspective: Perspective | None = None,
    *,
    currency: str | None = None,
) -> BudgetSummary:
    """The budget of *budget_year* for *perspective* (the whole household by default)."""
    perspective = perspective or Perspective.build()
    currency = currency or settings.DEFAULT_CURRENCY
    categories = list(BudgetCategory.objects.all())
    lines = [
        line
        for line in budget_year.lines.select_related("person").all()
        if str(line.amount.currency) == currency
    ]
    names = {
        line.person.pk: display_name(line.person)
        for line in lines
        if line.person is not None
    }
    roots = _category_nodes(categories, lines, perspective, names)
    resources = roots[BudgetKind.INCOME]
    expenses = roots[BudgetKind.EXPENSE]
    savings = roots[BudgetKind.SAVING]

    debt_categories = _debt_categories(categories)
    manual_debt = sum(
        (
            line.amount.amount * perspective.line_ratio(line.person_id)
            for line in lines
            if line.category_id in debt_categories
        ),
        Decimal(0),
    )
    manual_income = sum((n.total for n in resources), Decimal(0))

    property_flows: list[PropertyFlows] = []
    scpi_flows: list[SCPIFlows] = []
    finance = FinanceFlows()
    if budget_year.include_properties or budget_year.include_finance:
        resolver = HolderResolver()
        if budget_year.include_properties:
            excluded = set(budget_year.excluded_properties.values_list("pk", flat=True))
            property_flows = property_year_flows(
                budget_year.year,
                perspective,
                currency=currency,
                excluded=excluded,
                resolver=resolver,
            )
            scpi_flows = scpi_year_flows(
                budget_year.year, perspective, currency=currency, resolver=resolver
            )
        if budget_year.include_finance:
            finance = account_year_flows(
                budget_year.year, perspective, currency=currency, resolver=resolver
            )

    property_income, property_expenses = _property_nodes(property_flows)
    dividends, subscriptions = _scpi_nodes(scpi_flows)
    accounts = _account_nodes(finance.accounts)
    resources += [
        property_income,
        dividends,
        accounts.employer,
        accounts.withdrawals,
        accounts.exceptional,
    ]
    expenses.append(property_expenses)
    savings += [accounts.savings, accounts.investments, subscriptions]
    for root in [*resources, *expenses, *savings]:
        root.prune()
    resources = [n for n in resources if n.total]
    expenses = [n for n in expenses if n.total]
    savings = [n for n in savings if n.total]

    rents = sum((f.rent for f in property_flows), Decimal(0)) + dividends.total
    loan_payments = sum((f.loan.total for f in property_flows), Decimal(0))
    indicators = Indicators(
        income=manual_income
        + property_income.total
        + dividends.total
        + accounts.employer.total,
        expenses=sum((n.total for n in expenses), Decimal(0)),
        savings=sum((n.total for n in savings), Decimal(0)),
        withdrawals=accounts.withdrawals.total,
        exceptional=accounts.exceptional.total,
        principal=sum((f.loan.principal for f in property_flows), Decimal(0)),
        debt_payments=loan_payments + manual_debt,
        debt_income=manual_income + rents * RENT_WEIGHT,
    )
    return BudgetSummary(
        budget_year=budget_year,
        perspective=perspective,
        currency=currency,
        resources=resources,
        expenses=expenses,
        savings=savings,
        indicators=indicators,
        balance=balance_node(indicators.balance),
        guesses=finance.guesses,
    )


def balance_node(
    balance: Decimal, deficit_label: str | None = None
) -> BudgetNode | None:
    """Money left (a saving) or missing (a resource) once the budget is paid.

    A deficit is money taken from the current accounts or from accounts the
    application does not follow: it is named *deficit_label*, "Untracked
    resources" by default.
    """
    if balance > 0:
        return BudgetNode(
            key="balance:remaining",
            label=_("Not allocated"),
            kind=BudgetKind.SAVING,
            source="balance",
            amount=balance,
        )
    if balance < 0:
        return BudgetNode(
            key="balance:deficit",
            label=deficit_label or _("Untracked resources"),
            kind=BudgetKind.INCOME,
            source="balance",
            amount=-balance,
        )
    return None


def budget_monthly_expenses(
    year: int, currency: str | None = None
) -> tuple[BudgetYear, Decimal] | None:
    """Monthly expenses of the household from the budget of *year*.

    Falls back on the latest earlier budget; None without budget or when its
    expenses are zero.
    """
    budget_year = BudgetYear.objects.filter(year__lte=year).order_by("-year").first()
    if budget_year is None:
        return None
    expenses = build_budget(budget_year, currency=currency).indicators.monthly_expenses
    return (budget_year, expenses) if expenses > 0 else None
