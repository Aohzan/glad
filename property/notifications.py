"""Notification types about the properties and their taxes."""

import datetime
from collections.abc import Iterator
from typing import Any

from django.urls import reverse
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext

from notifications.checks import (
    days_before_param,
    deadline_check,
    month_day,
    when,
)
from notifications.registry import Event, NotificationType, Param, register
from property.models import LmnpDeclarationSnapshot, Property
from property.services.checks import pending_occurrences
from property.services.tax_lmnp import get_lmnp_checklist


def _pending_checks(params: dict[str, Any], today: datetime.date) -> Iterator[Event]:
    overdue = [
        p
        for p in pending_occurrences(up_to=today)
        if (today - p.planned_date).days > params["days"]
    ]
    if not overdue:
        return
    oldest = (today - overdue[0].planned_date).days
    yield Event(
        key="pending",
        title=ngettext(
            "%(count)d recurring entry to check",
            "%(count)d recurring entries to check",
            len(overdue),
        )
        % {"count": len(overdue)},
        body=_("The oldest one is %(days)d days old.") % {"days": oldest},
        url=reverse("property:checks"),
        level="warning",
    )


def _lmnp_properties(year: int) -> list[Property]:
    return [
        prop
        for prop in Property.objects.filter(
            tax_regime=Property.TaxRegime.LMNP_REEL, is_active=True
        )
        if prop.amortization_start_date.year <= year
    ]


def _lmnp_return(params: dict[str, Any], today: datetime.date) -> Iterator[Event]:
    deadline = month_day(params["deadline"], today.year)
    if not 0 <= (deadline - today).days <= params["days_before"]:
        return
    fiscal_year = today.year - 1
    properties = _lmnp_properties(fiscal_year)
    if not properties:
        return
    lines = [when(deadline, today)]
    issues = get_lmnp_checklist(properties, fiscal_year)["total_issues"]
    if issues:
        lines.append(
            ngettext(
                "The checklist reports %(count)d issue.",
                "The checklist reports %(count)d issues.",
                issues,
            )
            % {"count": issues}
        )
    if not LmnpDeclarationSnapshot.objects.filter(fiscal_year=fiscal_year).exists():
        lines.append(
            _("The declaration of %(year)d is not frozen yet.") % {"year": fiscal_year}
        )
    yield Event(
        key=str(fiscal_year),
        title=_("LMNP tax return for %(year)d due on %(date)s")
        % {"year": fiscal_year, "date": date_format(deadline, "DATE_FORMAT")},
        body="\n".join(lines),
        url=f"{reverse('property:lmnp_accounting')}?year={fiscal_year}",
        level="warning",
    )


def _local_taxes(params: dict[str, Any], today: datetime.date) -> Iterator[Event]:
    taxes = []
    if Property.objects.filter(is_active=True).exists():
        taxes.append(
            ("property_tax", _("Property tax (taxe foncière)"), params["property_tax"])
        )
    if Property.objects.filter(
        is_active=True, tax_regime=Property.TaxRegime.LMNP_REEL
    ).exists():
        taxes.append(("cfe", _("Business property tax (CFE)"), params["cfe"]))
    for key, label, setting in taxes:
        due = month_day(setting, today.year)
        if 0 <= (due - today).days <= params["days_before"]:
            yield Event(
                key=f"{key}:{today.year}",
                title=_("%(tax)s to pay") % {"tax": label},
                body=when(due, today),
                url="https://www.impots.gouv.fr/",
            )


register(
    NotificationType(
        key="ledger_checks_pending",
        group="property",
        label=gettext_lazy("Entries to check"),
        description=gettext_lazy(
            "Recurring entries (rents, charges, loans…) not checked on the bank account."
        ),
        check=_pending_checks,
        params=(
            Param(
                "days",
                gettext_lazy("Late by more than (days)"),
                7,
                min_value=0,
                max_value=365,
            ),
        ),
        renotify_days=7,
    )
)
register(
    NotificationType(
        key="rent_revision_due",
        group="property",
        label=gettext_lazy("Rent revision"),
        description=gettext_lazy("The yearly IRL revision of a lease is due."),
        # A revision not applied can still be claimed for a year.
        check=deadline_check("rent_revision", late_days=365),
        params=(days_before_param(30),),
    )
)
register(
    NotificationType(
        key="lease_term",
        group="property",
        label=gettext_lazy("End of a lease"),
        description=gettext_lazy(
            "A lease reaches its end date, or the last day for the landlord to "
            "give notice before the end of its term."
        ),
        check=deadline_check("lease_end", "landlord_notice"),
        params=(days_before_param(90),),
    )
)
register(
    NotificationType(
        key="dpe",
        group="property",
        label=gettext_lazy("DPE"),
        description=gettext_lazy(
            "The energy diagnosis of a property expires, or its rating will forbid renting it."
        ),
        check=deadline_check("dpe_ban", "dpe_expiry"),
        params=(days_before_param(180),),
    )
)
register(
    NotificationType(
        key="loan_end",
        group="property",
        label=gettext_lazy("End of a loan"),
        description=gettext_lazy("A property loan is about to be fully repaid."),
        check=deadline_check("loan_end"),
        params=(days_before_param(60),),
    )
)
register(
    NotificationType(
        key="scpi_deadline",
        group="property",
        label=gettext_lazy("SCPI dismemberment"),
        description=gettext_lazy("The temporary dismemberment of SCPI shares ends."),
        check=deadline_check("scpi_dismemberment"),
        params=(days_before_param(90),),
    )
)
register(
    NotificationType(
        key="lmnp_return",
        group="tax",
        label=gettext_lazy("LMNP tax return"),
        description=gettext_lazy(
            "The LMNP tax return (2031 and 2033) is due, with the state of the checklist."
        ),
        check=_lmnp_return,
        params=(
            Param(
                "deadline",
                gettext_lazy("Deadline (MM-DD)"),
                "05-20",
                kind="monthday",
                help_text=gettext_lazy(
                    "Usually the second working day after 1 May, plus 15 days online."
                ),
            ),
            days_before_param(30),
        ),
    )
)
register(
    NotificationType(
        key="local_taxes",
        group="tax",
        label=gettext_lazy("Local taxes"),
        description=gettext_lazy(
            "Payment of the property tax and of the CFE of furnished rentals."
        ),
        check=_local_taxes,
        params=(
            Param(
                "property_tax",
                gettext_lazy("Property tax deadline (MM-DD)"),
                "10-15",
                kind="monthday",
            ),
            Param(
                "cfe", gettext_lazy("CFE deadline (MM-DD)"), "12-15", kind="monthday"
            ),
            days_before_param(15),
        ),
    )
)
