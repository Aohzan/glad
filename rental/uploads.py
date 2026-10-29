"""Upload of the documents of the leases and the applications."""

from collections.abc import Callable

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import models
from django.http import HttpRequest
from django.utils.translation import gettext as _

from base.services.documents import attach_upload
from rental.forms import DocumentUploadForm


def store_upload(
    request: HttpRequest,
    form: DocumentUploadForm,
    target_of: Callable[[str], models.Model],
) -> bool:
    """Store the uploaded file on ``target_of(kind)``; False with the form errors."""
    if form.is_valid():
        try:
            attach_upload(
                target_of(form.cleaned_data["kind"]),
                form.cleaned_data["file"],
                title=form.cleaned_data["title"],
                kind=form.cleaned_data["kind"],
                valid_until=form.cleaned_data["valid_until"],
                user=request.user,
            )
        except ValidationError as exc:
            form.add_error("file", exc)
        else:
            messages.success(request, _("Document added."))
            return True
    messages.error(request, _("Please correct the errors below."))
    return False
