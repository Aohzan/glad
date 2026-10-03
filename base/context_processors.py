"""Context processors for the application shell (sidebar and header)."""

import datetime

from django.core.cache import cache
from django.utils.translation import gettext_lazy as _

from base.services.deadlines import SOON_DAYS, upcoming_deadlines

#: Seconds the count of upcoming deadlines shown in the sidebar is cached.
DEADLINES_CACHE_SECONDS = 600

#: Sidebar section of each ``namespace:url_name`` (or url-name prefix).
_SECTION_PREFIXES: tuple[tuple[str, str], ...] = (
    ("finance:other_asset", "other_assets"),
    ("finance:new_other_asset", "other_assets"),
    ("finance:edit_other_asset", "other_assets"),
    ("finance:delete_other_asset", "other_assets"),
    ("finance:update_other_asset", "other_assets"),
    ("finance:csv_", "csv"),
    ("finance:", "finance"),
    ("property:scpi_", "scpi"),
    ("property:all_loans", "loans"),
    ("property:checks", "checks"),
    ("property:report", "report"),
    ("property:lmnp_", "lmnp"),
    ("property:", "property"),
    ("accounts:", "account"),
    ("admin:", "admin"),
    ("allocation", "allocation"),
    ("owners", "owners"),
    ("manage_owners", "owners"),
    ("deadlines", "deadlines"),
    ("operations", "operations"),
    ("index", "dashboard"),
)

#: Breadcrumb label of each sidebar section.
SECTION_LABELS = {
    "dashboard": _("Dashboard"),
    "finance": _("Finance"),
    "other_assets": _("Other assets"),
    "csv": _("CSV import / export"),
    "property": _("Properties"),
    "scpi": _("SCPI"),
    "loans": _("All Loans"),
    "checks": _("Entries to check"),
    "report": _("Income & Expenses Report"),
    "lmnp": _("LMNP Accounting"),
    "account": _("Settings"),
    "admin": _("Administration"),
    "allocation": _("Allocation"),
    "owners": _("Net worth by owner"),
    "deadlines": _("Deadlines"),
    "operations": _("Operations"),
}


#: Sidebar group holding each section; only the current one starts unfolded.
SECTION_GROUPS = {
    "dashboard": "wealth",
    "finance": "wealth",
    "property": "wealth",
    "scpi": "wealth",
    "other_assets": "wealth",
    "allocation": "analysis",
    "owners": "analysis",
    "report": "analysis",
    "deadlines": "tracking",
    "operations": "tracking",
    "checks": "tracking",
    "loans": "tracking",
    "lmnp": "tools",
    "csv": "tools",
    "admin": "tools",
}


def _nav_section(request) -> str:
    match = getattr(request, "resolver_match", None)
    if match is None:
        return ""
    name = f"{match.namespace}:{match.url_name}" if match.namespace else match.url_name
    for prefix, section in _SECTION_PREFIXES:
        if name and name.startswith(prefix):
            return section
    return ""


def _initials(user) -> str:
    full = f"{user.first_name} {user.last_name}".split()
    letters = "".join(part[0] for part in full[:2]) if full else user.username[:2]
    return letters.upper()


def deadlines_soon_count(today: datetime.date | None = None) -> int:
    """Number of deadlines due within SOON_DAYS, cached for a few minutes."""
    today = today or datetime.date.today()
    key = f"glad:deadlines-soon:{today.isoformat()}"
    count = cache.get(key)
    if count is None:
        count = sum(
            1 for d in upcoming_deadlines(today) if 0 <= d.days_left <= SOON_DAYS
        )
        cache.set(key, count, DEADLINES_CACHE_SECONDS)
    return count


def shell(request):
    """Expose the active sidebar section and group, the deadline badge and initials."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"nav_section": ""}
    section = _nav_section(request)
    return {
        "nav_section": section,
        "nav_group": SECTION_GROUPS.get(section, ""),
        "nav_section_label": SECTION_LABELS.get(section, ""),
        "deadlines_soon_count": deadlines_soon_count(),
        "user_initials": _initials(user),
    }
