"""Views managing the members of the household, outside the administration."""

import copy

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from base.models import household_members

from .forms import HouseholdMemberForm, can_edit_member
from .models import is_child


def household(request: HttpRequest) -> HttpResponse:
    """Members of the household: adults first, then children."""
    members = [
        {
            "user": member,
            "is_child": is_child(member),
            "can_log_in": member.has_usable_password(),
            "birth_date": getattr(getattr(member, "profile", None), "birth_date", None),
            "editable": can_edit_member(request.user, member),
        }
        for member in household_members()
    ]
    return render(request, "accounts/household.html", {"members": members})


def household_member(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """Add a member of the household, or edit one when *pk* is given."""
    member = (
        get_object_or_404(get_user_model(), pk=pk, is_active=True)
        if pk is not None
        else None
    )
    if member is not None and not can_edit_member(request.user, member):
        raise PermissionDenied
    # The form works on a copy: a rejected submission leaves the title as stored.
    form = HouseholdMemberForm(
        request.POST or None,
        instance=copy.copy(member) if member is not None else None,
        acting_user=request.user,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Household member saved."))
        return redirect("accounts:household")
    return render(
        request, "accounts/household_member.html", {"form": form, "member": member}
    )
