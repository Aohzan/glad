"""Property edit view (property + loans + schedules)."""

from typing import Any

from django.contrib import messages
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from property.forms import PropertyEditForm, PropertyLoanForm, PropertyLoanScheduleForm
from property.models import Property, PropertyLoan, PropertyLoanSchedule


def _make_loan_formset_class(extra: int = 1):
    return inlineformset_factory(
        Property,
        PropertyLoan,
        form=PropertyLoanForm,
        extra=extra,
        can_delete=True,
    )


def _make_schedule_formset_class():
    return inlineformset_factory(
        PropertyLoan,
        PropertyLoanSchedule,
        form=PropertyLoanScheduleForm,
        extra=1,
        can_delete=True,
    )


def _build_loan_forms_with_schedules(
    property_obj: Property,
    loan_formset,
    schedule_formsets: dict,
) -> list[dict]:
    """Pair each loan form with its schedule formset for template rendering."""
    result = []
    for form_idx, form in enumerate(loan_formset.forms):
        loan_pk = form.instance.pk if form.instance.pk else None
        sf = (
            schedule_formsets.get(loan_pk)
            if loan_pk
            else schedule_formsets.get(f"temp_{form_idx}")
        )
        is_smoothed = form.instance.is_smoothed() if loan_pk else False
        result.append(
            {"form": form, "schedule_formset": sf, "is_smoothed": is_smoothed}
        )
    return result


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
    """Create, edit, or delete loans (and their payment schedules) for a property."""
    property_obj = get_object_or_404(Property, pk=pk)

    if request.method != "POST":
        return redirect("property:detail", pk=pk)

    PropertyLoanFormSet = _make_loan_formset_class()
    ScheduleFormSet = _make_schedule_formset_class()

    existing_loans = list(PropertyLoan.objects.filter(property=property_obj))
    loan_formset = PropertyLoanFormSet(request.POST, instance=property_obj)

    schedule_formsets: dict[int | str, BaseInlineFormSet[Any, Any, Any]] = {}
    for loan in existing_loans:
        prefix = f"schedules_{loan.pk}"
        schedule_formsets[loan.pk] = ScheduleFormSet(
            request.POST, instance=loan, prefix=prefix
        )
    for form_idx, loan_form in enumerate(loan_formset.forms):
        if not loan_form.instance.pk:
            prefix = f"schedules_new_{form_idx}"
            schedule_formsets[f"temp_{form_idx}"] = ScheduleFormSet(
                request.POST, instance=loan_form.instance, prefix=prefix
            )

    all_valid = loan_formset.is_valid()
    for sf in schedule_formsets.values():
        if not sf.is_valid():
            all_valid = False

    if all_valid:
        saved_loans = loan_formset.save()
        for loan in existing_loans:
            if loan.pk in schedule_formsets:
                schedule_formsets[loan.pk].save()
        for form_idx, loan in enumerate(saved_loans):
            if loan.pk and loan not in existing_loans:
                temp_key = f"temp_{form_idx}"
                if temp_key in schedule_formsets:
                    prefix = f"schedules_{loan.pk}"
                    new_sf = ScheduleFormSet(request.POST, instance=loan, prefix=prefix)
                    if new_sf.is_valid():
                        new_sf.save()
        messages.success(request, _("Loans updated successfully."))
        return HttpResponseRedirect(
            reverse("property:detail", kwargs={"pk": property_obj.pk}) + "#loans-panel"
        )

    messages.error(request, _("Please correct the errors below."))
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
