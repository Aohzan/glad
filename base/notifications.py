"""Notification types about the whole application and the household."""

import datetime
import logging
from collections.abc import Iterator
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from django.db.models import Max
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext
from moneyed import Money
lazy import httpx

from base.services.dashboard import default_currency, hero_summary, registry
from base.templatetags.format_money import format_money_filter
from finance.models.investment_account import InvestmentAccount
from finance.models.other_asset import OtherAsset
from finance.models.saving_account import SavingAccount
from notifications.checks import days_before_param, month_day, when
from notifications.registry import Event, NotificationType, Param, register
from property.models import Property

logger = logging.getLogger(__name__)

RELEASES_URL = "https://api.github.com/repos/Aohzan/glad/releases/latest"


def _as_date(value: datetime.date | datetime.datetime | None) -> datetime.date | None:
    if isinstance(value, datetime.datetime):
        return value.date()
    return value


def stale_assets(
    today: datetime.date, days: int, long_days: int
) -> list[tuple[str, datetime.date]]:
    """Assets whose last value is older than their limit: (name, last date)."""
    result = []
    short_limit = today - datetime.timedelta(days=days)
    long_limit = today - datetime.timedelta(days=long_days)
    for account in SavingAccount.objects.active().annotate(
        last=Max("values__value_date")
    ):
        result.append((str(account), _as_date(account.last), short_limit))
    for account in InvestmentAccount.objects.active().annotate(
        last_cash=Max("cash_values__value_date"),
        last_holding=Max(
            "investmentaccountholding__investmentaccountholdinghistory__valuation_date"
        ),
    ):
        dates = [
            d
            for d in (
                _as_date(account.last_cash),
                _as_date(account.last_holding),
            )
            if d
        ]
        result.append((str(account), max(dates) if dates else None, short_limit))
    for asset in OtherAsset.objects.filter(is_active=True).annotate(
        last=Max("values__value_date")
    ):
        result.append((str(asset), _as_date(asset.last), short_limit))  # ty: ignore[unresolved-attribute]
    for prop in Property.objects.filter(is_active=True).annotate(
        last=Max("property_values__valuation_date")
    ):
        result.append((str(prop), _as_date(prop.last), long_limit))  # ty: ignore[unresolved-attribute]
    return sorted(
        (name, last)
        for name, last, limit in result
        if last is not None and last < limit
    )


def _stale_data(params: dict[str, Any], today: datetime.date) -> Iterator[Event]:
    stale = stale_assets(today, params["days"], params["long_days"])
    if not stale:
        return
    yield Event(
        key="stale",
        title=ngettext(
            "%(count)d asset to update",
            "%(count)d assets to update",
            len(stale),
        )
        % {"count": len(stale)},
        body="\n".join(
            _("%(asset)s: last value on %(date)s")
            % {"asset": name, "date": date_format(last, "SHORT_DATE_FORMAT")}
            for name, last in stale
        ),
        url=reverse("finance:update"),
    )


def _income_tax_return(params: dict[str, Any], today: datetime.date) -> Iterator[Event]:
    opening = month_day(params["opening"], today.year)
    deadline = month_day(params["deadline"], today.year)
    if opening <= today <= deadline:
        yield Event(
            key=f"open:{today.year}",
            title=_("The %(year)d income tax return is open") % {"year": today.year},
            body=_("Deadline: %(date)s")
            % {"date": date_format(deadline, "DATE_FORMAT")},
            url="https://www.impots.gouv.fr/",
        )
    if 0 <= (deadline - today).days <= params["days_before"]:
        yield Event(
            key=f"deadline:{today.year}",
            title=_("Income tax return due on %(date)s")
            % {"date": date_format(deadline, "DATE_FORMAT")},
            body=when(deadline, today),
            url="https://www.impots.gouv.fr/",
            level="warning",
        )


def _version_tuple(text: str) -> tuple[int, ...]:
    parts = []
    for part in text.strip().lstrip("v").split("."):
        digits = "".join(c for c in part if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def installed_version() -> str:
    try:
        return version("glad")
    except PackageNotFoundError:
        return "0"


def _app_release(params: dict[str, Any], today: datetime.date) -> Iterator[Event]:
    try:
        response = httpx.get(
            RELEASES_URL,
            timeout=10,
            headers={"Accept": "application/vnd.github+json"},
        )
        response.raise_for_status()
        release = response.json()
    except httpx.HTTPError, ValueError:
        logger.warning("Could not read the latest Glad release", exc_info=True)
        return
    tag = str(release.get("tag_name") or "")
    if not tag or _version_tuple(tag) <= _version_tuple(installed_version()):
        return
    yield Event(
        key=tag,
        title=_("Glad %(version)s is available") % {"version": tag.lstrip("v")},
        body=_("Installed version: %(version)s") % {"version": installed_version()},
        url=str(release.get("html_url") or ""),
    )


def _monthly_summary(params: dict[str, Any], today: datetime.date) -> Iterator[Event]:
    if today.day > 7:  # sent at the start of the month, late runs included
        return
    currency = default_currency()
    hero = hero_summary(registry(currency, today), currency, today)
    lines = [
        _("Net worth: %(amount)s")
        % {"amount": format_money_filter(Money(hero.net, currency))}
    ]
    if hero.change_30d_pct is not None:
        lines.append(
            _("Over 30 days: %(amount)s (%(pct)+.1f %%)")
            % {
                "amount": format_money_filter(Money(hero.change_30d, currency)),
                "pct": hero.change_30d_pct,
            }
        )
    if hero.change_12m_pct is not None and hero.change_12m is not None:
        lines.append(
            _("Over 12 months: %(amount)s (%(pct)+.1f %%)")
            % {
                "amount": format_money_filter(Money(hero.change_12m, currency)),
                "pct": hero.change_12m_pct,
            }
        )
    yield Event(
        key=f"{today:%Y-%m}",
        title=_("Net worth summary of %(month)s")
        % {"month": date_format(today, "YEAR_MONTH_FORMAT")},
        body="\n".join(lines),
        url=reverse("index"),
    )


register(
    NotificationType(
        key="stale_data",
        group="finance",
        label=gettext_lazy("Data to update"),
        description=gettext_lazy(
            "The last value of an account or an asset is getting old: time for an update."
        ),
        check=_stale_data,
        params=(
            Param(
                "days",
                gettext_lazy("Accounts and assets (days)"),
                30,
                min_value=1,
                max_value=365,
            ),
            Param(
                "long_days",
                gettext_lazy("Properties (days)"),
                365,
                min_value=1,
                max_value=3650,
            ),
        ),
        renotify_days=30,
    )
)
register(
    NotificationType(
        key="monthly_summary",
        group="finance",
        label=gettext_lazy("Monthly summary"),
        description=gettext_lazy(
            "The net worth and its change, at the start of every month."
        ),
        check=_monthly_summary,
    )
)
register(
    NotificationType(
        key="income_tax_return",
        group="tax",
        label=gettext_lazy("Income tax return"),
        description=gettext_lazy(
            "Opening and deadline of the yearly income tax return."
        ),
        check=_income_tax_return,
        params=(
            Param(
                "opening",
                gettext_lazy("Opening (MM-DD)"),
                "04-10",
                kind="monthday",
            ),
            Param(
                "deadline",
                gettext_lazy("Online deadline (MM-DD)"),
                "05-28",
                kind="monthday",
                help_text=gettext_lazy("It depends on your department number."),
            ),
            days_before_param(14),
        ),
    )
)
register(
    NotificationType(
        key="app_release",
        group="app",
        label=gettext_lazy("New version"),
        description=gettext_lazy("A new version of Glad is published."),
        check=_app_release,
    )
)
register(
    NotificationType(
        key="job_failed",
        group="app",
        label=gettext_lazy("Background job failure"),
        description=gettext_lazy(
            "A background job (index refresh, notification checks…) failed."
        ),
    )
)
register(
    NotificationType(
        key="email_failed",
        group="app",
        label=gettext_lazy("Email failure"),
        description=gettext_lazy("An email sent from the application failed."),
    )
)
