"""Views for the property app."""

import datetime
from decimal import Decimal
from typing import TypeVar, cast
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Model
from django.core.paginator import Paginator
from django.forms import inlineformset_factory
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView
from moneyed import Money

from property.forms import (
    PropertyEditForm,
    PropertyExpenseEditForm,
    PropertyExpenseQuickCreateForm,
    PropertyLoanForm,
    PropertyRevenueEditForm,
    PropertyRevenueQuickCreateForm,
    PropertyValueQuickCreateForm,
)
from property.models import (
    Property,
    PropertyExpense,
    PropertyLoan,
    PropertyRevenue,
    PropertyValue,
)
from property.utils import (
    add_years_safe,
    build_loan_monthly_maps,
    iter_month_starts,
    month_start,
)

M = TypeVar("M", bound=Model)


def index(request: HttpRequest) -> HttpResponse:
    """Property index view."""
    properties = Property.objects.filter().order_by("is_active", "name")
    property_list = []

    # Track total values
    total_gross_value = 0
    total_net_value = 0

    for prop in properties:
        # Get gross and net values
        gross_value = prop.gross_value
        net_value = prop.net_value

        # Add to totals
        if isinstance(total_gross_value, int) and total_gross_value == 0:
            # First property, set the initial values
            total_gross_value = gross_value
            total_net_value = net_value
        else:
            # Add to totals if currency matches
            if str(gross_value.currency) == str(total_gross_value.currency):
                total_gross_value += gross_value
                total_net_value += net_value

        property_list.append(
            {
                "model": prop,
                "current_value": prop.get_value(),
                "gross_value": gross_value,
                "net_value": net_value,
                "loans_count": PropertyLoan.objects.filter(property=prop).count(),
                "progression": prop.get_progression(),
            }
        )

    # Get data for the chart, both gross and net values
    properties_active = [p for p in properties if p.is_active]
    properties_months = []
    properties_gross_evolution = []
    properties_net_evolution = []

    # Find the earliest property purchase date
    earliest_date = None
    if properties_active:
        earliest_date = min(prop.buying_date for prop in properties_active)

    if earliest_date:
        # Generate data from the earliest property date to now
        now = datetime.date.today()
        for current_date in iter_month_starts(
            month_start(earliest_date), month_start(now)
        ):
            month_str = current_date.strftime("%b %Y")
            properties_months.append(month_str)

            # Get all properties that were active at that month (purchased before or during that month)
            month_properties = [
                p for p in properties_active if p.buying_date <= current_date
            ]

            # Get property values for this month
            month_property_net_total = 0
            month_property_gross_total = 0
            for property_item in month_properties:
                try:
                    # For property net value at this specific month
                    net_value = property_item.net_value_at_date(current_date)
                    if net_value:
                        # Convert to same currency if needed
                        if (
                            isinstance(total_gross_value, int)
                            and total_gross_value == 0
                        ):
                            month_property_net_total += net_value.amount
                        elif hasattr(total_gross_value, "currency") and str(
                            net_value.currency
                        ) == str(total_gross_value.currency):
                            month_property_net_total += net_value.amount

                    # For property gross value at this specific month
                    gross_value = property_item.get_value(
                        max_date=datetime.datetime.combine(
                            current_date,
                            datetime.time.max,
                        )
                    )
                    if gross_value:
                        # Convert to same currency if needed
                        if (
                            isinstance(total_gross_value, int)
                            and total_gross_value == 0
                        ):
                            month_property_gross_total += gross_value.amount
                        elif hasattr(total_gross_value, "currency") and str(
                            gross_value.currency
                        ) == str(total_gross_value.currency):
                            month_property_gross_total += gross_value.amount
                except Exception:
                    # If there's an error, skip this property for this month
                    pass

            # Store the totals for the chart
            properties_gross_evolution.append(float(month_property_gross_total))
            properties_net_evolution.append(float(month_property_net_total))

    context = {
        "properties": property_list,
        "inactive_properties_count": properties.filter(is_active=False).count(),
        "total_gross_value": total_gross_value,
        "total_net_value": total_net_value,
        "properties_months": properties_months,
        "properties_gross_evolution": properties_gross_evolution,
        "properties_net_evolution": properties_net_evolution,
    }
    return render(request, "property/index.html", context)


class PropertyDetailView(DetailView):
    """Property detail dashboard view with long term projections."""

    model = Property
    template_name = "property/detail.html"
    context_object_name = "property"

    def _get_growth_rate(self) -> Decimal:
        """Return annual growth rate from query string with a safe default."""
        default_rate = Decimal("0.02")
        raw_growth_rate = self.request.GET.get("growth_rate")
        if not raw_growth_rate:
            return default_rate

        try:
            value = Decimal(raw_growth_rate)
            if value > Decimal("1"):
                value = value / Decimal("100")
            if value < Decimal("-0.99"):
                return default_rate
            return value
        except Exception:
            return default_rate

    def _build_projection_data(self, property_obj: Property) -> list[dict]:
        """Build projections for value, debt and net equity over selected horizons."""
        projection_years = list(range(1, 21))
        growth_rate = self._get_growth_rate()
        current_value = property_obj.get_value()
        today = datetime.date.today()

        projections = []
        for years in projection_years:
            as_of_date = add_years_safe(today, years)
            projected_amount = current_value.amount * (
                (Decimal("1") + growth_rate) ** years
            )
            projected_value = Money(projected_amount, str(current_value.currency))
            projected_debt = property_obj.total_remaining_loans_at_date(as_of_date)
            projected_net = projected_value - projected_debt

            projections.append(
                {
                    "years": years,
                    "date": as_of_date,
                    "projected_value": projected_value,
                    "projected_debt": projected_debt,
                    "projected_net": projected_net,
                    "value_amount": float(projected_value.amount),
                    "debt_amount": float(projected_debt.amount),
                    "net_amount": float(projected_net.amount),
                }
            )
        return projections

    def _build_chart_series(
        self,
        property_obj: Property,
        projections: list[dict],
    ) -> tuple[list[dict], list[dict], list[dict], list[dict], str]:
        """Build datetime chart series for historical and projected curves."""
        today = datetime.date.today()
        current_value = property_obj.get_value()
        current_debt = property_obj.total_remaining_loans_at_date(today)

        valuation_dates = list(
            PropertyValue.objects.filter(
                property=property_obj,
                valuation_date__lte=today,
            ).values_list("valuation_date", flat=True)
        )
        historical_dates = sorted({property_obj.buying_date, today, *valuation_dates})

        value_history_series = []
        debt_history_series = []
        for chart_date in historical_dates:
            historical_value = property_obj.get_value(
                max_date=datetime.datetime.combine(chart_date, datetime.time.max),
            )
            historical_debt = property_obj.total_remaining_loans_at_date(chart_date)
            value_history_series.append(
                {
                    "x": chart_date.isoformat(),
                    "y": float(historical_value.amount),
                }
            )
            debt_history_series.append(
                {
                    "x": chart_date.isoformat(),
                    "y": float(historical_debt.amount),
                }
            )

        value_projection_series = [
            {"x": today.isoformat(), "y": float(current_value.amount)}
        ]
        debt_projection_series = [
            {"x": today.isoformat(), "y": float(current_debt.amount)}
        ]
        for projection in projections:
            value_projection_series.append(
                {
                    "x": projection["date"].isoformat(),
                    "y": projection["value_amount"],
                }
            )
            debt_projection_series.append(
                {
                    "x": projection["date"].isoformat(),
                    "y": projection["debt_amount"],
                }
            )

        return (
            value_history_series,
            debt_history_series,
            value_projection_series,
            debt_projection_series,
            today.isoformat(),
        )

    def _estimated_monthly_cashflow(self, property_obj: Property) -> Decimal:
        """Estimate monthly cashflow from historical revenues, expenses, and loan costs."""
        revenues_qs = PropertyRevenue.objects.filter(property=property_obj)
        expenses_qs = PropertyExpense.objects.filter(property=property_obj)
        loans_qs = PropertyLoan.objects.filter(property=property_obj)
        start_month, end_month = self._observation_window(
            property_obj,
            revenues_qs,
            expenses_qs,
            loans_qs,
        )

        revenue_by_month = self._occurrences_by_month(revenues_qs, end_month)
        expense_by_month = self._occurrences_by_month(expenses_qs, end_month)
        loan_interest_by_month, loan_principal_by_month, loan_insurance_by_month = (
            self._loan_costs_by_month(loans_qs)
        )

        months = iter_month_starts(start_month, end_month)
        months_observed = max(1, len(months))

        total_revenues = sum(
            (
                revenue_by_month.get((month.year, month.month), Decimal("0"))
                for month in months
            ),
            Decimal("0"),
        )
        total_expenses = sum(
            (
                expense_by_month.get((month.year, month.month), Decimal("0"))
                for month in months
            ),
            Decimal("0"),
        )
        total_loan_costs = sum(
            (
                loan_interest_by_month.get((month.year, month.month), Decimal("0"))
                + loan_principal_by_month.get((month.year, month.month), Decimal("0"))
                + loan_insurance_by_month.get((month.year, month.month), Decimal("0"))
                for month in months
            ),
            Decimal("0"),
        )

        return (total_revenues - total_expenses - total_loan_costs) / Decimal(
            months_observed
        )

    def _observation_window(
        self,
        property_obj: Property,
        revenues_qs,
        expenses_qs,
        loans_qs,
    ) -> tuple[datetime.date, datetime.date]:
        """Return inclusive first-of-month boundaries for activity calculations."""
        start_date = property_obj.buying_date
        oldest_revenue = revenues_qs.order_by("revenue_date").first()
        oldest_expense = expenses_qs.order_by("expense_date").first()
        oldest_loan = loans_qs.order_by("start_date").first()

        if oldest_revenue and oldest_revenue.revenue_date < start_date:
            start_date = oldest_revenue.revenue_date
        if oldest_expense and oldest_expense.expense_date < start_date:
            start_date = oldest_expense.expense_date
        if oldest_loan and oldest_loan.start_date < start_date:
            start_date = oldest_loan.start_date

        return month_start(start_date), month_start(datetime.date.today())

    def _occurrences_by_month(
        self, entries, end_month: datetime.date
    ) -> dict[tuple[int, int], Decimal]:
        """Aggregate recurring and one-shot entries to month buckets."""
        by_month: dict[tuple[int, int], Decimal] = {}
        for entry in entries:
            for occurrence in entry.generate_occurrences(end_date=end_month):
                key = (occurrence["date"].year, occurrence["date"].month)
                by_month[key] = (
                    by_month.get(key, Decimal("0")) + occurrence["amount"].amount
                )
        return by_month

    def _loan_costs_by_month(
        self,
        loans_qs,
    ) -> tuple[
        dict[tuple[int, int], Decimal],
        dict[tuple[int, int], Decimal],
        dict[tuple[int, int], Decimal],
    ]:
        """Aggregate loan costs to month buckets for all loans."""
        loan_interest_by_month: dict[tuple[int, int], Decimal] = {}
        loan_principal_by_month: dict[tuple[int, int], Decimal] = {}
        loan_insurance_by_month: dict[tuple[int, int], Decimal] = {}

        for loan in loans_qs:
            insurance_amount = (
                loan.insurance.amount if loan.insurance is not None else Decimal("0")
            )
            interest_map, principal_map, insurance_map = build_loan_monthly_maps(
                start_date=loan.start_date,
                end_date=loan.end_date,
                original_amount=loan.original_amount.amount,
                monthly_payment=loan.monthly_payment.amount,
                interest_rate=loan.interest_rate,
                insurance_amount=insurance_amount,
            )

            for key, value in interest_map.items():
                loan_interest_by_month[key] = (
                    loan_interest_by_month.get(key, Decimal("0")) + value
                )
            for key, value in principal_map.items():
                loan_principal_by_month[key] = (
                    loan_principal_by_month.get(key, Decimal("0")) + value
                )
            for key, value in insurance_map.items():
                loan_insurance_by_month[key] = (
                    loan_insurance_by_month.get(key, Decimal("0")) + value
                )

        return loan_interest_by_month, loan_principal_by_month, loan_insurance_by_month

    def _build_cashflow_series(
        self,
        property_obj: Property,
    ) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict], list[dict]]:
        """Build monthly cashflow series for revenues, expenses and loans."""
        revenues_qs = PropertyRevenue.objects.filter(property=property_obj)
        expenses_qs = PropertyExpense.objects.filter(property=property_obj)
        loans_qs = PropertyLoan.objects.filter(property=property_obj)
        start_month, end_month = self._observation_window(
            property_obj,
            revenues_qs,
            expenses_qs,
            loans_qs,
        )

        revenue_by_month = self._occurrences_by_month(revenues_qs, end_month)
        expense_by_month = self._occurrences_by_month(expenses_qs, end_month)
        loan_interest_by_month, loan_principal_by_month, loan_insurance_by_month = (
            self._loan_costs_by_month(loans_qs)
        )

        revenue_series = []
        expense_series = []
        loan_interest_series = []
        loan_principal_series = []
        loan_insurance_series = []
        total_expenses_series = []

        for current in iter_month_starts(start_month, end_month):
            month_key = (current.year, current.month)

            expense_value = float(expense_by_month.get(month_key, 0))
            loan_interest_value = float(loan_interest_by_month.get(month_key, 0))
            loan_principal_value = float(loan_principal_by_month.get(month_key, 0))
            loan_insurance_value = float(loan_insurance_by_month.get(month_key, 0))
            total_expenses_value = (
                expense_value
                + loan_interest_value
                + loan_principal_value
                + loan_insurance_value
            )

            revenue_series.append(
                {
                    "x": current.isoformat(),
                    "y": float(revenue_by_month.get(month_key, 0)),
                }
            )
            expense_series.append({"x": current.isoformat(), "y": expense_value})
            loan_interest_series.append(
                {
                    "x": current.isoformat(),
                    "y": loan_interest_value,
                }
            )
            loan_principal_series.append(
                {
                    "x": current.isoformat(),
                    "y": loan_principal_value,
                }
            )
            loan_insurance_series.append(
                {
                    "x": current.isoformat(),
                    "y": loan_insurance_value,
                }
            )
            total_expenses_series.append(
                {
                    "x": current.isoformat(),
                    "y": total_expenses_value,
                }
            )

        return (
            revenue_series,
            expense_series,
            loan_interest_series,
            loan_principal_series,
            loan_insurance_series,
            total_expenses_series,
        )

    def _build_transactions_table_context(self, property_obj: Property) -> dict:
        """Build unified transactions context for expenses and revenues table."""
        transaction_type = self.request.GET.get("transaction_type", "all")
        search_query = self.request.GET.get("q", "").strip()
        sort = self.request.GET.get("sort", "date")
        order = self.request.GET.get("order", "desc")
        page_size_raw = self.request.GET.get("page_size", "10")

        allowed_page_sizes = [5, 10, 20, 50]
        try:
            page_size = int(page_size_raw)
        except ValueError:
            page_size = 10
        if page_size not in allowed_page_sizes:
            page_size = 10

        expenses = PropertyExpense.objects.filter(property=property_obj)
        revenues = PropertyRevenue.objects.filter(property=property_obj)

        if search_query:
            expenses = expenses.filter(description__icontains=search_query)
            revenues = revenues.filter(description__icontains=search_query)

        rows = []
        if transaction_type in ["all", "expense"]:
            for expense in expenses:
                # Generate all occurrences for recurring expenses
                occurrences = expense.generate_occurrences()
                for occurrence in occurrences:
                    rows.append(
                        {
                            "kind": "expense",
                            "date": occurrence["date"],
                            "category": expense.get_expense_type_display(),  # type: ignore[attr-defined]
                            "amount": occurrence["amount"],
                            "description": expense.description or "",
                            "is_recurring": occurrence["is_recurring"],
                            "parent_id": expense.pk,
                            "parent_obj": expense,
                        }
                    )

        if transaction_type in ["all", "revenue"]:
            for revenue in revenues:
                # Generate all occurrences for recurring revenues
                occurrences = revenue.generate_occurrences()
                for occurrence in occurrences:
                    rows.append(
                        {
                            "kind": "revenue",
                            "date": occurrence["date"],
                            "category": revenue.get_revenue_type_display(),  # type: ignore[attr-defined]
                            "amount": occurrence["amount"],
                            "description": revenue.description or "",
                            "is_recurring": occurrence["is_recurring"],
                            "parent_id": revenue.pk,
                            "parent_obj": revenue,
                        }
                    )

        sort_key_map = {
            "date": lambda row: row["date"],
            "kind": lambda row: row["kind"],
            "category": lambda row: row["category"].lower(),
            "amount": lambda row: row["amount"].amount,
            "description": lambda row: row["description"].lower(),
        }
        sort_key = sort_key_map.get(sort, sort_key_map["date"])
        reverse = order != "asc"
        rows.sort(key=sort_key, reverse=reverse)

        paginator = Paginator(rows, page_size)
        page_number = self.request.GET.get("page", "1")
        page_obj = paginator.get_page(page_number)

        base_query_dict = {
            "transaction_type": transaction_type,
            "q": search_query,
            "sort": sort,
            "order": order,
            "page_size": page_size,
        }
        base_query_string = urlencode(base_query_dict)

        def _sort_query(column: str) -> str:
            next_order = "asc"
            if sort == column and order == "asc":
                next_order = "desc"
            query = {
                "transaction_type": transaction_type,
                "q": search_query,
                "sort": column,
                "order": next_order,
                "page_size": page_size,
            }
            return urlencode(query)

        return {
            "transactions_page": page_obj,
            "transaction_type": transaction_type,
            "transaction_search_query": search_query,
            "transaction_sort": sort,
            "transaction_order": order,
            "transaction_page_size": page_size,
            "transaction_page_sizes": allowed_page_sizes,
            "transactions_base_query": base_query_string,
            "sort_query_date": _sort_query("date"),
            "sort_query_kind": _sort_query("kind"),
            "sort_query_category": _sort_query("category"),
            "sort_query_amount": _sort_query("amount"),
            "sort_query_description": _sort_query("description"),
        }

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """Handle quick create forms from dashboard modals."""
        self.object = self.get_object()
        form_type = request.POST.get("form_type")

        if form_type == "value":
            form = PropertyValueQuickCreateForm(request.POST)
            if form.is_valid():
                created_value = form.save(commit=False)
                created_value.property = self.object
                created_value.value = Money(
                    created_value.value.amount,
                    str(self.object.currency),
                )
                created_value.save()
                messages.success(request, _("Property value added."))
                return redirect("property:detail", pk=self.object.pk)
            messages.error(request, _("Unable to add property value."))
        elif form_type == "expense":
            form = PropertyExpenseQuickCreateForm(request.POST)
            if form.is_valid():
                created_expense = form.save(commit=False)
                created_expense.property = self.object
                created_expense.save()
                messages.success(request, _("Property expense added."))
                return redirect("property:detail", pk=self.object.pk)
            messages.error(request, _("Unable to add property expense."))
        elif form_type == "revenue":
            form = PropertyRevenueQuickCreateForm(request.POST)
            if form.is_valid():
                created_revenue = form.save(commit=False)
                created_revenue.property = self.object
                created_revenue.save()
                messages.success(request, _("Property revenue added."))
                return redirect("property:detail", pk=self.object.pk)
            messages.error(request, _("Unable to add property revenue."))
        else:
            messages.error(request, _("Unknown form action."))

        return self.get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """Add dashboard metrics and chart datasets to template context."""
        context = super().get_context_data(**kwargs)
        property_obj = self.object

        growth_rate = self._get_growth_rate()
        projections = self._build_projection_data(property_obj)
        (
            value_history_series,
            debt_history_series,
            value_projection_series,
            debt_projection_series,
            projection_start_date,
        ) = self._build_chart_series(property_obj, projections)
        monthly_cashflow_amount = self._estimated_monthly_cashflow(property_obj)
        transactions_context = self._build_transactions_table_context(property_obj)
        (
            revenue_series,
            expense_series,
            loan_interest_series,
            loan_principal_series,
            loan_insurance_series,
            total_expenses_series,
        ) = self._build_cashflow_series(property_obj)

        # Get all unique expenses and revenues for edit/delete modals
        expenses = PropertyExpense.objects.filter(property=property_obj)
        revenues = PropertyRevenue.objects.filter(property=property_obj)

        expenses_with_forms = [
            {
                "obj": expense,
                "edit_form": PropertyExpenseEditForm(instance=expense),
            }
            for expense in expenses
        ]

        revenues_with_forms = [
            {
                "obj": revenue,
                "edit_form": PropertyRevenueEditForm(instance=revenue),
            }
            for revenue in revenues
        ]

        context.update(
            {
                "growth_rate": growth_rate,
                "growth_rate_percent": growth_rate * Decimal("100"),
                "projection_points": projections,
                "projection_labels": [str(item["years"]) for item in projections],
                "projection_values": [item["value_amount"] for item in projections],
                "projection_debts": [item["debt_amount"] for item in projections],
                "projection_nets": [item["net_amount"] for item in projections],
                "value_history_series": value_history_series,
                "debt_history_series": debt_history_series,
                "value_projection_series": value_projection_series,
                "debt_projection_series": debt_projection_series,
                "cashflow_revenue_series": revenue_series,
                "cashflow_expense_series": expense_series,
                "cashflow_loan_interest_series": loan_interest_series,
                "cashflow_loan_principal_series": loan_principal_series,
                "cashflow_loan_insurance_series": loan_insurance_series,
                "cashflow_total_expenses_series": total_expenses_series,
                "projection_start_date": projection_start_date,
                "current_raw_value": property_obj.get_value(),
                "current_net_value": property_obj.net_value,
                "capital_repaid": property_obj.total_paid_loans,
                "estimated_monthly_cashflow": Money(
                    monthly_cashflow_amount,
                    str(property_obj.buying_value.currency),
                ),
                "value_form": PropertyValueQuickCreateForm(
                    initial={
                        "valuation_date": datetime.date.today(),
                        "value_1": str(property_obj.currency),
                    }
                ),
                "expense_form": PropertyExpenseQuickCreateForm(),
                "revenue_form": PropertyRevenueQuickCreateForm(),
                "property_values": PropertyValue.objects.filter(
                    property=property_obj
                ).order_by("-valuation_date"),
                "expenses_with_forms": expenses_with_forms,
                "revenues_with_forms": revenues_with_forms,
            }
        )
        context.update(transactions_context)
        return context


def _get_property_or_redirect(
    request: HttpRequest,
    property_pk: int,
) -> tuple[Property | None, HttpResponse | None]:
    """Return a property or a redirect response when not found."""
    property_obj = Property.objects.filter(pk=property_pk).first()
    if property_obj is not None:
        return property_obj, None

    messages.error(request, _("Property not found."))
    return None, redirect("property:index")


def _get_related_or_redirect(
    request: HttpRequest,
    *,
    model: type[M],
    related_name: str,
    object_pk: int,
    property_obj: Property,
) -> tuple[M | None, HttpResponse | None]:
    """Return a related object bound to a property or a redirect response."""
    obj = cast(
        M | None, model.objects.filter(pk=object_pk, property=property_obj).first()
    )
    if obj is not None:
        return obj, None

    messages.error(request, _("%(name)s not found.") % {"name": related_name})
    return None, redirect("property:detail", pk=property_obj.pk)


def delete_property_valuation(
    request: HttpRequest, property_pk: int, valuation_pk: int
) -> HttpResponse:
    """Delete a property valuation."""
    property_obj, response = _get_property_or_redirect(request, property_pk)
    if response:
        return response
    assert property_obj is not None

    valuation = PropertyValue.objects.filter(
        pk=valuation_pk, property=property_obj
    ).first()
    if not valuation:
        messages.error(request, _("Valuation not found."))
        return redirect("property:detail", pk=property_pk)

    valuation.delete()
    messages.success(request, _("Property valuation deleted successfully."))
    return redirect("property:detail", pk=property_pk)


def edit_property(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit a property and its associated loans."""
    property_obj = get_object_or_404(Property, pk=pk)

    # Create a formset for the property loans
    PropertyLoanFormSet = inlineformset_factory(
        Property,
        PropertyLoan,
        form=PropertyLoanForm,
        extra=1,
        can_delete=True,
    )

    if request.method == "POST":
        property_form = PropertyEditForm(request.POST, instance=property_obj)
        loan_formset = PropertyLoanFormSet(request.POST, instance=property_obj)

        if property_form.is_valid() and loan_formset.is_valid():
            property_form.save()
            loan_formset.save()
            messages.success(request, _("Property updated successfully."))
            return redirect("property:detail", pk=property_obj.pk)
        else:
            messages.error(
                request,
                _("Please correct the errors below."),
            )
    else:
        property_form = PropertyEditForm(instance=property_obj)
        loan_formset = PropertyLoanFormSet(instance=property_obj)

    context = {
        "property": property_obj,
        "property_form": property_form,
        "loan_formset": loan_formset,
    }
    return render(request, "property/edit.html", context)


def edit_property_expense(
    request: HttpRequest, property_pk: int, expense_pk: int
) -> HttpResponse:
    """Edit a property expense (including recurring settings)."""
    property_obj, response = _get_property_or_redirect(request, property_pk)
    if response:
        return response
    assert property_obj is not None

    expense, response = _get_related_or_redirect(
        request,
        model=PropertyExpense,
        related_name=str(_("Expense")),
        object_pk=expense_pk,
        property_obj=property_obj,
    )
    if response:
        return response
    assert expense is not None

    if request.method == "POST":
        form = PropertyExpenseEditForm(request.POST, instance=expense)
        if form.is_valid():
            form.save()
            messages.success(request, _("Expense updated successfully."))
            return redirect("property:detail", pk=property_pk)
        messages.error(request, _("Please correct the errors below."))
    else:
        form = PropertyExpenseEditForm(instance=expense)

    context = {
        "property": property_obj,
        "expense": expense,
        "form": form,
    }
    return render(request, "property/edit_expense.html", context)


def delete_property_expense(
    request: HttpRequest, property_pk: int, expense_pk: int
) -> HttpResponse:
    """Delete a property expense (and all its recurrences)."""
    property_obj, response = _get_property_or_redirect(request, property_pk)
    if response:
        return response
    assert property_obj is not None

    expense, response = _get_related_or_redirect(
        request,
        model=PropertyExpense,
        related_name=str(_("Expense")),
        object_pk=expense_pk,
        property_obj=property_obj,
    )
    if response:
        return response
    assert expense is not None

    if request.method == "POST":
        expense.delete()
        messages.success(request, _("Expense deleted successfully."))
        return redirect("property:detail", pk=property_pk)

    context = {
        "property": property_obj,
        "expense": expense,
    }
    return render(request, "property/delete_expense.html", context)


def edit_property_revenue(
    request: HttpRequest, property_pk: int, revenue_pk: int
) -> HttpResponse:
    """Edit a property revenue (including recurring settings)."""
    property_obj, response = _get_property_or_redirect(request, property_pk)
    if response:
        return response
    assert property_obj is not None

    revenue, response = _get_related_or_redirect(
        request,
        model=PropertyRevenue,
        related_name=str(_("Revenue")),
        object_pk=revenue_pk,
        property_obj=property_obj,
    )
    if response:
        return response
    assert revenue is not None

    if request.method == "POST":
        form = PropertyRevenueEditForm(request.POST, instance=revenue)
        if form.is_valid():
            form.save()
            messages.success(request, _("Revenue updated successfully."))
            return redirect("property:detail", pk=property_pk)
        messages.error(request, _("Please correct the errors below."))
    else:
        form = PropertyRevenueEditForm(instance=revenue)

    context = {
        "property": property_obj,
        "revenue": revenue,
        "form": form,
    }
    return render(request, "property/edit_revenue.html", context)


def delete_property_revenue(
    request: HttpRequest, property_pk: int, revenue_pk: int
) -> HttpResponse:
    """Delete a property revenue (and all its recurrences)."""
    property_obj, response = _get_property_or_redirect(request, property_pk)
    if response:
        return response
    assert property_obj is not None

    revenue, response = _get_related_or_redirect(
        request,
        model=PropertyRevenue,
        related_name=str(_("Revenue")),
        object_pk=revenue_pk,
        property_obj=property_obj,
    )
    if response:
        return response
    assert revenue is not None

    if request.method == "POST":
        revenue.delete()
        messages.success(request, _("Revenue deleted successfully."))
        return redirect("property:detail", pk=property_pk)

    context = {
        "property": property_obj,
        "revenue": revenue,
    }
    return render(request, "property/delete_revenue.html", context)
