"""Views for the property app."""

import datetime
from decimal import Decimal

from django.contrib import messages
from django.forms import inlineformset_factory
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView
from moneyed import Money

from property.services.cashflow import build_balance_sheet
from property.forms import (
    LeaseForm,
    ManagementMandateForm,
    PropertyEditForm,
    PropertyLedgerEntryEditForm,
    PropertyLedgerEntryQuickCreateForm,
    PropertyLoanForm,
    PropertyManagerForm,
    PropertyValueQuickCreateForm,
    TenantForm,
)
from property.models import (
    Lease,
    ManagementMandate,
    Property,
    PropertyLedgerEntry,
    PropertyLoan,
    PropertyManager,
    PropertyValue,
    Tenant,
)
from property.utils import (
    add_years_safe,
    build_loan_monthly_maps,
    iter_month_starts,
    month_end,
    month_start,
)


def index(request: HttpRequest) -> HttpResponse:
    """Property index view."""
    properties = Property.objects.order_by("is_active", "name")
    property_list = []

    total_gross_value: Money | None = None
    total_net_value: Money | None = None

    for prop in properties:
        gross_value = prop.gross_value
        net_value = prop.net_value

        if total_gross_value is None:
            total_gross_value = gross_value
            total_net_value = net_value
        elif str(gross_value.currency) == str(total_gross_value.currency):
            total_gross_value += gross_value
            total_net_value += net_value  # type: ignore[operator]

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

    properties_active = [p for p in properties if p.is_active]
    properties_months = []
    properties_gross_evolution = []
    properties_net_evolution = []

    earliest_date = None
    if properties_active:
        earliest_date = min(prop.buying_date for prop in properties_active)

    if earliest_date:
        now = datetime.date.today()
        chart_currency = (
            str(total_gross_value.currency) if total_gross_value is not None else None
        )

        for current_date in iter_month_starts(
            month_start(earliest_date), month_start(now)
        ):
            month_str = current_date.strftime("%b %Y")
            properties_months.append(month_str)

            month_properties = [
                p for p in properties_active if p.buying_date <= current_date
            ]

            month_property_net_total = Decimal("0")
            month_property_gross_total = Decimal("0")
            for property_item in month_properties:
                try:
                    net_value = property_item.net_value_at_date(current_date)
                    if net_value and (
                        chart_currency is None
                        or str(net_value.currency) == chart_currency
                    ):
                        month_property_net_total += net_value.amount

                    gross_value = property_item.get_value(
                        max_date=datetime.datetime.combine(
                            current_date,
                            datetime.time.max,
                        )
                    )
                    if gross_value and (
                        chart_currency is None
                        or str(gross_value.currency) == chart_currency
                    ):
                        month_property_gross_total += gross_value.amount
                except Exception:
                    pass

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

    def _parse_balance_sheet_range(
        self,
    ) -> tuple[datetime.date, datetime.date, int, int, int]:
        """
        Parse year/month range from GET params.

        Returns (date_from, date_to, year, months_span) where:
        - date_from  = first day of the start month
        - date_to    = last day of the end month
        - year       = reference year (used for display)
        - months_span = number of months in the range (12 for full year, 1 for single month)

        Default: current civil year (Jan 1 → Dec 31).
        """
        today = datetime.date.today()
        try:
            year = int(self.request.GET.get("bs_year", today.year))
        except ValueError, TypeError:
            year = today.year

        try:
            months_span = int(self.request.GET.get("bs_months", 12))
            if months_span not in (1, 3, 6, 12):
                months_span = 12
        except ValueError, TypeError:
            months_span = 12

        try:
            start_month = int(self.request.GET.get("bs_start_month", 1))
            if not 1 <= start_month <= 12:
                start_month = 1
        except ValueError, TypeError:
            start_month = 1

        date_from = datetime.date(year, start_month, 1)
        # Compute end month by adding (months_span - 1) months
        from property.utils import add_months_safe, month_end

        date_to_start = add_months_safe(date_from, months_span - 1)
        date_to = month_end(date_to_start)

        return date_from, date_to, year, months_span, start_month

    def _build_balance_sheet_context(self, property_obj: Property) -> dict:
        """Build balance sheet context for the given property and date range."""
        date_from, date_to, bs_year, bs_months, bs_start_month = (
            self._parse_balance_sheet_range()
        )

        balance_sheet = build_balance_sheet(property_obj, date_from, date_to)

        # Compute prev/next navigation params
        from property.utils import add_months_safe

        prev_start = add_months_safe(date_from, -bs_months)
        next_start = add_months_safe(date_from, bs_months)

        return {
            "balance_sheet": balance_sheet,
            "bs_date_from": date_from,
            "bs_date_to": date_to,
            "bs_year": bs_year,
            "bs_months": bs_months,
            "bs_start_month": bs_start_month,
            "bs_prev_year": prev_start.year,
            "bs_prev_start_month": prev_start.month,
            "bs_next_year": next_start.year,
            "bs_next_start_month": next_start.month,
        }

    def _get_growth_rate(self) -> Decimal:
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
                {"x": chart_date.isoformat(), "y": float(historical_value.amount)}
            )
            debt_history_series.append(
                {"x": chart_date.isoformat(), "y": float(historical_debt.amount)}
            )

        value_projection_series = [
            {"x": today.isoformat(), "y": float(current_value.amount)}
        ]
        debt_projection_series = [
            {"x": today.isoformat(), "y": float(current_debt.amount)}
        ]
        for projection in projections:
            value_projection_series.append(
                {"x": projection["date"].isoformat(), "y": projection["value_amount"]}
            )
            debt_projection_series.append(
                {"x": projection["date"].isoformat(), "y": projection["debt_amount"]}
            )

        return (
            value_history_series,
            debt_history_series,
            value_projection_series,
            debt_projection_series,
            today.isoformat(),
        )

    def _observation_window(
        self,
        property_obj: Property,
        entries_qs,
        loans_qs,
    ) -> tuple[datetime.date, datetime.date]:
        """Return inclusive first-of-month boundaries for activity calculations."""
        start_date = property_obj.buying_date
        oldest_entry = entries_qs.order_by("entry_date").first()
        oldest_loan = loans_qs.order_by("start_date").first()

        if oldest_entry and oldest_entry.entry_date < start_date:
            start_date = oldest_entry.entry_date
        if oldest_loan and oldest_loan.start_date < start_date:
            start_date = oldest_loan.start_date

        return month_start(start_date), month_start(datetime.date.today())

    def _occurrences_by_month(
        self, entries, end_month: datetime.date
    ) -> dict[tuple[int, int], Decimal]:
        """Aggregate recurring and one-shot entries to month buckets."""
        by_month: dict[tuple[int, int], Decimal] = {}
        end_of_month = month_end(end_month)
        for entry in entries:
            for occurrence in entry.generate_occurrences(end_date=end_of_month):
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

    def _estimated_monthly_cashflow(self, property_obj: Property) -> Decimal:
        """Estimate average monthly cashflow from ledger entries and loan costs."""
        entries_qs = PropertyLedgerEntry.objects.filter(property=property_obj)
        revenues_qs = entries_qs.filter(flow_type=PropertyLedgerEntry.FlowType.INCOME)
        expenses_qs = entries_qs.filter(flow_type=PropertyLedgerEntry.FlowType.EXPENSE)
        loans_qs = PropertyLoan.objects.filter(property=property_obj)
        start_month, end_month = self._observation_window(
            property_obj, entries_qs, loans_qs
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

    def _build_cashflow_series(
        self,
        property_obj: Property,
    ) -> tuple[
        list[dict],
        list[dict],
        list[dict],
        list[dict],
        list[dict],
        list[dict],
        list[dict],
    ]:
        """Build monthly cashflow series from ledger entries and loans."""
        entries_qs = PropertyLedgerEntry.objects.filter(property=property_obj)
        revenues_qs = entries_qs.filter(flow_type=PropertyLedgerEntry.FlowType.INCOME)
        expenses_qs = entries_qs.filter(flow_type=PropertyLedgerEntry.FlowType.EXPENSE)
        loans_qs = PropertyLoan.objects.filter(property=property_obj)
        start_month, end_month = self._observation_window(
            property_obj, entries_qs, loans_qs
        )

        revenue_by_month = self._occurrences_by_month(revenues_qs, end_month)
        expense_by_month = self._occurrences_by_month(expenses_qs, end_month)
        loan_interest_by_month, loan_principal_by_month, loan_insurance_by_month = (
            self._loan_costs_by_month(loans_qs)
        )

        # Breakdown of expenses by management_category
        expense_by_mgmt_cat: dict[str, dict] = {}
        end_of_month = month_end(end_month)
        for entry in expenses_qs:
            cat_key = entry.management_category
            if cat_key not in expense_by_mgmt_cat:
                expense_by_mgmt_cat[cat_key] = {
                    "label": entry.get_management_category_display(),
                    "by_month": {},
                }
            for occurrence in entry.generate_occurrences(end_date=end_of_month):
                key = (occurrence["date"].year, occurrence["date"].month)
                expense_by_mgmt_cat[cat_key]["by_month"][key] = (
                    expense_by_mgmt_cat[cat_key]["by_month"].get(key, Decimal("0"))
                    + occurrence["amount"].amount
                )

        revenue_series = []
        expense_series = []
        loan_interest_series = []
        loan_principal_series = []
        loan_insurance_series = []
        total_expenses_series = []
        type_month_series: dict[str, list[dict]] = {k: [] for k in expense_by_mgmt_cat}

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
                {"x": current.isoformat(), "y": loan_interest_value}
            )
            loan_principal_series.append(
                {"x": current.isoformat(), "y": loan_principal_value}
            )
            loan_insurance_series.append(
                {"x": current.isoformat(), "y": loan_insurance_value}
            )
            total_expenses_series.append(
                {"x": current.isoformat(), "y": total_expenses_value}
            )
            for cat_key, cat_data in expense_by_mgmt_cat.items():
                type_month_series[cat_key].append(
                    {
                        "x": current.isoformat(),
                        "y": float(cat_data["by_month"].get(month_key, 0)),
                    }
                )

        expense_by_type_series = [
            {"label": expense_by_mgmt_cat[k]["label"], "data": type_month_series[k]}
            for k in expense_by_mgmt_cat
        ]

        return (
            revenue_series,
            expense_series,
            loan_interest_series,
            loan_principal_series,
            loan_insurance_series,
            total_expenses_series,
            expense_by_type_series,
        )

    def _build_transactions_json(self, property_obj: Property) -> list[dict]:
        """Build all expanded transactions as a list of dicts for DataTables."""
        entries_qs = PropertyLedgerEntry.objects.filter(property=property_obj)
        rows = []
        for entry in entries_qs:
            tax_label = entry.get_tax_category_display()
            for occurrence in entry.generate_occurrences():
                rows.append(
                    {
                        "kind": entry.flow_type,
                        "date": occurrence["date"].isoformat(),
                        "category": str(tax_label),
                        "amount": float(occurrence["amount"].amount),
                        "description": entry.description or "",
                        "is_recurring": occurrence["is_recurring"],
                        "parent_id": entry.pk,
                    }
                )
        # Default sort: most recent first
        rows.sort(key=lambda r: r["date"], reverse=True)
        return rows

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

        elif form_type == "ledger_entry":
            form = PropertyLedgerEntryQuickCreateForm(request.POST)
            if form.is_valid():
                entry = form.save(commit=False)
                entry.property = self.object
                entry.amount = Money(entry.amount.amount, str(self.object.currency))
                entry.save()
                messages.success(request, _("Entry added."))
                return redirect("property:detail", pk=self.object.pk)
            messages.error(request, _("Unable to add entry."))

        else:
            messages.error(request, _("Unknown form action."))

        return self.get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
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
        transactions_data = self._build_transactions_json(property_obj)
        (
            revenue_series,
            expense_series,
            loan_interest_series,
            loan_principal_series,
            loan_insurance_series,
            total_expenses_series,
            expense_by_type_series,
        ) = self._build_cashflow_series(property_obj)

        entries = PropertyLedgerEntry.objects.filter(property=property_obj)
        entries_with_forms = [
            {
                "obj": entry,
                "edit_form": PropertyLedgerEntryEditForm(instance=entry),
            }
            for entry in entries
        ]

        balance_sheet_context = self._build_balance_sheet_context(property_obj)

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
                "cashflow_expense_by_type_series": expense_by_type_series,
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
                "entry_form": PropertyLedgerEntryQuickCreateForm(),
                "value_form": PropertyValueQuickCreateForm(
                    initial={
                        "valuation_date": datetime.date.today(),
                        "value_1": str(property_obj.currency),
                    }
                ),
                "property_values": PropertyValue.objects.filter(
                    property=property_obj
                ).order_by("-valuation_date"),
                "entries_with_forms": entries_with_forms,
                "active_leases": Lease.objects.filter(
                    property=property_obj,
                    status__in=[Lease.Status.ACTIVE, Lease.Status.NOTICE_PERIOD],
                ).prefetch_related("tenants"),
                "active_mandate": ManagementMandate.objects.filter(
                    property=property_obj, end_date__isnull=True
                ).first(),
                "transactions_json": transactions_data,
            }
        )
        context.update(balance_sheet_context)
        return context


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _get_property_or_redirect(
    request: HttpRequest,
    property_pk: int,
) -> tuple[Property | None, HttpResponse | None]:
    property_obj = Property.objects.filter(pk=property_pk).first()
    if property_obj is not None:
        return property_obj, None
    messages.error(request, _("Property not found."))
    return None, redirect("property:index")


def _get_related_or_redirect(
    request: HttpRequest,
    *,
    model,
    related_name: str,
    object_pk: int,
    property_obj: Property,
) -> tuple:
    obj = model.objects.filter(pk=object_pk, property=property_obj).first()
    if obj is not None:
        return obj, None
    messages.error(request, _("%(name)s not found.") % {"name": related_name})
    return None, redirect("property:detail", pk=property_obj.pk)


# ─── Property valuation ───────────────────────────────────────────────────────


def delete_property_valuation(
    request: HttpRequest, property_pk: int, valuation_pk: int
) -> HttpResponse:
    if request.method != "POST":
        messages.error(request, _("Invalid request method."))
        return redirect("property:detail", pk=property_pk)

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


# ─── Property edit ────────────────────────────────────────────────────────────


def edit_property(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit a property and its associated loans."""
    property_obj = get_object_or_404(Property, pk=pk)

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
            messages.error(request, _("Please correct the errors below."))
    else:
        property_form = PropertyEditForm(instance=property_obj)
        loan_formset = PropertyLoanFormSet(instance=property_obj)

    context = {
        "property": property_obj,
        "property_form": property_form,
        "loan_formset": loan_formset,
    }
    return render(request, "property/edit.html", context)


# ─── Ledger entry CRUD ────────────────────────────────────────────────────────


def edit_ledger_entry(
    request: HttpRequest, property_pk: int, entry_pk: int
) -> HttpResponse:
    """Edit a ledger entry (income or expense)."""
    property_obj, response = _get_property_or_redirect(request, property_pk)
    if response:
        return response
    assert property_obj is not None

    entry, response = _get_related_or_redirect(
        request,
        model=PropertyLedgerEntry,
        related_name=str(_("Entry")),
        object_pk=entry_pk,
        property_obj=property_obj,
    )
    if response:
        return response
    assert entry is not None

    if request.method == "POST":
        form = PropertyLedgerEntryEditForm(request.POST, instance=entry)
        if form.is_valid():
            form.save()
            messages.success(request, _("Entry updated successfully."))
            return redirect("property:detail", pk=property_pk)
        messages.error(request, _("Please correct the errors below."))
    else:
        form = PropertyLedgerEntryEditForm(instance=entry)

    context = {
        "property": property_obj,
        "entry": entry,
        "form": form,
    }
    return render(request, "property/edit_entry.html", context)


def delete_ledger_entry(
    request: HttpRequest, property_pk: int, entry_pk: int
) -> HttpResponse:
    """Delete a ledger entry. Only accepts POST."""
    if request.method != "POST":
        messages.error(request, _("Invalid request method."))
        return redirect("property:detail", pk=property_pk)

    property_obj, response = _get_property_or_redirect(request, property_pk)
    if response:
        return response
    assert property_obj is not None

    entry, response = _get_related_or_redirect(
        request,
        model=PropertyLedgerEntry,
        related_name=str(_("Entry")),
        object_pk=entry_pk,
        property_obj=property_obj,
    )
    if response:
        return response
    assert entry is not None

    entry.delete()
    messages.success(request, _("Entry deleted successfully."))
    return redirect("property:detail", pk=property_pk)


# ─── Tenant CRUD ──────────────────────────────────────────────────────────────


def edit_tenant(request: HttpRequest, pk: int) -> HttpResponse:
    """Create or edit a tenant."""
    tenant = get_object_or_404(Tenant, pk=pk) if pk else None

    if request.method == "POST":
        form = TenantForm(request.POST, instance=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, _("Tenant saved."))
            return redirect("property:index")
        messages.error(request, _("Please correct the errors below."))
    else:
        form = TenantForm(instance=tenant)

    return render(
        request, "property/edit_tenant.html", {"form": form, "tenant": tenant}
    )


# ─── Lease CRUD ───────────────────────────────────────────────────────────────


def edit_lease(
    request: HttpRequest, property_pk: int, lease_pk: int | None = None
) -> HttpResponse:
    """Create or edit a lease for a property."""
    property_obj = get_object_or_404(Property, pk=property_pk)
    lease = (
        get_object_or_404(Lease, pk=lease_pk, property=property_obj)
        if lease_pk
        else None
    )

    if request.method == "POST":
        form = LeaseForm(request.POST, instance=lease)
        if form.is_valid():
            created = form.save(commit=False)
            created.property = property_obj
            created.save()
            messages.success(request, _("Lease saved."))
            return redirect("property:detail", pk=property_pk)
        messages.error(request, _("Please correct the errors below."))
    else:
        form = LeaseForm(instance=lease)

    return render(
        request,
        "property/edit_lease.html",
        {"property": property_obj, "lease": lease, "form": form},
    )


# ─── PropertyManager / ManagementMandate CRUD ────────────────────────────────


def edit_manager(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """Create or edit a property manager."""
    manager = get_object_or_404(PropertyManager, pk=pk) if pk else None

    if request.method == "POST":
        form = PropertyManagerForm(request.POST, instance=manager)
        if form.is_valid():
            form.save()
            messages.success(request, _("Manager saved."))
            return redirect("property:index")
        messages.error(request, _("Please correct the errors below."))
    else:
        form = PropertyManagerForm(instance=manager)

    return render(
        request, "property/edit_manager.html", {"form": form, "manager": manager}
    )


def edit_mandate(
    request: HttpRequest, property_pk: int, mandate_pk: int | None = None
) -> HttpResponse:
    """Create or edit a management mandate for a property."""
    property_obj = get_object_or_404(Property, pk=property_pk)
    mandate = (
        get_object_or_404(ManagementMandate, pk=mandate_pk, property=property_obj)
        if mandate_pk
        else None
    )

    if request.method == "POST":
        form = ManagementMandateForm(request.POST, instance=mandate)
        if form.is_valid():
            created = form.save(commit=False)
            created.property = property_obj
            created.save()
            messages.success(request, _("Mandate saved."))
            return redirect("property:detail", pk=property_pk)
        messages.error(request, _("Please correct the errors below."))
    else:
        form = ManagementMandateForm(instance=mandate)

    return render(
        request,
        "property/edit_mandate.html",
        {"property": property_obj, "mandate": mandate, "form": form},
    )
