"""Notification types about the accounts (see ``notifications.registry``)."""

import datetime
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext

from base.services.dashboard import default_currency, registry
from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountHolding,
    QuoteSnapshot,
)
from finance.models.saving_account import SavingAccount
from notifications.checks import days_before_param, deadline_check
from notifications.registry import Event, NotificationType, Param, register


def _account_drops(params: dict[str, Any], today: datetime.date) -> Iterator[Event]:
    threshold = -Decimal(params["threshold"])
    for group in registry(default_currency(), today):
        for row in group.rows:
            if row.change_pct is None or row.change_pct > threshold:
                continue
            if row.old_value <= 0:  # a negative net value (loan) has no drop rate
                continue
            yield Event(
                key=row.url,
                title=_("%(asset)s dropped %(pct).1f %% in 30 days")
                % {"asset": row.name, "pct": -row.change_pct},
                url=row.url,
                level="warning",
            )


def _security_drops(params: dict[str, Any], today: datetime.date) -> Iterator[Event]:
    """Securities whose last close lost the threshold over the window.

    The window counts calendar days back from the last close; one day compares
    with the previous trading day.
    """
    window = int(params["window"])
    threshold = Decimal(params["threshold"])
    holdings: dict[str, InvestmentAccountHolding] = {}
    for holding in (
        InvestmentAccountHolding.objects.filter(is_active=True, account__is_active=True)
        .exclude(isin__isnull=True)
        .exclude(isin="")
        .select_related("account")
    ):
        holdings.setdefault(str(holding.isin), holding)
    closes: dict[str, list[QuoteSnapshot]] = {}
    for snapshot in QuoteSnapshot.objects.filter(isin__in=holdings).order_by(
        "isin", "-date"
    ):
        closes.setdefault(snapshot.isin, []).append(snapshot)
    for isin, snapshots in closes.items():
        latest = snapshots[0]
        if (today - latest.date).days > 7:  # no recent close: nothing to compare
            continue
        if window == 1:
            reference = snapshots[1] if len(snapshots) > 1 else None
        else:
            limit = latest.date - datetime.timedelta(days=window)
            reference = next((s for s in snapshots if s.date <= limit), None)
        if reference is None or not reference.close:
            continue
        change = (latest.close - reference.close) / reference.close * 100
        if change > -threshold:
            continue
        holding = holdings[isin]
        yield Event(
            key=f"{isin}:{latest.date.isoformat()}:{window}",
            title=ngettext(
                "%(security)s dropped %(pct).1f %% in %(days)d day",
                "%(security)s dropped %(pct).1f %% in %(days)d days",
                window,
            )
            % {"security": holding.short_name, "pct": -change, "days": window},
            body=_("Close of %(date)s: %(close)s %(currency)s")
            % {
                "date": latest.date.isoformat(),
                "close": f"{latest.close:.2f}",
                "currency": latest.currency,
            },
            url=reverse(
                "finance:holding_detail",
                kwargs={"account_pk": holding.account_id, "holding_pk": holding.pk},
            ),
            level="warning",
        )


def _ceilings(params: dict[str, Any], today: datetime.date) -> Iterator[Event]:
    for model, url_name in (
        (SavingAccount, "finance:saving_detail"),
        (InvestmentAccount, "finance:investment_detail"),
    ):
        for account in model.objects.active().select_related("account_type"):
            usage = account.ceiling_usage
            if usage is None or usage.percent < params["percent"]:
                continue
            yield Event(
                key=f"{model.__name__}:{account.pk}",
                title=(
                    _("%(account)s reached its deposit ceiling")
                    if usage.is_reached
                    else _("%(account)s is at %(pct).0f %% of its deposit ceiling")
                )
                % {"account": account, "pct": usage.percent},
                url=reverse(url_name, kwargs={"pk": account.pk}),
            )


register(
    NotificationType(
        key="security_drop",
        group="finance",
        label=gettext_lazy("Security drop"),
        description=gettext_lazy(
            "A held security (with an ISIN) lost more than the threshold, from the "
            "daily market closes, whether its value is updated automatically or by hand."
        ),
        check=_security_drops,
        params=(
            Param(
                "threshold",
                gettext_lazy("Drop threshold (%)"),
                5,
                min_value=1,
                max_value=100,
            ),
            Param(
                "window",
                gettext_lazy("Over"),
                1,
                kind="choice",
                choices=(
                    (1, gettext_lazy("1 day")),
                    (7, gettext_lazy("7 days")),
                    (30, gettext_lazy("30 days")),
                ),
            ),
        ),
    )
)
register(
    NotificationType(
        key="account_drop",
        group="finance",
        label=gettext_lazy("Asset drop"),
        description=gettext_lazy(
            "An account or asset lost more than the threshold over 30 days."
        ),
        check=_account_drops,
        params=(
            Param(
                "threshold",
                gettext_lazy("Drop threshold (%)"),
                5,
                min_value=1,
                max_value=100,
            ),
        ),
        renotify_days=30,
    )
)
register(
    NotificationType(
        key="savings_ceiling",
        group="finance",
        label=gettext_lazy("Deposit ceiling"),
        description=gettext_lazy(
            "A regulated savings book or a PEA nears its deposit ceiling."
        ),
        check=_ceilings,
        params=(
            Param(
                "percent",
                gettext_lazy("Usage of the ceiling (%)"),
                95,
                min_value=1,
                max_value=100,
            ),
        ),
        renotify_days=90,
    )
)
register(
    NotificationType(
        key="envelope_milestone",
        group="finance",
        label=gettext_lazy("Envelope milestones"),
        description=gettext_lazy(
            "Tax milestones of the accounts: PEA 5 years, life insurance 8 years, PEL…"
        ),
        check=deadline_check("milestone"),
        params=(days_before_param(30),),
    )
)
