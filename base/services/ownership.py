"""Who owns what: household shares, dismemberment values and net worth per person.

The value of a dismembered right follows article 669 CGI:

- a life usufruct is worth a percentage of the full value that decreases with
  the age of the usufructuary (90 % before 21 years, then 10 points less every
  ten years, down to 10 % from 91 years);
- a temporary usufruct is worth 23 % per period of ten years, any started
  period counting in full;
- the bare ownership is worth the rest.
"""

import datetime
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Model
from django.urls import reverse
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

from accounts.models import is_child
from base.models import Ownership, display_name, household_members
from finance.models.investment_account import InvestmentAccount
from finance.models.other_asset import OtherAsset
from finance.models.saving_account import SavingAccount
from property.models import Property
from property.models.scpi import SCPIInvestment

#: (upper age bound, usufruct percentage) of article 669 I CGI.
LIFE_USUFRUCT_SCALE = (
    (21, 90),
    (31, 80),
    (41, 70),
    (51, 60),
    (61, 50),
    (71, 40),
    (81, 30),
    (91, 20),
)
LIFE_USUFRUCT_MIN = 10
TEMPORARY_USUFRUCT_PER_DECADE = 23


def life_usufruct_percent(birth_date: datetime.date, as_of: datetime.date) -> int:
    """Value of a life usufruct, in percent of the full ownership."""
    age = relativedelta(as_of, birth_date).years
    for bound, percent in LIFE_USUFRUCT_SCALE:
        if age < bound:
            return percent
    return LIFE_USUFRUCT_MIN


def temporary_usufruct_percent(end_date: datetime.date, as_of: datetime.date) -> int:
    """Value of a usufruct ending on *end_date*, in percent of the full ownership."""
    days = (end_date - as_of).days
    if days <= 0:
        return 0
    periods = math.ceil(days / 365.25 / 10)
    return min(100, periods * TEMPORARY_USUFRUCT_PER_DECADE)


def usufruct_percent(ownership: Ownership, as_of: datetime.date) -> int | None:
    """Usufruct value of a dismembered ownership, None when it cannot be valued."""
    if ownership.usufruct_end_date:
        return temporary_usufruct_percent(ownership.usufruct_end_date, as_of)
    birth_date = ownership.usufructuary_birth_date
    if birth_date is None and ownership.right == Ownership.Right.USUFRUCT:
        birth_date = getattr(
            getattr(ownership.user, "profile", None), "birth_date", None
        )
    if birth_date is None:
        return None
    return life_usufruct_percent(birth_date, as_of)


def missing_birth_dates() -> list:
    """Holders of a life usufruct that cannot be valued without their birth date."""
    holders = Ownership.objects.filter(
        right=Ownership.Right.USUFRUCT,
        usufruct_end_date__isnull=True,
        usufructuary_birth_date__isnull=True,
        user__profile__isnull=False,
        user__profile__birth_date__isnull=True,
    ).values("user")
    return list(household_members().filter(pk__in=holders))


def right_ratio(ownership: Ownership, as_of: datetime.date) -> Decimal | None:
    """Part of the full value the right is worth (1 for full ownership)."""
    if ownership.right == Ownership.Right.FULL:
        return Decimal(1)
    percent = usufruct_percent(ownership, as_of)
    if percent is None:
        return None
    if ownership.right == Ownership.Right.BARE:
        percent = 100 - percent
    return Decimal(percent) / 100


@dataclass(frozen=True)
class AssetKind:
    """An asset model that can be owned."""

    model: type[Model]
    label: str | Promise
    url_name: str
    url_kwarg: str = "pk"
    #: True when the ownership can be dismembered (the SCPI investments carry
    #: their own dismemberment, accounts cannot be dismembered).
    dismemberable: bool = False

    def detail_url(self, obj) -> str:
        """URL of the asset detail page."""
        if isinstance(obj, SCPIInvestment):
            return reverse(self.url_name, kwargs={"scpi_pk": obj.scpi_id})
        return reverse(self.url_name, kwargs={self.url_kwarg: obj.pk})


ASSET_KINDS: dict[str, AssetKind] = {
    "saving": AssetKind(SavingAccount, _("Saving account"), "finance:saving_detail"),
    "investment": AssetKind(
        InvestmentAccount, _("Investment account"), "finance:investment_detail"
    ),
    "property": AssetKind(
        Property, _("Property"), "property:detail", dismemberable=True
    ),
    "scpi": AssetKind(SCPIInvestment, _("SCPI"), "property:scpi_fund_detail"),
    "other": AssetKind(
        OtherAsset, _("Other asset"), "finance:other_asset_detail", dismemberable=True
    ),
}


def kind_of(obj) -> str:
    """Key of ASSET_KINDS for an asset instance."""
    for key, kind in ASSET_KINDS.items():
        if isinstance(obj, kind.model):
            return key
    raise KeyError(type(obj).__name__)


def ownerships_of(obj) -> list[Ownership]:
    """Ownership rows of an asset, largest share first."""
    return list(
        Ownership.objects.filter(
            content_type=ContentType.objects.get_for_model(obj), object_id=obj.pk
        ).select_related("user", "user__profile")
    )


#: Smallest share an owner can hold (the validator of ``Ownership.share``).
MIN_SHARE = Decimal("0.01")


def split_equally(total: Decimal, count: int) -> list[Decimal]:
    """*total* split in *count* shares of two decimals, the last one taking the rest."""
    part = (total / count).quantize(MIN_SHARE, rounding=ROUND_DOWN)
    return [part] * (count - 1) + [total - part * (count - 1)]


class NoShareLeftError(ValueError):
    """The other rights of the asset leave no share to the new full owners."""


@dataclass
class OwnersPlan:
    """Ownership rows to delete and to save for a new selection of owners."""

    delete: list[Ownership] = field(default_factory=list)
    save: list[Ownership] = field(default_factory=list)


def plan_owners(rows: list[Ownership], users: Iterable) -> OwnersPlan:
    """Changes making *users* the exact owners of an asset held through *rows*.

    Unselected owners are removed and the others keep their right. When the
    full owners change (one added or one holding the full ownership removed),
    the part held in full ownership is split equally between the remaining and
    the new full owners, so the part held outside the household is kept. A
    finer split or a dismembered right is set on the owners page.

    Raises NoShareLeftError when the dismembered rights leave no share to the
    new owners.
    """
    users = list(users)
    selected = {user.pk for user in users}
    current = {row.user_id for row in rows}  # ty: ignore[unresolved-attribute]
    removed = [row for row in rows if row.user_id not in selected]  # ty: ignore[unresolved-attribute]
    new_users = [user for user in users if user.pk not in current]
    full = Ownership.Right.FULL
    if not new_users and all(row.right != full for row in removed):
        return OwnersPlan(delete=removed)
    kept = [row for row in rows if row.user_id in selected]  # ty: ignore[unresolved-attribute]
    if any(row.right == full for row in rows):
        pool = sum((row.share for row in rows if row.right == full), Decimal(0))
    else:
        pool = Decimal(100) - max(
            sum((row.share for row in kept if row.right == right), Decimal(0))
            for right in (Ownership.Right.BARE, Ownership.Right.USUFRUCT)
        )
    holders = [row for row in kept if row.right == full] + [
        Ownership(user=user, right=full) for user in new_users
    ]
    if not holders:
        return OwnersPlan(delete=removed)
    shares = split_equally(pool, len(holders))
    if min(shares) < MIN_SHARE:
        raise NoShareLeftError
    for row, share in zip(holders, shares, strict=True):
        row.share = share
    return OwnersPlan(delete=removed, save=holders)


def plan_shares(rows: list[Ownership], shares: dict) -> OwnersPlan:
    """Changes making the users of *shares* the full owners of an asset held through *rows*.

    *shares* maps each user to the percentage of the asset they hold; the
    owners left out are removed.
    """
    by_user = {row.user_id: row for row in rows}  # ty: ignore[unresolved-attribute]
    plan = OwnersPlan(
        delete=[row for row in rows if row.user_id not in {u.pk for u in shares}]  # ty: ignore[unresolved-attribute]
    )
    for user, share in shares.items():
        row = by_user.get(user.pk) or Ownership(user=user)
        if row.pk and row.share == share and row.right == Ownership.Right.FULL:
            continue
        row.share, row.right = share, Ownership.Right.FULL
        plan.save.append(row)
    return plan


@transaction.atomic
def apply_owners(asset, plan: OwnersPlan) -> None:
    """Delete and save the ownership rows of *plan* for *asset*."""
    if plan.delete:
        Ownership.objects.filter(pk__in=[row.pk for row in plan.delete]).delete()
    content_type = ContentType.objects.get_for_model(asset)
    for row in plan.save:
        row.content_type = content_type
        row.object_id = asset.pk
        row.save()


@dataclass
class PersonWorth:
    """Net worth of one person (or of the unassigned and outside parts)."""

    label: str
    by_kind: dict[str, Decimal] = field(default_factory=dict)
    unvalued: list[str] = field(default_factory=list)
    is_child: bool = False

    @property
    def total(self) -> Decimal:
        """Sum of every kind."""
        return sum(self.by_kind.values(), Decimal(0))

    def add(self, kind: str, amount: Decimal) -> None:
        """Add *amount* to the total of *kind*."""
        self.by_kind[kind] = self.by_kind.get(kind, Decimal(0)) + amount


def _current_value(obj, today: datetime.date) -> Decimal | None:
    if isinstance(obj, Property):
        return obj.net_value.amount
    if isinstance(obj, SCPIInvestment):
        return obj.get_estimated_value(today).amount
    return obj.current_value.amount


def _assets():
    yield from SavingAccount.objects.active()
    yield from InvestmentAccount.objects.active()
    yield from Property.objects.filter(is_active=True)
    yield from SCPIInvestment.objects.filter(sold_date__isnull=True).select_related(
        "scpi"
    )
    yield from OtherAsset.objects.filter(is_active=True)


def net_worth_by_person(
    currency: str | None = None, today: datetime.date | None = None
) -> tuple[list[PersonWorth], PersonWorth, PersonWorth]:
    """Net worth of each household member, of the unassigned assets and of outside owners.

    Returns ``(people, unassigned, outside)``: *unassigned* sums the assets
    without ownership row, *outside* the part of the assets held by people
    who are not household members (shares below 100 %, the other side of a
    dismembered right, former users). Assets in another currency than
    *currency* are left out.
    """
    currency = currency or settings.DEFAULT_CURRENCY
    today = today or datetime.date.today()
    people = {
        u.pk: PersonWorth(label=display_name(u), is_child=is_child(u))
        for u in household_members()
    }
    unassigned = PersonWorth(label=str(_("Not assigned")))
    outside = PersonWorth(label=str(_("Outside the household")))

    rows = ownership_index()
    content_types = ContentType.objects.get_for_models(
        *(k.model for k in ASSET_KINDS.values())
    )

    for obj in _assets():
        if obj.currency != currency:
            continue
        kind = kind_of(obj)
        value = _current_value(obj, today)
        if not value:
            continue
        owners = rows.get((content_types[type(obj)].pk, obj.pk))
        if not owners:
            unassigned.add(kind, value)
            continue
        held = Decimal(0)
        for owner in owners:
            person = people.get(owner.user_id)  # ty: ignore[unresolved-attribute]
            if person is None:
                continue
            ratio = right_ratio(owner, today)
            if ratio is None:
                # A dismembered right without date cannot be valued: its full
                # share stays unassigned.
                part = value * owner.share / 100
                held += part
                unassigned.add(kind, part)
                person.unvalued.append(str(obj))
                continue
            part = value * owner.share / 100 * ratio
            held += part
            person.add(kind, part)
        if value - held:
            outside.add(kind, value - held)
    return list(people.values()), unassigned, outside


def held_ratio(
    rows: list[Ownership],
    people: set[int],
    today: datetime.date,
    *,
    household: bool = False,
) -> Decimal:
    """Part of the value of an asset held by the users *people*.

    With *household*, *people* are all the household members, who also hold
    the assets without owner and the dismembered rights that cannot be valued,
    as in :func:`net_worth_by_person`.
    """
    if not rows:
        return Decimal(1) if household else Decimal(0)
    ratio = Decimal(0)
    for row in rows:
        if row.user_id not in people:  # ty: ignore[unresolved-attribute]
            continue
        right = right_ratio(row, today)
        if right is None:
            if household:
                ratio += row.share / 100
            continue
        ratio += row.share / 100 * right
    return ratio


def ownership_index() -> dict[tuple[int, int], list[Ownership]]:
    """Every ownership row keyed by ``(content_type_id, object_id)``, in one query."""
    index: dict[tuple[int, int], list[Ownership]] = {}
    for row in Ownership.objects.select_related("user", "user__profile"):
        index.setdefault((row.content_type_id, row.object_id), []).append(row)  # ty: ignore[unresolved-attribute]
    return index


def holder_label(rows: list[Ownership]) -> str:
    """Short name of who holds an asset, for lists and filters.

    A single owner is named (with the dismembered right when there is one),
    several owners hold it jointly; without any ownership row the whole
    household holds it.
    """
    if not rows:
        return str(_("Household"))
    if len(rows) > 1:
        return str(_("Joint"))
    row = rows[0]
    name = display_name(row.user)
    if row.right == Ownership.Right.BARE:
        return str(_("%(name)s (bare)") % {"name": name})
    if row.right == Ownership.Right.USUFRUCT:
        return str(_("%(name)s (usufruct)") % {"name": name})
    return name


class HolderResolver:
    """Holder labels of many assets, from a single ownership query."""

    def __init__(self):
        self.index = ownership_index()
        self.content_types = ContentType.objects.get_for_models(
            *(kind.model for kind in ASSET_KINDS.values())
        )

    def rows(self, obj) -> list[Ownership]:
        """Ownership rows of *obj*."""
        content_type = self.content_types.get(type(obj))
        if content_type is None:
            return []
        return self.index.get((content_type.pk, obj.pk), [])

    def label(self, *objs) -> str:
        """Holder of *objs* taken together (e.g. the investments of one fund)."""
        rows: dict[int, Ownership] = {}
        for obj in objs:
            for row in self.rows(obj):
                rows.setdefault(row.user_id, row)  # ty: ignore[unresolved-attribute]
        return holder_label(list(rows.values()))
