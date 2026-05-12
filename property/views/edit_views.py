"""Property edit views (property, loans, loan amortization table)."""

import csv
import datetime
import io
import unicodedata
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.forms import inlineformset_factory
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from moneyed import Money

from property.forms import PropertyEditForm, PropertyLoanForm
from property.models import Property, PropertyLoan, PropertyLoanAmortizationEntry


def _make_loan_formset_class(extra: int = 1):
    return inlineformset_factory(
        Property,
        PropertyLoan,
        form=PropertyLoanForm,
        extra=extra,
        can_delete=True,
    )


def edit_property(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit property details (name, dates, amounts, etc.)."""
    property_obj = get_object_or_404(Property, pk=pk)

    if request.method == "POST":
        property_form = PropertyEditForm(request.POST, instance=property_obj)
        if property_form.is_valid():
            property_form.save()
            messages.success(request, _("Property updated successfully."))
            return redirect("property:detail", pk=property_obj.pk)
        else:
            messages.error(request, _("Please correct the errors below."))
    else:
        property_form = PropertyEditForm(instance=property_obj)

    return render(
        request,
        "property/edit.html",
        {"property": property_obj, "property_form": property_form},
    )


def manage_property_loans(request: HttpRequest, pk: int) -> HttpResponse:
    """Create, edit, or delete loans for a property."""
    property_obj = get_object_or_404(Property, pk=pk)

    if request.method != "POST":
        return redirect("property:detail", pk=pk)

    PropertyLoanFormSet = _make_loan_formset_class()
    loan_formset = PropertyLoanFormSet(request.POST, instance=property_obj)

    if loan_formset.is_valid():
        loan_formset.save()
        messages.success(request, _("Loans updated successfully."))
        return HttpResponseRedirect(
            reverse("property:detail", kwargs={"pk": property_obj.pk}) + "#loans-panel"
        )

    form_errors_parts = []
    for form in loan_formset.forms:
        for field, errs in form.errors.items():
            label = form.fields[field].label if field in form.fields else field
            form_errors_parts.append(f"{label}: {', '.join(str(e) for e in errs)}")
    if loan_formset.non_form_errors():
        form_errors_parts.extend(str(e) for e in loan_formset.non_form_errors())
    error_detail = "; ".join(form_errors_parts)
    messages.error(
        request,
        _("Please correct the errors below.")
        + (f" {error_detail}" if error_detail else ""),
    )
    return HttpResponseRedirect(
        reverse("property:detail", kwargs={"pk": property_obj.pk}) + "#loans-panel"
    )


def create_property(request: HttpRequest) -> HttpResponse:
    """Create a new property."""
    if request.method == "POST":
        property_form = PropertyEditForm(request.POST)
        if property_form.is_valid():
            property_obj = property_form.save()
            messages.success(request, _("Property created successfully."))
            return redirect("property:detail", pk=property_obj.pk)
        else:
            messages.error(request, _("Please correct the errors below."))
    else:
        property_form = PropertyEditForm()

    return render(request, "property/create.html", {"property_form": property_form})


# ─── Loan amortization table ───────────────────────────────────────────────────

_LOANS_ANCHOR = "#loans-panel"

_COL_DATE = {"date"}
_COL_CAPITAL = {"capital"}
_COL_INTEREST = {"interets", "interet", "interest", "interêts", "intêret"}
_COL_BALANCE = {
    "capital_restant",
    "capital_restant_du",
    "remaining",
    "solde",
    "capitaldue",
    "restant",
}


def _normalize_col(name: str) -> str:
    """Lowercase, strip spaces, remove accents."""
    s = name.strip().lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    ).replace(" ", "_")


def _parse_amount(raw: str) -> Decimal:
    cleaned = raw.strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    if cleaned == "":
        return Decimal("0")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"Invalid amount: {raw!r}")


def _parse_date(raw: str) -> datetime.date:
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%m/%d/%Y"):
        try:
            return datetime.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: {raw!r}")


@require_POST  # type: ignore
def import_loan_amortization(
    request: HttpRequest, pk: int, loan_pk: int
) -> HttpResponse:
    """Parse a bank CSV and replace the loan's amortization entries (all-or-nothing)."""
    loan = get_object_or_404(PropertyLoan, pk=loan_pk, property__pk=pk)
    redirect_url = reverse("property:detail", kwargs={"pk": pk}) + _LOANS_ANCHOR

    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        messages.error(request, _("No file provided."))
        return redirect(redirect_url)

    try:
        text = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            csv_file.seek(0)
            text = csv_file.read().decode("latin-1")
        except Exception:
            messages.error(request, _("Could not decode file — use UTF-8 or Latin-1."))
            return redirect(redirect_url)

    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        messages.error(request, _("Empty file."))
        return redirect(redirect_url)

    # Detect separator
    sample = lines[0]
    sep = ";" if sample.count(";") >= sample.count(",") else ","

    reader = csv.DictReader(io.StringIO(text), delimiter=sep)
    raw_fields = reader.fieldnames or []
    col_map: dict[str, str] = {}
    for raw in raw_fields:
        norm = _normalize_col(raw)
        if norm in _COL_DATE:
            col_map["date"] = raw
        elif norm in _COL_CAPITAL:
            col_map["capital"] = raw
        elif norm in _COL_INTEREST:
            col_map["interest"] = raw
        elif norm in _COL_BALANCE:
            col_map["balance"] = raw

    missing = [
        k for k in ("date", "capital", "interest", "balance") if k not in col_map
    ]
    if missing:
        messages.error(
            request, _("Missing columns: %(cols)s") % {"cols": ", ".join(missing)}
        )
        return redirect(redirect_url)

    currency = str(loan.original_amount.currency)
    entries = []
    errors = []

    for row_num, row in enumerate(reader, start=2):
        if not any(v.strip() for v in row.values()):
            continue
        try:
            date = _parse_date(row[col_map["date"]])
            capital = _parse_amount(row[col_map["capital"]])
            interest = _parse_amount(row[col_map["interest"]])
            balance = _parse_amount(row[col_map["balance"]])
            if capital < 0 or interest < 0 or balance < 0:
                raise ValueError("Negative amount")
        except (ValueError, InvalidOperation) as exc:
            errors.append(_("Row %(n)d: %(err)s") % {"n": row_num, "err": str(exc)})
            continue

        entries.append(
            PropertyLoanAmortizationEntry(
                loan=loan,
                date=date,
                capital=Money(capital, currency),
                interest=Money(interest, currency),
                remaining_balance_amount=Money(balance, currency),
            )
        )

    if errors:
        for err in errors:
            messages.error(request, err)
        return redirect(redirect_url)

    if not entries:
        messages.error(request, _("No valid rows found in the file."))
        return redirect(redirect_url)

    with transaction.atomic():
        PropertyLoanAmortizationEntry.objects.filter(loan=loan).delete()
        PropertyLoanAmortizationEntry.objects.bulk_create(entries)

    messages.success(request, _("%(n)d entries imported.") % {"n": len(entries)})
    return redirect(redirect_url)


@require_POST  # type: ignore
def generate_loan_amortization(
    request: HttpRequest, pk: int, loan_pk: int
) -> HttpResponse:
    """Auto-generate amortization entries from loan parameters."""
    from property.utils import build_loan_monthly_maps

    loan = get_object_or_404(PropertyLoan, pk=loan_pk, property__pk=pk)
    redirect_url = reverse("property:detail", kwargs={"pk": pk}) + _LOANS_ANCHOR

    if loan.monthly_payment is None:
        # Try to compute it on-the-fly from the loan's stored parameters
        loan.compute_monthly_payment()
    if loan.monthly_payment is None:
        messages.error(request, _("Cannot generate: loan has no monthly payment."))
        return redirect(redirect_url)

    insurance_amount = (
        loan.insurance.amount if loan.insurance is not None else Decimal("0")
    )
    interest_map, principal_map, _insurance_map = build_loan_monthly_maps(
        start_date=loan.start_date,
        end_date=loan.end_date,
        original_amount=loan.original_amount.amount,
        monthly_payment=loan.monthly_payment.amount,
        interest_rate=loan.interest_rate,
        insurance_amount=insurance_amount,
        disbursement_date=loan.start_date,
        first_payment_date=loan.first_payment_date,
    )

    currency = str(loan.original_amount.currency)
    entries = []
    balance = loan.original_amount.amount
    for key in sorted(interest_map.keys()):
        year, month = key
        capital = principal_map.get(key, Decimal("0"))
        interest = interest_map.get(key, Decimal("0"))
        balance = max(Decimal("0"), balance - capital)
        entries.append(
            PropertyLoanAmortizationEntry(
                loan=loan,
                date=datetime.date(year, month, 1),
                capital=Money(capital, currency),
                interest=Money(interest, currency),
                remaining_balance_amount=Money(balance, currency),
            )
        )

    with transaction.atomic():
        PropertyLoanAmortizationEntry.objects.filter(loan=loan).delete()
        PropertyLoanAmortizationEntry.objects.bulk_create(entries)

    messages.success(request, _("%(n)d entries generated.") % {"n": len(entries)})
    return redirect(redirect_url)


@require_POST  # type: ignore
def clear_loan_amortization(
    request: HttpRequest, pk: int, loan_pk: int
) -> HttpResponse:
    """Delete all amortization entries for a loan (reverts to auto-calculation)."""
    loan = get_object_or_404(PropertyLoan, pk=loan_pk, property__pk=pk)
    count, _deleted = PropertyLoanAmortizationEntry.objects.filter(loan=loan).delete()
    messages.success(request, _("%(n)d entries cleared.") % {"n": count})
    return redirect(reverse("property:detail", kwargs={"pk": pk}) + _LOANS_ANCHOR)
