"""Context processors for the property app."""

from property.models import Property


def nav_properties(request):
    """Expose favorite active properties list for the global navigation dropdown."""
    if not request.user.is_authenticated:
        return {"nav_properties": [], "nav_properties_any": False}
    favorites = list(
        Property.objects.filter(is_active=True, is_favorite=True).order_by("name")
    )
    has_any = Property.objects.filter(is_active=True).exists()
    return {
        "nav_properties": favorites,
        "nav_properties_any": has_any,
    }
