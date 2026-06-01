"""Property detail dashboard view."""

import datetime
import json
import statistics
from decimal import Decimal

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView
from moneyed import Money

from property.forms import (
    PropertyLedgerEntryEditForm,
    PropertyLedgerEntryQuickCreateForm,
    PropertyValueQuickCreateForm,
)
from property.models import (
    Lease,
    ManagementMandate,
    Property,
    PropertyLedgerEntry,
    PropertyLoan,
    PropertyLoanAmortizationEntry,
    PropertyValue,
)
from property.services.cashflow import build_balance_sheet
from property.utils import (
    add_years_safe,
    build_loan_maps_from_loan_obj,
    build_loan_monthly_maps,
    iter_month_starts,
    month_end,
    month_start,
)
from property.views.edit_views import _make_loan_formset_class
from property.views.fiscal_views import get_amortization_context


class PropertyDetailView(DetailView):
    """Property detail dashboard view with long term projections."""

    model = Property
    template_name = "property/detail.html"
    context_object_name = "property"

    def _parse_balance_sheet_range(
        self,
    ) -> tuple[datetime.date, datetime.date]:
        """
        Parse explicit date range from GET params ``start_date`` and ``end_date``.

        Both params must be ISO-8601 dates (YYYY-MM-DD).  ``start_date`` is
        normalised to the first day of its month; ``end_date`` to the last day
        of its month so the balance sheet always covers whole months.

        Default: full current civil year (Jan 1 → Dec 31).
        """
        today = datetime.date.today()
        default_from = datetime.date(today.year, 1, 1)
        default_to = datetime.date(today.year, 12, 31)

        raw_start = self.request.GET.get("start_date", "")
        raw_end = self.request.GET.get("end_date", "")

        try:
            parsed_start = datetime.date.fromisoformat(raw_start)
        except ValueError, TypeError:
            parsed_start = default_from

        try:
            parsed_end = datetime.date.fromisoformat(raw_end)
        except ValueError, TypeError:
            parsed_end = default_to

        # Normalise to month boundaries
        date_from = month_start(parsed_start)
        date_to = month_end(parsed_end)

        # Sanity: ensure range is not inverted
        if date_from > date_to:
            date_from = default_from
            date_to = default_to

        return date_from, date_to

    def _build_balance_sheet_context(self, property_obj: Property) -> dict:
        """Build balance sheet context for the given property and date range."""
        date_from, date_to = self._parse_balance_sheet_range()

        balance_sheet = build_balance_sheet(property_obj, date_from, date_to)

        return {
            "balance_sheet": balance_sheet,
            "bs_date_from": date_from,
            "bs_date_to": date_to,
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
    ) -> tuple[
        list[dict], list[dict], list[dict], list[dict], list[dict], list[dict], str
    ]:
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
        net_history_series = []
        for chart_date in historical_dates:
            if chart_date == property_obj.buying_date:
                historical_value = property_obj.buying_value_gross
            else:
                historical_value = property_obj.get_value(
                    max_date=datetime.datetime.combine(chart_date, datetime.time.max),
                )
            historical_debt = property_obj.total_remaining_loans_at_date(chart_date)
            net_amount = max(
                Decimal("0"), historical_value.amount - historical_debt.amount
            )
            value_history_series.append(
                {"x": chart_date.isoformat(), "y": float(historical_value.amount)}
            )
            debt_history_series.append(
                {"x": chart_date.isoformat(), "y": float(historical_debt.amount)}
            )
            net_history_series.append(
                {"x": chart_date.isoformat(), "y": float(net_amount)}
            )

        current_net = max(Decimal("0"), current_value.amount - current_debt.amount)
        value_projection_series = [
            {"x": today.isoformat(), "y": float(current_value.amount)}
        ]
        debt_projection_series = [
            {"x": today.isoformat(), "y": float(current_debt.amount)}
        ]
        net_projection_series = [{"x": today.isoformat(), "y": float(current_net)}]
        for projection in projections:
            value_projection_series.append(
                {"x": projection["date"].isoformat(), "y": projection["value_amount"]}
            )
            debt_projection_series.append(
                {"x": projection["date"].isoformat(), "y": projection["debt_amount"]}
            )
            net_projection_series.append(
                {"x": projection["date"].isoformat(), "y": projection["net_amount"]}
            )

        return (
            value_history_series,
            debt_history_series,
            net_history_series,
            value_projection_series,
            debt_projection_series,
            net_projection_series,
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

            # When amortization entries exist, use them for interest and principal.
            amort_entries = list(
                PropertyLoanAmortizationEntry.objects.filter(loan=loan).order_by("date")
            )
            if amort_entries:
                for entry in amort_entries:
                    key = (entry.date.year, entry.date.month)
                    loan_interest_by_month[key] = (
                        loan_interest_by_month.get(key, Decimal("0"))
                        + entry.interest.amount
                    )
                    loan_principal_by_month[key] = (
                        loan_principal_by_month.get(key, Decimal("0"))
                        + entry.capital.amount
                    )
                # Insurance is not in amortization entries; derive from loan params.
                if (
                    insurance_amount > Decimal("0")
                    and loan.start_date
                    and loan.end_date
                ):
                    _, _, insurance_map = build_loan_maps_from_loan_obj(
                        loan, insurance_amount
                    )
                    for key, value in insurance_map.items():
                        loan_insurance_by_month[key] = (
                            loan_insurance_by_month.get(key, Decimal("0")) + value
                        )
                continue

            # Fallback: compute from loan parameters when no amortization entries.
            if loan.monthly_payment is None:
                continue

            interest_map, principal_map, insurance_map = build_loan_maps_from_loan_obj(
                loan, insurance_amount
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
        """Estimate monthly cashflow as the median of the last 12 months."""
        today = datetime.date.today()
        end_month = month_start(today)
        start_month = month_start(datetime.date(today.year - 1, today.month, 1))

        entries_qs = PropertyLedgerEntry.objects.filter(
            property=property_obj
        ).prefetch_related("exceptions")
        revenues_qs = entries_qs.filter(flow_type=PropertyLedgerEntry.FlowType.INCOME)
        expenses_qs = entries_qs.filter(flow_type=PropertyLedgerEntry.FlowType.EXPENSE)
        loans_qs = PropertyLoan.objects.filter(property=property_obj)

        revenue_by_month = self._occurrences_by_month(revenues_qs, end_month)
        expense_by_month = self._occurrences_by_month(expenses_qs, end_month)
        loan_interest_by_month, loan_principal_by_month, loan_insurance_by_month = (
            self._loan_costs_by_month(loans_qs)
        )

        months = iter_month_starts(start_month, end_month)
        monthly_cashflows = []
        for m in months:
            key = (m.year, m.month)
            rev = revenue_by_month.get(key, Decimal("0"))
            exp = expense_by_month.get(key, Decimal("0"))
            interest = loan_interest_by_month.get(key, Decimal("0"))
            principal = loan_principal_by_month.get(key, Decimal("0"))
            insurance = loan_insurance_by_month.get(key, Decimal("0"))
            # Skip months with no financial activity at all (no data)
            if not (rev or exp or interest or principal or insurance):
                continue
            monthly_cashflows.append(rev - exp - interest - principal - insurance)

        if not monthly_cashflows:
            return Decimal("0")

        return Decimal(str(statistics.median(monthly_cashflows)))

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
        entries_qs = PropertyLedgerEntry.objects.filter(
            property=property_obj
        ).prefetch_related("exceptions")
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

        # Exclude loan_interest and loan_insurance: those are already shown as
        # dedicated computed series in the breakdown chart (from _loan_costs_by_month).
        _LOAN_COST_CATS = {
            PropertyLedgerEntry.ManagementCategory.LOAN_INTEREST,
            PropertyLedgerEntry.ManagementCategory.LOAN_INSURANCE,
        }
        expense_by_type_series = [
            {"label": expense_by_mgmt_cat[k]["label"], "data": type_month_series[k]}
            for k in expense_by_mgmt_cat
            if k not in _LOAN_COST_CATS
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
        entries_qs = (
            PropertyLedgerEntry.objects.filter(property=property_obj)
            .select_related("lease")
            .prefetch_related("exceptions", "capitalized_as")
        )
        rows = []
        for entry in entries_qs:
            cat_label = entry.get_management_category_display()
            lease_name = entry.lease.name if entry.lease else ""
            descriptions = [entry.description] if entry.description else []
            if entry.third_party:
                descriptions.insert(0, entry.third_party)
            if lease_name:
                descriptions.append(lease_name)
            base_description = " - ".join(descriptions)
            is_capitalized = entry.capitalized_as.exists()  # ty: ignore[unresolved-attribute]
            for occurrence in entry.generate_occurrences():
                is_recurring = occurrence["is_recurring"]
                rows.append(
                    {
                        "kind": entry.flow_type,
                        "date": occurrence["date"].isoformat(),
                        "category": str(cat_label),
                        "amount": float(occurrence["amount"].amount),
                        "description": occurrence.get("description_override")
                        or base_description,
                        "is_recurring": is_recurring,
                        "is_capitalized": is_capitalized,
                        "occurrence_date": occurrence["date"].isoformat()
                        if is_recurring
                        else None,
                        "has_exception": occurrence.get("has_exception", False),
                        "parent_id": entry.pk,
                        "property_id": property_obj.pk,
                    }
                )
        # Default sort: most recent first
        rows.sort(key=lambda r: r["date"], reverse=True)
        return rows

    def _build_loan_chart_data(self, property_obj: Property) -> dict:
        """Build per-loan monthly chart data for the loans panel chart.

        Returns a dict with:
        - loans: list of {name, data: [{x, y}]} — total payment per month per loan
        - total_capital: [{x, y}] — total capital repaid per month across all loans
        - total_interest: [{x, y}] — total interest paid per month across all loans
        """
        loans = (
            PropertyLoan.objects.filter(property=property_obj)
            .prefetch_related("amortization_entries")
            .order_by("start_date")
        )

        # Collect per-loan monthly maps: {(year, month): total_payment}
        loan_series: list[dict] = []
        all_capital: dict[tuple[int, int], Decimal] = {}
        all_interest: dict[tuple[int, int], Decimal] = {}

        for loan in loans:
            if loan.start_date is None or loan.end_date is None:
                continue

            capital_map: dict[tuple[int, int], Decimal] = {}
            interest_map: dict[tuple[int, int], Decimal] = {}
            insurance_map: dict[tuple[int, int], Decimal] = {}

            if loan.amortization_entries.exists():
                # Use imported/generated amortization table
                for entry in loan.amortization_entries.all():
                    key = (entry.date.year, entry.date.month)
                    capital_map[key] = (
                        capital_map.get(key, Decimal("0")) + entry.capital.amount
                    )
                    interest_map[key] = (
                        interest_map.get(key, Decimal("0")) + entry.interest.amount
                    )
            elif loan.monthly_payment is not None and loan.interest_rate is not None:
                insurance_amount = (
                    loan.insurance.amount if loan.insurance else Decimal("0")
                )
                interest_map, capital_map, insurance_map = build_loan_monthly_maps(
                    start_date=loan.start_date,
                    end_date=loan.end_date,
                    original_amount=loan.original_amount.amount,
                    monthly_payment=loan.monthly_payment.amount,
                    interest_rate=loan.interest_rate,
                    insurance_amount=insurance_amount,
                    disbursement_date=loan.start_date,
                    first_payment_date=loan.first_payment_date,
                )
            else:
                continue

            # Build total payment per month for this loan (capital + interest + insurance)
            all_months = set(capital_map) | set(interest_map) | set(insurance_map)
            total_map: dict[tuple[int, int], Decimal] = {}
            for key in all_months:
                total = (
                    capital_map.get(key, Decimal("0"))
                    + interest_map.get(key, Decimal("0"))
                    + insurance_map.get(key, Decimal("0"))
                )
                total_map[key] = total
                all_capital[key] = all_capital.get(key, Decimal("0")) + capital_map.get(
                    key, Decimal("0")
                )
                all_interest[key] = all_interest.get(
                    key, Decimal("0")
                ) + interest_map.get(key, Decimal("0"))

            sorted_months = sorted(total_map.keys())
            loan_series.append(
                {
                    "name": loan.name or loan.lender or f"#{loan.pk}",
                    "data": [
                        {"x": f"{y}-{m:02d}-01", "y": float(total_map[(y, m)])}
                        for y, m in sorted_months
                    ],
                }
            )

        # Build aggregate lines
        all_months_sorted = sorted(set(all_capital) | set(all_interest))
        total_capital_series = [
            {"x": f"{y}-{m:02d}-01", "y": float(all_capital.get((y, m), Decimal("0")))}
            for y, m in all_months_sorted
        ]
        total_interest_series = [
            {"x": f"{y}-{m:02d}-01", "y": float(all_interest.get((y, m), Decimal("0")))}
            for y, m in all_months_sorted
        ]

        return {
            "loans": loan_series,
            "total_capital": total_capital_series,
            "total_interest": total_interest_series,
        }

    def _build_loans_context(self, property_obj: Property) -> list[dict]:
        """Build loan details with computed total cost for the Info tab."""
        loans = PropertyLoan.objects.filter(property=property_obj).order_by(
            "start_date"
        )
        result = []
        for loan in loans:
            duration = loan.get_duration_months()
            avg_monthly_payment = None
            if loan.monthly_payment is not None and duration > 0:
                monthly = loan.monthly_payment.amount
                insurance = loan.insurance.amount if loan.insurance is not None else 0
                total_repaid = Money(
                    (monthly + insurance) * duration, loan.original_amount.currency
                )
            else:
                total_repaid = None

            total_cost = (
                total_repaid.amount - loan.original_amount.amount
                if total_repaid is not None
                else None
            )

            remaining = loan.remaining_balance()
            result.append(
                {
                    "loan": loan,
                    "duration_months": duration,
                    "total_repaid": total_repaid,
                    "total_cost": total_cost,
                    "avg_monthly_payment": avg_monthly_payment,
                    "remaining_balance": remaining,
                }
            )
        return result

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
                return HttpResponseRedirect(
                    reverse("property:detail", kwargs={"pk": self.object.pk})
                    + "#projection-panel"
                )
            form_errors = "; ".join(
                f"{field}: {', '.join(str(e) for e in errors)}"
                for field, errors in form.errors.items()
            )
            messages.error(
                request,
                _("Unable to add property value.")
                + (f" {form_errors}" if form_errors else ""),
            )

        elif form_type == "ledger_entry":
            form = PropertyLedgerEntryQuickCreateForm(
                request.POST, property_obj=self.object
            )
            if form.is_valid():
                entry = form.save(commit=False)
                entry.property = self.object
                entry.amount = Money(entry.amount.amount, str(self.object.currency))
                entry.save()
                messages.success(request, _("Entry added."))
                return HttpResponseRedirect(
                    reverse("property:detail", kwargs={"pk": self.object.pk})
                    + "#cashflow-panel"
                )
            form_errors = "; ".join(
                f"{field}: {', '.join(str(e) for e in errors)}"
                for field, errors in form.errors.items()
            )
            messages.error(
                request,
                _("Unable to add entry.") + (f" {form_errors}" if form_errors else ""),
            )

        else:
            messages.error(request, _("Unknown form action."))

        return self.get(request, *args, **kwargs)

    def _build_loan_formset(self, property_obj: Property):
        """Build a read-only (GET) loan formset for the Loans tab."""
        PropertyLoanFormSet = _make_loan_formset_class()
        loan_formset = PropertyLoanFormSet(instance=property_obj)
        self._loan_formset_cache = loan_formset
        return loan_formset

    def _build_loan_forms_ctx(self) -> list[dict]:
        """Return each loan form as a simple dict (no schedule formsets)."""
        loan_formset = getattr(self, "_loan_formset_cache", None)
        if loan_formset is None:
            return []
        return [{"form": form} for form in loan_formset.forms]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        property_obj = self.object

        monthly_cashflow_amount = self._estimated_monthly_cashflow(property_obj)

        property_leases = Lease.objects.filter(property=property_obj).order_by(
            "-start_date"
        )
        property_mandates = ManagementMandate.objects.filter(
            property=property_obj
        ).order_by("-start_date")

        loans_count = PropertyLoan.objects.filter(property=property_obj).count()

        context.update(
            {
                "current_raw_value": property_obj.get_value(),
                "buying_value_gross": property_obj.buying_value_gross,
                "value_progression_pct": (
                    (
                        (
                            property_obj.get_value().amount
                            - property_obj.buying_value_gross.amount
                        )
                        / property_obj.buying_value_gross.amount
                        * Decimal("100")
                    )
                    if property_obj.buying_value_gross.amount
                    else None
                ),
                "current_net_value": property_obj.net_value,
                "capital_repaid": property_obj.total_paid_loans,
                "estimated_monthly_cashflow": Money(
                    monthly_cashflow_amount,
                    str(property_obj.buying_value.currency),
                ),
                "entry_form": PropertyLedgerEntryQuickCreateForm(
                    property_obj=property_obj,
                    initial={"entry_date": datetime.date.today()},
                ),
                "value_form": PropertyValueQuickCreateForm(
                    initial={
                        "valuation_date": datetime.date.today(),
                        "value_1": str(property_obj.currency),
                    }
                ),
                "property_values": PropertyValue.objects.filter(
                    property=property_obj
                ).order_by("-valuation_date"),
                "property_leases": property_leases,
                "property_mandates": property_mandates,
                "loans_count": loans_count,
                "today": datetime.date.today(),
                "ledger_income_categories": [
                    (c.value, c.label)
                    for c in PropertyLedgerEntry.ManagementCategory
                    if c.value in PropertyLedgerEntry._INCOME_CATEGORIES
                ],
                "ledger_expense_categories": [
                    (c.value, c.label)
                    for c in PropertyLedgerEntry.ManagementCategory
                    if c.value not in PropertyLedgerEntry._INCOME_CATEGORIES
                ],
            }
        )
        # Amortization tab (only for LMNP réel properties)
        context["show_amortization_tab"] = (
            property_obj.tax_regime == Property.TaxRegime.LMNP_REEL
        )
        return context


# ── Panel HTML fragment views (async-loaded on tab click) ────────────────────


def _make_panel_view(
    property_obj: Property, request: HttpRequest
) -> "PropertyDetailView":
    """Create a lightweight PropertyDetailView instance to reuse helper methods."""
    view = PropertyDetailView()
    view.object = property_obj
    view.request = request
    view.kwargs = {}
    return view


def property_panel_cashflow(request: HttpRequest, pk: int) -> HttpResponse:
    """Return the Cash flow panel HTML fragment."""
    prop = get_object_or_404(Property, pk=pk)
    view = _make_panel_view(prop, request)
    (
        revenue_series,
        expense_series,
        loan_interest_series,
        loan_principal_series,
        loan_insurance_series,
        total_expenses_series,
        expense_by_type_series,
    ) = view._build_cashflow_series(prop)
    transactions_data = view._build_transactions_json(prop)
    entries = (
        PropertyLedgerEntry.objects.filter(property=prop)
        .select_related("lease")
        .prefetch_related("exceptions", "capitalized_as")
    )
    entries_with_forms = [
        {
            "obj": entry,
            "edit_form": PropertyLedgerEntryEditForm(instance=entry, property_obj=prop),
        }
        for entry in entries
    ]
    context = {
        "property": prop,
        "transactions_json": transactions_data,
        "cashflow_revenue_series": revenue_series,
        "cashflow_expense_series": expense_series,
        "cashflow_expense_by_type_series": expense_by_type_series,
        "cashflow_loan_interest_series": loan_interest_series,
        "cashflow_loan_principal_series": loan_principal_series,
        "cashflow_loan_insurance_series": loan_insurance_series,
        "cashflow_total_expenses_series": total_expenses_series,
        "entries_with_forms": entries_with_forms,
        "ledger_income_categories": [
            (c.value, c.label)
            for c in PropertyLedgerEntry.ManagementCategory
            if c.value in PropertyLedgerEntry._INCOME_CATEGORIES
        ],
        "ledger_expense_categories": [
            (c.value, c.label)
            for c in PropertyLedgerEntry.ManagementCategory
            if c.value not in PropertyLedgerEntry._INCOME_CATEGORIES
        ],
    }
    return render(request, "property/detail_panel_cashflow.html", context)


def property_panel_projection(request: HttpRequest, pk: int) -> HttpResponse:
    """Return the Value & Projection panel HTML fragment."""
    prop = get_object_or_404(Property, pk=pk)
    view = _make_panel_view(prop, request)
    growth_rate = view._get_growth_rate()
    projections = view._build_projection_data(prop)
    (
        value_history_series,
        debt_history_series,
        net_history_series,
        value_projection_series,
        debt_projection_series,
        net_projection_series,
        projection_start_date,
    ) = view._build_chart_series(prop, projections)
    context = {
        "property": prop,
        "growth_rate": growth_rate,
        "growth_rate_percent": growth_rate * Decimal("100"),
        "projection_points": projections,
        "value_history_series": value_history_series,
        "debt_history_series": debt_history_series,
        "net_history_series": net_history_series,
        "value_projection_series": value_projection_series,
        "debt_projection_series": debt_projection_series,
        "net_projection_series": net_projection_series,
        "projection_start_date": projection_start_date,
        "property_values": PropertyValue.objects.filter(property=prop).order_by(
            "-valuation_date"
        ),
    }
    return render(request, "property/detail_panel_projection.html", context)


def property_panel_balance(request: HttpRequest, pk: int) -> HttpResponse:
    """Return the Balance sheet panel HTML fragment."""
    prop = get_object_or_404(Property, pk=pk)
    view = _make_panel_view(prop, request)
    context = {"property": prop}
    context.update(view._build_balance_sheet_context(prop))
    return render(request, "property/detail_panel_balance.html", context)


def property_panel_info(request: HttpRequest, pk: int) -> HttpResponse:
    """Return the Info panel HTML fragment."""
    prop = get_object_or_404(Property, pk=pk)
    context = {"property": prop}
    return render(request, "property/detail_panel_info.html", context)


def property_panel_loans(request: HttpRequest, pk: int) -> HttpResponse:
    """Return the Loans panel HTML fragment."""
    prop = get_object_or_404(Property, pk=pk)
    view = _make_panel_view(prop, request)
    loans_with_totals = view._build_loans_context(prop)
    loan_chart_data = view._build_loan_chart_data(prop)
    loan_formset = view._build_loan_formset(prop)
    loan_forms_ctx = view._build_loan_forms_ctx()
    context = {
        "property": prop,
        "loans_with_totals": loans_with_totals,
        "loan_chart_data_json": json.dumps(loan_chart_data),
        "today": datetime.date.today(),
        "loan_formset": loan_formset,
        "loan_forms_with_schedules": loan_forms_ctx,
    }
    return render(request, "property/detail_panel_loans.html", context)


def property_panel_leases(request: HttpRequest, pk: int) -> HttpResponse:
    """Return the Leases panel HTML fragment."""
    prop = get_object_or_404(Property, pk=pk)
    property_leases = Lease.objects.filter(property=prop).order_by("-start_date")
    context = {
        "property": prop,
        "property_leases": property_leases,
    }
    return render(request, "property/detail_panel_leases.html", context)


def property_panel_mandate(request: HttpRequest, pk: int) -> HttpResponse:
    """Return the Mandate panel HTML fragment."""
    prop = get_object_or_404(Property, pk=pk)
    property_mandates = ManagementMandate.objects.filter(property=prop).order_by(
        "-start_date"
    )
    context = {
        "property": prop,
        "property_mandates": property_mandates,
    }
    return render(request, "property/detail_panel_mandate.html", context)


def property_panel_amortization(request: HttpRequest, pk: int) -> HttpResponse:
    """Return the Amortization panel HTML fragment (LMNP réel only)."""
    prop = get_object_or_404(Property, pk=pk)
    if prop.tax_regime != Property.TaxRegime.LMNP_REEL:
        return HttpResponse(status=404)
    context = {"property": prop}
    context.update(get_amortization_context(prop))
    return render(request, "property/detail_panel_amortization.html", context)
