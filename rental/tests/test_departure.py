"""Tests for the departure of a tenant."""

import datetime
from decimal import Decimal

import pytest
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from moneyed import Money

from property.models import Lease, PropertyLedgerEntry
from rental import notifications, rules
from rental.models import DepositSettlement, InventoryItem
from rental.services import departure
from rental.services.inventories import create_entry, create_exit

D = datetime.date
LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


def _lease(lease_type=Lease.LeaseType.EMPTY, tight=False, **kwargs):
    from property.models import Property

    prop = Property(is_tight_zone=tight)
    return Lease(property=prop, lease_type=lease_type, **kwargs)


def test_tenant_notice():
    assert rules.tenant_notice_months(_lease()) == 3
    assert rules.tenant_notice_months(_lease(tight=True)) == 1
    assert rules.tenant_notice_months(_lease(Lease.LeaseType.FURNISHED)) == 1
    assert rules.tenant_notice_months(_lease(Lease.LeaseType.COMMERCIAL)) == 3


def test_term_end():
    lease = _lease(start_date=D(2020, 3, 1))
    assert rules.term_end(lease, D(2026, 10, 1)) == D(2029, 2, 28)
    lease.end_date = D(2027, 1, 1)
    assert rules.term_end(lease, D(2026, 10, 1)) == D(2027, 1, 1)
    assert (
        rules.term_end(
            _lease(Lease.LeaseType.MOBILITY, start_date=D(2026, 1, 1)), D(2026, 2, 1)
        )
        is None
    )


def test_notice_end_and_landlord_deadline():
    lease = _lease(Lease.LeaseType.FURNISHED, start_date=D(2025, 9, 1))
    assert departure.notice_end(lease, D(2026, 3, 15), departure.TENANT) == D(
        2026, 4, 15
    )
    assert departure.notice_end(lease, D(2026, 3, 15), departure.LANDLORD) == D(
        2026, 8, 31
    )
    assert departure.landlord_notice_deadline(lease, D(2026, 3, 15)) == D(2026, 6, 1)
    assert (
        departure.landlord_notice_deadline(
            _lease(Lease.LeaseType.MOBILITY, start_date=D(2026, 1, 1)), D(2026, 2, 1)
        )
        is None
    )


@pytest.mark.django_db
def test_give_notice_and_close(lease, rent_schedule):
    departure.give_notice(lease, D(2026, 9, 10), departure.TENANT)
    lease.refresh_from_db()
    assert (lease.status, lease.end_date, lease.notice_by) == (
        Lease.Status.NOTICE_PERIOD,
        D(2026, 12, 10),
        "tenant",
    )
    assert departure.close_lease(lease, D(2026, 12, 10)) == 2
    lease.refresh_from_db()
    assert lease.status == Lease.Status.ENDED
    rent, _charges = rent_schedule
    rent.refresh_from_db()
    assert rent.recurrence_end_date == D(2026, 12, 10)


@pytest.mark.django_db
def test_compare(lease):
    assert departure.compare(lease) == []
    entry = create_entry(lease, D(2025, 1, 1))
    InventoryItem.objects.filter(room__inventory=entry).update(condition="good")
    exit_inventory = create_exit(lease, D(2026, 1, 1))
    items = InventoryItem.objects.filter(room__inventory=exit_inventory)
    items.update(condition="good")
    first = items.first()
    assert first is not None
    first.condition = "damaged"
    first.comment = "Trou"
    first.save()
    rows = departure.compare(lease)
    worse = [row for row in rows if row.is_worse]
    assert [(row.item, row.entry, row.exit, row.comment) for row in worse] == [
        (first.name, "good", "damaged", "Trou")
    ]
    assert not departure.Comparison("r", "i", "", "damaged", "").is_worse


@pytest.fixture
def settlement(lease):
    return DepositSettlement.objects.create(
        lease=lease,
        keys_returned_date=D(2026, 1, 10),
        deductions=[{"label": "Peinture", "amount": "150.00"}],
        coownership_withholding=Decimal(100),
    )


@pytest.mark.django_db
def test_deposit_amounts(settlement):
    assert departure.return_deadline(settlement) == D(2026, 2, 10)
    assert departure.months_late(settlement, D(2026, 2, 10)) == 0
    assert departure.months_late(settlement, D(2026, 2, 11)) == 1
    assert departure.months_late(settlement, D(2026, 3, 11)) == 2
    assert departure.penalty(settlement, D(2026, 3, 11)) == Decimal("160.00")
    assert departure.deposit_back(settlement) == Decimal(550)
    assert departure.to_pay(settlement, D(2026, 2, 1)) == Decimal(550)
    settlement.exit_matches_entry = False
    assert departure.return_deadline(settlement) == D(2026, 3, 10)
    settlement.deductions = [{"label": "Tout", "amount": "2000"}]
    assert departure.deposit_back(settlement) == 0
    assert str(settlement) == str(settlement.lease)


@pytest.mark.django_db
def test_settle(settlement):
    departure.settle(settlement, D(2026, 2, 20))
    settlement.refresh_from_db()
    assert (settlement.status, settlement.returned_date) == (
        DepositSettlement.Status.RETURNED,
        D(2026, 2, 20),
    )
    entries = {
        e.management_category: e.amount.amount
        for e in PropertyLedgerEntry.objects.filter(lease=settlement.lease)
    }
    assert entries == {
        "deposit_out": Decimal(550),
        "other_income": Decimal(150),
        "non_deductible": Decimal(80),
    }


@pytest.mark.django_db
def test_settle_without_anything(lease):
    lease.deposit_amount = Money(0, "EUR")
    settlement = DepositSettlement.objects.create(
        lease=lease, keys_returned_date=D(2026, 1, 10)
    )
    departure.settle(settlement, D(2026, 1, 20))
    assert not PropertyLedgerEntry.objects.filter(lease=lease).exists()


@pytest.mark.django_db
def test_statement_pdf(settlement):
    assert departure.statement_pdf(settlement, D(2026, 4, 1)).startswith(b"%PDF")
    settlement.coownership_withholding = Decimal(0)
    settlement.exit_matches_entry = False
    assert departure.statement_pdf(settlement, D(2026, 2, 1)).startswith(b"%PDF")


# ── Views ───────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_departure_tab(user_client, lease):
    url = reverse("rental:lease_departure", args=[lease.pk])
    response = user_client.get(url)
    assert response.status_code == 200
    assert response.context["tenant_notice_months"] == 3
    assert response.context["landlord_deadline"] is not None
    assert response.context["settlement"] is None
    create_entry(lease, D(2025, 1, 1))
    create_exit(lease, D(2026, 1, 1))
    response = user_client.get(url)
    assert response.context["compared"]
    assert response.context["worse"] == []


@pytest.mark.django_db
def test_notice_view(user_client, lease):
    url = reverse("rental:give_notice", args=[lease.pk])
    user_client.post(url, {"notice_date": "bad", "notice_by": "tenant"})
    lease.refresh_from_db()
    assert lease.notice_date is None
    user_client.post(url, {"notice_date": "2026-09-01", "notice_by": "tenant"})
    lease.refresh_from_db()
    assert lease.end_date == D(2026, 12, 1)
    response = user_client.get(reverse("rental:lease_departure", args=[lease.pk]))
    assert "Notice given by the tenant on" in response.content.decode()


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_settlement_views(user_client, lease, django_capture_on_commit_callbacks):
    save = reverse("rental:save_settlement", args=[lease.pk])
    user_client.post(
        save, {"keys_returned_date": "2026-01-10", "coownership_withholding": "500"}
    )
    assert not DepositSettlement.objects.exists()
    user_client.post(
        save,
        {
            "keys_returned_date": "2026-01-10",
            "deduction_label": ["X"],
            "deduction_amount": [""],
        },
    )
    assert not DepositSettlement.objects.exists()
    user_client.post(
        save,
        {
            "keys_returned_date": "2026-01-10",
            "exit_matches_entry": "on",
            "deduction_label": ["Peinture", ""],
            "deduction_amount": ["150", ""],
            "coownership_withholding": "100",
        },
    )
    settlement = DepositSettlement.objects.get()
    assert settlement.deductions == [{"label": "Peinture", "amount": "150.00"}]
    response = user_client.get(reverse("rental:lease_departure", args=[lease.pk]))
    assert response.context["to_pay"] > 0
    pdf = user_client.get(reverse("rental:deposit_pdf", args=[lease.pk]))
    assert pdf["Content-Type"] == "application/pdf"
    compose = reverse("rental:compose_email", args=[lease.pk, "deposit_settlement"])
    response = user_client.get(compose)
    body = response.context["form"].initial["body"]
    assert "- Retenue : Peinture (150,00 €)" in body
    assert "copropriété : 100,00 €" in body
    assert response.context["attachment"] == "restitution-depot-de-garantie.pdf"
    with django_capture_on_commit_callbacks(execute=True):
        user_client.post(
            compose, {"to": "jean@example.com", "subject": "Dépôt", "body": "Bonjour"}
        )
    assert mail.outbox[0].attachments[0].filename == "restitution-depot-de-garantie.pdf"
    settlement.refresh_from_db()
    assert settlement.sent_at is not None
    user_client.post(
        reverse("rental:return_deposit", args=[lease.pk]),
        {"returned_date": "2026-02-01"},
    )
    settlement.refresh_from_db()
    assert settlement.status == DepositSettlement.Status.RETURNED
    # Once returned, it is no longer edited.
    user_client.post(save, {"keys_returned_date": "2026-03-01"})
    settlement.refresh_from_db()
    assert settlement.keys_returned_date == D(2026, 1, 10)
    response = user_client.get(reverse("rental:lease_emails", args=[lease.pk]))
    assert "deposit_settlement" not in [k.key for k in response.context["kinds"]]


@pytest.mark.django_db
def test_close_view(user_client, lease):
    url = reverse("rental:close_lease", args=[lease.pk])
    user_client.post(url, {"end_date": "1999-01-01"})
    lease.refresh_from_db()
    assert lease.status == Lease.Status.ACTIVE
    response = user_client.post(url, {"end_date": "2026-12-31"})
    assert response.url == reverse("rental:lease_detail", args=[lease.pk])
    lease.refresh_from_db()
    assert (lease.status, lease.end_date) == (Lease.Status.ENDED, D(2026, 12, 31))


# ── Notifications and deadlines ─────────────────────────────────────────────


@pytest.mark.django_db
def test_deposit_return_due(settlement):
    params = {"days_before": 7}
    assert list(notifications._deposit_due(params, D(2026, 1, 20))) == []
    (event,) = notifications._deposit_due(params, D(2026, 2, 5))
    assert event.title == "Return the deposit: Rue des Lilas — Jean Dupont"


@pytest.mark.django_db
def test_exit_inventory_due(lease):
    params = {"days_before": 15}
    departure.give_notice(lease, datetime.date.today(), departure.TENANT)
    assert list(notifications._exit_inventory_due(params, datetime.date.today())) == []
    soon = lease.end_date - datetime.timedelta(days=10)
    (event,) = notifications._exit_inventory_due(params, soon)
    assert event.url == reverse("rental:lease_departure", args=[lease.pk])
    create_exit(lease, soon)
    assert list(notifications._exit_inventory_due(params, soon)) == []


@pytest.mark.django_db
def test_landlord_notice_deadline_in_the_deadlines(lease):
    from base.services.deadlines import deadlines_of

    (deadline,) = deadlines_of({"landlord_notice"}, datetime.date.today())
    assert deadline.detail == "Last day to give notice as the landlord"
    assert deadline.url == reverse("rental:lease_detail", args=[lease.pk])


@pytest.mark.django_db
def test_no_landlord_deadlines_under_a_mandate(lease):
    from base.services.deadlines import deadlines_of
    from property.models import ManagementMandate

    kinds = {"landlord_notice", "rent_revision"}
    assert {d.kind for d in deadlines_of(kinds, datetime.date.today())} == kinds
    ManagementMandate.objects.create(
        property=lease.property,
        manager_name="Foncia",
        start_date=datetime.date(2020, 1, 1),
    )
    assert deadlines_of(kinds, datetime.date.today()) == []
