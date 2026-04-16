"""Context processors for the property app."""

from property.models import Property


def nav_properties(request):
    """Expose active properties list for the global navigation dropdown."""
    if not request.user.is_authenticated:
        return {"nav_properties": []}
    return {
        "nav_properties": Property.objects.filter(is_active=True).order_by("name"),
    }
