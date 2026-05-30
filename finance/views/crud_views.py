"""Generic CRUD helpers for finance account-related models."""

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _


def _edit_account_related(
    request: HttpRequest,
    *,
    account_pk: int,
    account_model,
    model,
    object_pk: int | None,
    form_class,
    template: str,
    context_key: str,
    success_message: str,
    detail_url_name: str,
    anchor: str,
    parent_field: str = "account",
) -> HttpResponse:
    """Shared create/edit logic for models that belong to an account."""
    account = get_object_or_404(account_model, pk=account_pk)
    obj = (
        get_object_or_404(model, pk=object_pk, **{parent_field: account})
        if object_pk
        else None
    )

    if request.method == "POST":
        form = form_class(request.POST, instance=obj)
        if form.is_valid():
            created = form.save(commit=False)
            setattr(created, parent_field, account)
            created.save()
            messages.success(request, success_message)
            return HttpResponseRedirect(
                reverse(detail_url_name, kwargs={"pk": account_pk}) + anchor
            )
        messages.error(request, _("Please correct the errors below."))
    else:
        form = form_class(instance=obj)

    return render(
        request,
        template,
        {"account": account, context_key: obj, "form": form},
    )


def _delete_account_related(
    request: HttpRequest,
    *,
    account_pk: int,
    account_model,
    model,
    object_pk: int,
    success_message: str,
    detail_url_name: str,
    anchor: str,
    parent_field: str = "account",
) -> HttpResponse:
    """Shared delete logic for models that belong to an account."""
    if request.method != "POST":
        messages.error(request, _("Invalid request method."))
        return redirect(detail_url_name, pk=account_pk)

    account = get_object_or_404(account_model, pk=account_pk)
    obj = get_object_or_404(model, pk=object_pk, **{parent_field: account})
    obj.delete()
    messages.success(request, success_message)
    return HttpResponseRedirect(
        reverse(detail_url_name, kwargs={"pk": account_pk}) + anchor
    )
