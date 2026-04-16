"""Property edit view (property + loans + schedules)."""

from typing import Any

from django.contrib import messages
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _

from property.forms import (
    PropertyEditForm,
    PropertyLoanForm,
    PropertyLoanScheduleForm,
)
from property.models import Property, PropertyLoan, PropertyLoanSchedule


def edit_property(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit a property and its associated loans (including smoothed loan schedules)."""
    property_obj = get_object_or_404(Property, pk=pk)

    PropertyLoanFormSet = inlineformset_factory(
        Property,
        PropertyLoan,
        form=PropertyLoanForm,
        extra=1,
        can_delete=True,
    )

    ScheduleFormSet = inlineformset_factory(
        PropertyLoan,
        PropertyLoanSchedule,
        form=PropertyLoanScheduleForm,
        extra=1,
        can_delete=True,
    )

    existing_loans = list(PropertyLoan.objects.filter(property=property_obj))

    if request.method == "POST":
        property_form = PropertyEditForm(request.POST, instance=property_obj)
        loan_formset = PropertyLoanFormSet(request.POST, instance=property_obj)

        # Build schedule formsets for each existing loan
        schedule_formsets: dict[int, BaseInlineFormSet[Any, Any, Any]] = {}
        for loan in existing_loans:
            prefix = f"schedules_{loan.pk}"
            schedule_formsets[loan.pk] = ScheduleFormSet(
                request.POST, instance=loan, prefix=prefix
            )

        all_valid = property_form.is_valid() and loan_formset.is_valid()
        for sf in schedule_formsets.values():
            if not sf.is_valid():
                all_valid = False

        if all_valid:
            property_form.save()
            saved_loans = loan_formset.save()
            # Save schedule formsets for existing loans
            for sf in schedule_formsets.values():
                sf.save()
            # Save schedule formsets for newly created loans (empty by default)
            for loan in saved_loans:
                if loan.pk not in schedule_formsets:
                    prefix = f"schedules_{loan.pk}"
                    new_sf = ScheduleFormSet(request.POST, instance=loan, prefix=prefix)
                    if new_sf.is_valid():
                        new_sf.save()
            messages.success(request, _("Property updated successfully."))
            return redirect("property:detail", pk=property_obj.pk)
        else:
            messages.error(request, _("Please correct the errors below."))
    else:
        property_form = PropertyEditForm(instance=property_obj)
        loan_formset = PropertyLoanFormSet(instance=property_obj)
        schedule_formsets: dict[int, BaseInlineFormSet[Any, Any, Any]] = {}
        for loan in existing_loans:
            prefix = f"schedules_{loan.pk}"
            schedule_formsets[loan.pk] = ScheduleFormSet(instance=loan, prefix=prefix)

    # Pair each loan form with its schedule formset for template rendering
    loan_forms_with_schedules = []
    for form in loan_formset.forms:
        loan_pk: int | None = form.instance.pk if form.instance.pk else None
        sf = schedule_formsets.get(loan_pk) if loan_pk is not None else None
        is_smoothed = form.instance.is_smoothed() if loan_pk is not None else False
        loan_forms_with_schedules.append(
            {
                "form": form,
                "schedule_formset": sf,
                "is_smoothed": is_smoothed,
            }
        )

    context = {
        "property": property_obj,
        "property_form": property_form,
        "loan_formset": loan_formset,
        "loan_forms_with_schedules": loan_forms_with_schedules,
    }
    return render(request, "property/edit.html", context)
