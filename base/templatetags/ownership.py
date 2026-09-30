"""Template tag summarizing the owners of an asset."""

from django import template
from django.urls import reverse

from base.services.ownership import kind_of, ownerships_of

register = template.Library()


@register.inclusion_tag("_owners_summary.html")
def owners_summary(asset, legacy_owner: str = ""):
    """Owners of *asset* with a link to manage them.

    *legacy_owner* is the free-text owner shown while no user is assigned.
    """
    return {
        "rows": ownerships_of(asset),
        "legacy_owner": legacy_owner,
        "manage_url": reverse(
            "manage_owners", kwargs={"kind": kind_of(asset), "pk": asset.pk}
        ),
    }
