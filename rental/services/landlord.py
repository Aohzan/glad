"""Identity of the landlord written on the leases, receipts and letters."""

from dataclasses import dataclass

from django.contrib.auth import get_user_model

from property.models import Property


@dataclass(frozen=True)
class Landlord:
    name: str
    address: str

    @property
    def is_complete(self) -> bool:
        return bool(self.name and self.address)


def _full_name(user) -> str:
    return user.get_full_name() or user.get_username()


def _postal_address(user) -> str:
    return getattr(getattr(user, "profile", None), "postal_address", "")


def landlord_of(prop: Property) -> Landlord:
    """The landlord of *prop*: its own landlord fields, else its owners.

    A property without ownership rows is held by the whole household: its
    adults are the landlords. Prefetch ``ownerships__user__profile`` when
    looping over properties.
    """
    owners = [o.user for o in prop.ownerships.all()]
    if not owners:
        owners = list(
            get_user_model()
            .objects.filter(is_active=True, profile__is_child=False)
            .select_related("profile")
            .order_by("pk")
        )
    name = prop.landlord_name or " & ".join(_full_name(user) for user in owners)
    address = prop.landlord_address or next(
        (_postal_address(user) for user in owners if _postal_address(user)), ""
    )
    return Landlord(name=name, address=address)
