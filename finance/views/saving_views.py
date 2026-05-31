"""Views for saving account CRUD operations."""

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from finance.forms import (
    SavingAccountDepositForm,
    SavingAccountForm,
    SavingAccountValueForm,
)
from finance.models.saving_account import (
    SavingAccount,
    SavingAccountDeposit,
    SavingAccountValue,
)
from finance.views.crud_views import _delete_account_related, _edit_account_related

DETAIL_URL = "finance:saving_detail"


# ─── Saving account CRUD ─────────────────────────────────────────────────────


def saving_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Detail view for a saving account."""
    account = get_object_or_404(SavingAccount, pk=pk)
    values = account.values.order_by("-value_date")  # type: ignore[union-attr]
    deposits = account.deposits.order_by("-deposit_date")
    progression = account.get_progression(days=30)
    total_deposits, capital_gain = account.compute_capital_gain()

    return render(
        request,
        "finance/saving_detail.html",
        {
            "account": account,
            "values": values,
            "deposits": deposits,
            "progression": progression,
            "total_deposits": total_deposits,
            "capital_gain": capital_gain,
        },
    )


def create_saving(request: HttpRequest) -> HttpResponse:
    """Create a new saving account."""
    if request.method == "POST":
        form = SavingAccountForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Saving account created successfully."))
            return redirect(DETAIL_URL, pk=form.instance.pk)
        messages.error(request, _("Please correct the errors below."))
    else:
        form = SavingAccountForm()

    return render(
        request,
        "finance/edit_saving.html",
        {
            "form": form,
            "account_back_url": reverse("finance:index"),
            "account_back_label": "Finance",
            "account_cancel_url": reverse("finance:index"),
        },
    )


def edit_saving(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit an existing saving account."""
    account = get_object_or_404(SavingAccount, pk=pk)

    if request.method == "POST":
        form = SavingAccountForm(request.POST, instance=account)
        if form.is_valid():
            form.save()
            messages.success(request, _("Saving account updated successfully."))
            return redirect(DETAIL_URL, pk=account.pk)
        messages.error(request, _("Please correct the errors below."))
    else:
        form = SavingAccountForm(instance=account)

    return render(
        request,
        "finance/edit_saving.html",
        {
            "form": form,
            "account": account,
            "account_back_url": reverse("finance:saving_detail", args=[account.pk]),
            "account_back_label": str(account),
            "account_cancel_url": reverse("finance:saving_detail", args=[account.pk]),
        },
    )


def delete_saving(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a saving account."""
    if request.method != "POST":
        messages.error(request, _("Invalid request method."))
        return redirect(DETAIL_URL, pk=pk)

    account = get_object_or_404(SavingAccount, pk=pk)
    account.delete()
    messages.success(request, _("Saving account deleted successfully."))
    return redirect("finance:index")


# ─── Saving value CRUD ────────────────────────────────────────────────────────


def edit_saving_value(
    request: HttpRequest, account_pk: int, value_pk: int | None = None
) -> HttpResponse:
    """Create or edit a saving account value entry."""
    return _edit_account_related(
        request,
        account_pk=account_pk,
        account_model=SavingAccount,
        model=SavingAccountValue,
        object_pk=value_pk,
        form_class=SavingAccountValueForm,
        template="finance/edit_saving_value.html",
        context_key="value",
        success_message=_("Value entry saved successfully."),
        detail_url_name=DETAIL_URL,
        anchor="#values-panel",
    )


def delete_saving_value(
    request: HttpRequest, account_pk: int, value_pk: int
) -> HttpResponse:
    """Delete a saving account value entry."""
    return _delete_account_related(
        request,
        account_pk=account_pk,
        account_model=SavingAccount,
        model=SavingAccountValue,
        object_pk=value_pk,
        success_message=_("Value entry deleted successfully."),
        detail_url_name=DETAIL_URL,
        anchor="#values-panel",
    )


# ─── Saving deposit CRUD ─────────────────────────────────────────────────────


def edit_saving_deposit(
    request: HttpRequest, account_pk: int, deposit_pk: int | None = None
) -> HttpResponse:
    """Create or edit a saving account deposit."""
    return _edit_account_related(
        request,
        account_pk=account_pk,
        account_model=SavingAccount,
        model=SavingAccountDeposit,
        object_pk=deposit_pk,
        form_class=SavingAccountDepositForm,
        template="finance/edit_saving_deposit.html",
        context_key="deposit",
        success_message=_("Deposit saved successfully."),
        detail_url_name=DETAIL_URL,
        anchor="#deposits-panel",
    )


def delete_saving_deposit(
    request: HttpRequest, account_pk: int, deposit_pk: int
) -> HttpResponse:
    """Delete a saving account deposit."""
    return _delete_account_related(
        request,
        account_pk=account_pk,
        account_model=SavingAccount,
        model=SavingAccountDeposit,
        object_pk=deposit_pk,
        success_message=_("Deposit deleted successfully."),
        detail_url_name=DETAIL_URL,
        anchor="#deposits-panel",
    )


@require_POST  # type: ignore
def toggle_saving_favorite(request: HttpRequest, pk: int) -> HttpResponse:
    """Toggle the is_favorite flag for a saving account."""
    account = get_object_or_404(SavingAccount, pk=pk)
    account.is_favorite = not account.is_favorite
    account.save(update_fields=["is_favorite"])
    return redirect(request.META.get("HTTP_REFERER") or reverse("finance:index"))
