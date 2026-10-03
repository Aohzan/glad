"""Tests for the application shell: navigation, search, icons and operations."""

import datetime
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.core.cache import cache
from django.template import Context, Template
from django.test import RequestFactory
from django.urls import reverse
from moneyed import Money

from base.context_processors import _initials, _nav_section, deadlines_soon_count, shell
from base.services.operations import (
    OPERATION_KINDS,
    operations_queryset,
    recent_operations,
    resolve,
)
from finance.models.other_asset import OtherAsset
from finance.models.saving_account import SavingAccount, SavingAccountValue
from property.models.scpi import SCPI, SCPIDividend

TODAY = datetime.date.today()


# ── Context processor ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("namespace", "url_name", "section"),
    [
        ("", "index", "dashboard"),
        ("finance", "investment_detail", "finance"),
        ("finance", "other_asset_list", "other_assets"),
        ("finance", "csv_import", "csv"),
        ("property", "scpi_list", "scpi"),
        ("property", "all_loans", "loans"),
        ("property", "detail", "property"),
        ("", "deadlines", "deadlines"),
        ("", "manage_owners", "owners"),
        ("admin", "index", "admin"),
        ("", "unknown", ""),
    ],
)
def test_nav_section(namespace, url_name, section):
    request = SimpleNamespace(
        resolver_match=SimpleNamespace(namespace=namespace, url_name=url_name)
    )
    assert _nav_section(request) == section


def test_nav_section_without_match():
    assert _nav_section(SimpleNamespace(resolver_match=None)) == ""


def test_initials():
    assert _initials(User(username="jdoe", first_name="Jane", last_name="Doe")) == "JD"
    assert _initials(User(username="mister")) == "MI"


@pytest.mark.django_db
def test_shell_anonymous():
    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    assert shell(request) == {"nav_section": ""}


@pytest.mark.django_db
def test_shell_authenticated(admin_user):
    cache.clear()
    request = RequestFactory().get("/")
    request.user = admin_user
    request.resolver_match = SimpleNamespace(  # ty: ignore[invalid-assignment]
        namespace="", url_name="operations"
    )
    context = shell(request)
    assert context["nav_section"] == "operations"
    assert context["nav_group"] == "tracking"
    assert str(context["nav_section_label"]) == "Operations"
    assert context["user_initials"] == "AD"
    assert isinstance(context["deadlines_soon_count"], int)


@pytest.mark.django_db
def test_deadlines_count_is_cached():
    cache.clear()
    first = deadlines_soon_count(TODAY)
    cache.set(f"glad:deadlines-soon:{TODAY.isoformat()}", first + 5)
    assert deadlines_soon_count(TODAY) == first + 5


@pytest.mark.django_db
def test_sidebar_marks_the_active_section(admin_client):
    content = admin_client.get(reverse("operations")).content.decode()
    assert 'aria-current="page"' in content
    assert reverse("api_search") in content


@pytest.mark.django_db
def test_sidebar_unfolds_only_the_current_group(admin_client):
    content = admin_client.get(reverse("operations")).content.decode()
    assert re.search(r'aria-controls="g-nav-tracking" aria-expanded="true"', content)
    assert re.search(r'aria-controls="g-nav-wealth" aria-expanded="false"', content)
    assert 'id="g-nav-tracking">' in content
    assert 'id="g-nav-wealth" data-folded>' in content


@pytest.mark.django_db
def test_sidebar_folds_every_group_outside_the_menu(admin_client):
    content = admin_client.get(reverse("accounts:settings")).content.decode()
    assert 'aria-expanded="true"' not in content.split('class="g-sidebar__foot"')[0]


@pytest.mark.django_db
def test_anonymous_layout(client):
    content = client.get(reverse("login")).content.decode()
    assert "g-auth" in content
    assert "g-sidebar" not in content


# ── Search ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_search_index(admin_client, saving_account_type):
    SavingAccount.objects.create(
        name="Search me",
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
        institution="Bank",
    )
    SCPI.objects.create(name="Search SCPI")
    OtherAsset.objects.create(
        name="Search car",
        category=OtherAsset.Category.VEHICLE,
        acquisition_date=TODAY,
        acquisition_value=Money(1000, "EUR"),
    )
    response = admin_client.get(reverse("api_search"))
    assert response.status_code == 200
    items = response.json()["items"]
    kinds = {item["kind"] for item in items}
    assert {"account", "scpi", "other", "page"} <= kinds
    labels = {item["label"] for item in items}
    assert "Search SCPI" in labels and "Search car" in labels
    assert all(item["url"].startswith("/") for item in items)


@pytest.mark.django_db
def test_search_requires_login(client):
    response = client.get(reverse("api_search"))
    assert response.status_code == 302


# ── Icons ──────────────────────────────────────────────────────────────────


def test_icon_tag_decorative():
    html = Template('{% icon "house" "me-2" %}').render(Context())
    assert 'class="g-icon me-2"' in html
    assert 'aria-hidden="true"' in html
    assert "sprite.svg#house" in html


def test_icon_tag_labelled_and_sized():
    html = Template('{% icon "info" label="Help" size=20 %}').render(Context())
    assert 'role="img" aria-label="Help"' in html
    assert 'width="20" height="20"' in html


SPRITE = Path(settings.BASE_DIR) / "static" / "vendors" / "lucide" / "sprite.svg"


@pytest.mark.skipif(not SPRITE.exists(), reason="run npm ci to vendor the sprite")
def test_every_icon_exists_in_the_sprite():
    symbols = set(re.findall(r'<symbol id="([^"]+)"', SPRITE.read_text()))
    root = Path(settings.BASE_DIR)
    used = set()
    for path in (root / "templates").rglob("*.html"):
        text = path.read_text()
        used |= set(re.findall(r'{%\s*icon\s+"([a-z0-9-]+)"', text))
        used |= set(re.findall(r"gIcon\('([a-z0-9-]+)'", text))
        used |= set(
            re.findall(
                r'(?:icon|title_icon|submit_icon|header_icon|account_icon)="([a-z0-9-]+)"',
                text,
            )
        )
    for path in (root / "static" / "js").glob("*.js"):
        used |= set(re.findall(r"gIcon\('([a-z0-9-]+)'", path.read_text()))
    for app in ("base", "finance", "property"):
        for path in (root / app).rglob("*.py"):
            if "tests" in path.parts or "migrations" in path.parts:
                continue
            used |= set(re.findall(r'"icon": "([a-z0-9-]+)"', path.read_text()))
    used |= {spec.icon for spec in OPERATION_KINDS.values()}
    used |= set(OtherAsset.CATEGORY_ICONS.values())
    missing = sorted(used - symbols)
    assert not missing, f"Unknown Lucide icons: {missing}"


# ── Operations ─────────────────────────────────────────────────────────────


@pytest.fixture
def operations(saving_account_type):
    account = SavingAccount.objects.create(
        name="Ops account",
        account_type=saving_account_type,
        opening_value=Money(0, "EUR"),
    )
    SavingAccountValue.objects.create(
        account=account,
        value=Money(1500, "EUR"),
        value_date=datetime.datetime.combine(TODAY, datetime.time(10)),
    )
    scpi = SCPI.objects.create(name="Ops SCPI")
    SCPIDividend.objects.create(
        scpi=scpi,
        payment_date=TODAY + datetime.timedelta(days=1),
        gross_amount=Money(40, "EUR"),
        net_amount=Money(30, "EUR"),
    )
    return account, scpi


@pytest.mark.django_db
def test_operations_union_is_ordered(operations):
    account, _scpi = operations
    rows = list(operations_queryset()[:2])
    resolved = resolve(rows)
    assert resolved[0].kind == "scpi_dividend"
    assert resolved[0].target == "Ops SCPI"
    assert resolved[0].flow == "in"
    assert resolved[0].icon == "coins"
    assert str(resolved[0].label) == "Dividend"
    assert resolved[1].kind == "saving_value"
    assert resolved[1].amount == Money(1500, "EUR")
    assert resolved[1].url == reverse(
        "finance:saving_detail", kwargs={"pk": account.pk}
    )
    assert recent_operations(1)[0].kind == "scpi_dividend"


@pytest.mark.django_db
def test_operations_filter_kinds(operations):
    rows = list(operations_queryset(["saving_value"]))
    assert {row["g_kind"] for row in rows} == {"saving_value"}
    every = operations_queryset(["unknown"]).count()
    assert every == operations_queryset().count()


@pytest.mark.django_db
def test_operations_page(admin_client, operations):
    response = admin_client.get(reverse("operations"))
    assert response.status_code == 200
    assert response.context["page"].number == 1
    assert "Ops SCPI" in response.content.decode()
    filtered = admin_client.get(reverse("operations") + "?kind=dividends&page=1")
    assert {op.kind for op in filtered.context["operations"]} == {"scpi_dividend"}
    unknown = admin_client.get(reverse("operations") + "?kind=nope")
    assert unknown.context["kind"] == ""


# ── Patrimony chart ────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("value", "months"), [("1", 13), ("5", 61), ("x", 25), ("3", 25)]
)
def test_patrimony_chart_range(admin_client, value, months):
    data = admin_client.get(reverse("api_patrimony_chart") + f"?range={value}").json()
    assert len(data["dates"]) == months
    assert len(data["net"]) == len(data["gross"]) == len(data["debt"]) == months
    assert all(
        g == pytest.approx(n + d)
        for n, g, d in zip(data["net"], data["gross"], data["debt"], strict=True)
    )
