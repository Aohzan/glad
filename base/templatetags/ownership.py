"""Template tag summarizing the owners of an asset."""

from django import template
from django.urls import reverse

from base.services.ownership import kind_of, ownerships_of

register = template.Library()


@register.inclusion_tag("_owners_summary.html")
def owners_summary(asset):
    """Owners of *asset* with a link to manage them."""
    return {
        "rows": ownerships_of(asset),
        "manage_url": reverse(
            "manage_owners", kwargs={"kind": kind_of(asset), "pk": asset.pk}
        ),
    }
