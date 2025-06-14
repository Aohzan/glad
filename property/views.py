"""Views for the property app."""

from django.http import HttpResponse


def index(request):
    """Index view for the property app."""
    return HttpResponse("Hello, world. You're at the property index.")
