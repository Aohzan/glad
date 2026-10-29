"""Download and deletion of the stored documents.

Files are only reachable through these views, behind the login: there is no
public media URL. Images are shown inline, every other type is downloaded.
"""

from pathlib import Path

from django.contrib import messages
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from base.models import Document


def _safe_next(request: HttpRequest) -> str:
    next_url = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return reverse("index")


def download_document(request: HttpRequest, pk: int) -> FileResponse:
    """Send the file of a document."""
    document = get_object_or_404(Document, pk=pk)
    try:
        handle = document.file.open("rb")
    except FileNotFoundError as exc:
        raise Http404(_("The file of this document is missing.")) from exc
    response = FileResponse(
        handle,
        as_attachment=not document.is_image,
        filename=document.original_name or Path(document.file.name or "").name,
        content_type=document.mime_type or "application/octet-stream",
    )
    response["Cache-Control"] = "private, no-store"
    return response


@require_POST  # type: ignore
def delete_document(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a document and its file, then go back to the ``next`` page."""
    document = get_object_or_404(Document, pk=pk)
    document.delete()
    messages.success(request, _("Document deleted."))
    return redirect(_safe_next(request))
