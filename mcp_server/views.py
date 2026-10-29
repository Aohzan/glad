"""Settings page of the MCP access: API keys and call log."""

from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from mcp_server.forms import ApiKeyForm
from mcp_server.models import ApiKey, McpCallLog

#: Calls shown on the settings page.
LOG_SIZE = 50


#: Session key holding a new API key until the page shows it.
NEW_KEY_SESSION = "mcp_new_api_key"


def _endpoint(request: HttpRequest) -> str:
    return f"{settings.APP_URL or request.build_absolute_uri('/').rstrip('/')}/mcp"


def _render(request: HttpRequest, form: ApiKeyForm, status: int = 200, **extra):
    return render(
        request,
        "mcp_server/settings.html",
        {
            "keys": ApiKey.objects.filter(user=request.user),
            "calls": McpCallLog.objects.filter(
                api_key__user=request.user
            ).select_related("api_key")[:LOG_SIZE],
            "form": form,
            "endpoint": _endpoint(request),
            **extra,
        },
        status=status,
    )


def mcp_settings(request: HttpRequest) -> HttpResponse:
    """The API keys of the user and their latest calls; a new key is shown once."""
    return _render(
        request, ApiKeyForm(), new_key=request.session.pop(NEW_KEY_SESSION, None)
    )


@require_POST  # type: ignore
def add_key(request: HttpRequest) -> HttpResponse:
    """Create a key, kept in the session for the next page only."""
    form = ApiKeyForm(request.POST)
    if not form.is_valid():
        return _render(request, form, status=400)
    key, raw = ApiKey.create(
        request.user, form.cleaned_data["name"], form.cleaned_data["can_write"]
    )
    request.session[NEW_KEY_SESSION] = raw
    messages.success(request, _("Key “%(name)s” created.") % {"name": key.name})
    return redirect(f"{reverse('mcp_server:settings')}#keys")


@require_POST  # type: ignore
def toggle_key(request: HttpRequest, pk: int) -> HttpResponse:
    key = get_object_or_404(ApiKey, pk=pk, user=request.user)
    key.is_active = not key.is_active
    key.save(update_fields=["is_active", "updated_at"])
    return redirect(f"{reverse('mcp_server:settings')}#keys")


@require_POST  # type: ignore
def delete_key(request: HttpRequest, pk: int) -> HttpResponse:
    key = get_object_or_404(ApiKey, pk=pk, user=request.user)
    key.delete()
    messages.success(request, _("Key “%(name)s” deleted.") % {"name": key.name})
    return redirect(f"{reverse('mcp_server:settings')}#keys")
