"""Search index behind the ⌘K asset search of the header."""

from django.http import HttpRequest, JsonResponse
from django.urls import reverse
from django.utils.translation import gettext as _

from finance.models.investment_account import InvestmentAccount
from finance.models.other_asset import OtherAsset
from finance.models.saving_account import SavingAccount
from property.models import Property
from property.models.scpi import SCPI


def _entry(label: str, sub: str, url: str, icon: str, kind: str) -> dict:
    return {"label": label, "sub": sub, "url": url, "icon": icon, "kind": kind}


def _accounts():
    for model, url_name, icon in (
        (InvestmentAccount, "finance:investment_detail", "chart-line"),
        (SavingAccount, "finance:saving_detail", "piggy-bank"),
    ):
        accounts = model.objects.select_related("account_type").order_by(
            "-is_active", "name"
        )
        for account in accounts:
            sub = " · ".join(
                part
                for part in (account.account_type.name, account.institution)
                if part
            )
            yield _entry(
                str(account),
                sub,
                reverse(url_name, kwargs={"pk": account.pk}),
                icon,
                "account",
            )


def _properties():
    for prop in Property.objects.order_by("-is_active", "name"):
        yield _entry(
            prop.name,
            prop.full_address,
            reverse("property:detail", kwargs={"pk": prop.pk}),
            prop.icon,
            "property",
        )
    for scpi in SCPI.objects.order_by("name"):
        yield _entry(
            scpi.name,
            scpi.management_company,
            reverse("property:scpi_fund_detail", kwargs={"scpi_pk": scpi.pk}),
            "building",
            "scpi",
        )


def _other_assets():
    for asset in OtherAsset.objects.order_by("-is_active", "name"):
        yield _entry(
            asset.name,
            asset.get_category_display(),  # ty: ignore[unresolved-attribute]
            reverse("finance:other_asset_detail", kwargs={"pk": asset.pk}),
            asset.icon,
            "other",
        )


def _pages():
    pages = (
        (_("Dashboard"), "index", "layout-dashboard"),
        (_("Finance"), "finance:index", "wallet"),
        (_("Properties"), "property:index", "house"),
        (_("SCPI"), "property:scpi_list", "building"),
        (_("Other assets"), "finance:other_asset_list", "gem"),
        (_("Allocation"), "allocation", "chart-pie"),
        (_("Net worth by owner"), "owners", "users"),
        (_("Deadlines"), "deadlines", "calendar-clock"),
        (_("Operations"), "operations", "arrow-left-right"),
        (_("All Loans"), "property:all_loans", "landmark"),
        (_("Settings"), "accounts:settings", "settings"),
    )
    for label, url_name, icon in pages:
        yield _entry(str(label), _("Page"), reverse(url_name), icon, "page")


def api_search(request: HttpRequest) -> JsonResponse:
    """Every asset and page the header search can jump to.

    The client filters this list itself, so it is fetched once per session.
    """
    items = [*_accounts(), *_properties(), *_other_assets(), *_pages()]
    return JsonResponse({"items": items})
