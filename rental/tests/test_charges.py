"""Tests for the yearly charges reconciliation."""

import datetime
from decimal import Decimal

import pytest
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from moneyed import Money

from base.models import Document
from property.models import Lease, PropertyLedgerEntry
from property.services.checks import check_occurrence
from rental import notifications
from rental.models import ChargesReconciliation
from rental.services import charges

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
D = datetime.date


@pytest.fixture
def year_lease(lease):
    """Monthly provisions of 50 € over 2025, 10 of them checked."""
    lease.start_date = D(2025, 1, 1)
    lease.save()
    provisions = PropertyLedgerEntry.objects.create(
        property=lease.property,
        lease=lease,
        flow_type=PropertyLedgerEntry.FlowType.INCOME,
        management_category="charges_collected",
        amount=Money(50, "EUR"),
        entry_date=D(2025, 1, 5),
        recurrence_type=PropertyLedgerEntry.RecurrenceType.MONTHLY,
    )
    for month in range(1, 11):
        check_occurrence(provisions, D(2025, month, 5))
    for amount, day, label in ((300, D(2025, 3, 1), "Eau"), (420, D(2025, 9, 1), "")):
        PropertyLedgerEntry.objects.create(
            property=lease.property,
            flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
            management_category="maintenance",
            amount=Money(amount, "EUR"),
            entry_date=day,
            description=label,
            is_recoverable=True,
        )
    PropertyLedgerEntry.objects.create(  # not recoverable
        property=lease.property,
        flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
        management_category="insurance",
        amount=Money(200, "EUR"),
        entry_date=D(2025, 4, 1),
    )
    return lease, provisions


def test_default_period():
    lease = Lease(start_date=D(2020, 5, 1))
    assert charges.default_period(lease, D(2026, 3, 10)) == (
        D(2025, 1, 1),
        D(2025, 12, 31),
    )
    lease.start_date = D(2025, 7, 1)
    lease.end_date = D(2025, 11, 30)
    assert charges.default_period(lease, D(2026, 3, 10)) == (
        D(2025, 7, 1),
        D(2025, 11, 30),
    )
    lease = Lease(start_date=D(2026, 2, 1))
    assert charges.default_period(lease, D(2026, 3, 10)) == (
        D(2026, 2, 1),
        D(2026, 3, 10),
    )


def test_occupancy_ratio():
    lease = Lease(start_date=D(2025, 7, 1))
    ratio = charges.occupancy_ratio(lease, D(2025, 1, 1), D(2025, 12, 31))
    assert ratio == Decimal(184) / Decimal(365)


@pytest.mark.django_db
def test_compute(year_lease):
    lease, _provisions = year_lease
    reconciliation = charges.create(lease, D(2025, 1, 1), D(2025, 12, 31))
    assert reconciliation.provisions == Decimal(500)
    assert [line["label"] for line in reconciliation.expenses] == [
        "Eau",
        "Routine maintenance",
    ]
    assert reconciliation.actual == Decimal(720)
    assert reconciliation.balance == Decimal(220)
    assert str(reconciliation).startswith("2025-01-01 → 2025-12-31")
    assert charges.suggested_provision(reconciliation) == Decimal(60)


@pytest.mark.django_db
def test_prorata_and_adjustments(year_lease):
    lease, _provisions = year_lease
    lease.start_date = D(2025, 7, 1)
    reconciliation = charges.create(lease, D(2025, 1, 1), D(2025, 12, 31))
    assert reconciliation.expenses[0]["share"] == "151.23"  # 300 × 184 / 365
    reconciliation.adjustments = [{"label": "TEOM", "amount": "-12.50"}]
    assert reconciliation.actual == Decimal("151.23") + Decimal("211.73") - Decimal(
        "12.50"
    )


@pytest.mark.django_db
def test_record_balance(year_lease):
    lease, _provisions = year_lease
    reconciliation = charges.create(lease, D(2025, 1, 1), D(2025, 12, 31))
    entry = charges.record_balance(reconciliation)
    assert entry is not None
    assert (entry.flow_type, entry.management_category, entry.amount.amount) == (
        "income",
        "charges_collected",
        Decimal(220),
    )
    assert charges.record_balance(reconciliation) is None
    # The balance paid is not a provision of the next reconciliation.
    assert charges.create(lease, D(2025, 1, 1), D(2026, 12, 31)).provisions == Decimal(
        500
    )
    refund = charges.create(lease, D(2025, 1, 1), D(2025, 12, 31))
    refund.adjustments = [{"label": "Avoir", "amount": "-400"}]
    entry = charges.record_balance(refund)
    assert entry is not None
    assert (entry.flow_type, entry.management_category, entry.amount.amount) == (
        "expense",
        "misc_deductible",
        Decimal(180),
    )
    even = charges.create(lease, D(2025, 1, 1), D(2025, 12, 31))
    even.adjustments = [{"label": "x", "amount": "-220"}]
    assert charges.record_balance(even) is None


@pytest.mark.django_db
def test_update_provision(year_lease):
    lease, provisions = year_lease
    assert charges.update_provision(lease, Decimal(60), D(2026, 1, 1)) == 1
    lease.refresh_from_db()
    assert lease.charges_amount == Money(60, "EUR")
    provisions.refresh_from_db()
    assert provisions.recurrence_end_date == D(2026, 1, 4)
    new = PropertyLedgerEntry.objects.get(entry_date=D(2026, 1, 5))
    assert new.amount == Money(60, "EUR")


@pytest.mark.django_db
def test_suggested_provision_without_days(lease):
    reconciliation = ChargesReconciliation(
        lease=lease, period_start=D(2000, 1, 1), period_end=D(2000, 12, 31)
    )
    assert charges.suggested_provision(reconciliation) is None


@pytest.mark.django_db
def test_statement_pdf(year_lease):
    lease, _provisions = year_lease
    lease.start_date = D(2025, 7, 1)
    reconciliation = charges.create(lease, D(2025, 1, 1), D(2025, 12, 31))
    reconciliation.adjustments = [{"label": "TEOM", "amount": "80"}]
    assert charges.statement_pdf(reconciliation).startswith(b"%PDF")


# ── Views ───────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_charges_tab_and_create(user_client, year_lease):
    lease, _provisions = year_lease
    tab = reverse("rental:lease_charges", args=[lease.pk])
    response = user_client.get(tab)
    assert response.context["is_provision"]
    url = reverse("rental:create_reconciliation", args=[lease.pk])
    assert (
        user_client.post(
            url, {"period_start": "2025-12-31", "period_end": "2025-01-01"}
        ).url
        == tab
    )
    response = user_client.post(
        url, {"period_start": "2025-01-01", "period_end": "2025-12-31"}
    )
    reconciliation = ChargesReconciliation.objects.get()
    assert response.url == reverse(
        "rental:reconciliation_detail", args=[reconciliation.pk]
    )
    assert reconciliation in user_client.get(tab).context["reconciliations"]


@pytest.mark.django_db
def test_detail_adjustments_and_actions(user_client, year_lease):
    lease, _provisions = year_lease
    reconciliation = charges.create(lease, D(2025, 1, 1), D(2025, 12, 31))
    url = reverse("rental:reconciliation_detail", args=[reconciliation.pk])
    response = user_client.get(url)
    assert response.context["suggested"] == Decimal(60)
    assert response.context["balance_abs"] == Decimal(220)
    response = user_client.post(
        url,
        {
            "adjustment_label": ["TEOM", "", "Sans montant"],
            "adjustment_amount": ["80", "", "x"],
        },
    )
    assert response.status_code == 200
    response = user_client.post(
        url,
        {
            "adjustment_label": ["TEOM", ""],
            "adjustment_amount": ["80,5", ""],
            "action": "refresh",
        },
    )
    assert response.status_code == 302
    reconciliation.refresh_from_db()
    assert reconciliation.adjustments == [{"label": "TEOM", "amount": "80.50"}]
    pdf = user_client.get(reverse("rental:charges_pdf", args=[reconciliation.pk]))
    assert 'filename="regularisation-charges-2025.pdf"' in pdf["Content-Disposition"]
    user_client.post(reverse("rental:record_reconciliation", args=[reconciliation.pk]))
    reconciliation.refresh_from_db()
    assert reconciliation.ledger_entry is not None
    provision = reverse("rental:update_provision", args=[reconciliation.pk])
    user_client.post(provision, {"amount": "nope", "effective_date": "2026-01-01"})
    lease.refresh_from_db()
    assert lease.charges_amount == Money(50, "EUR")
    user_client.post(provision, {"amount": "65", "effective_date": "2026-01-01"})
    lease.refresh_from_db()
    assert lease.charges_amount == Money(65, "EUR")


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_send_and_delete(user_client, year_lease, django_capture_on_commit_callbacks):
    lease, _provisions = year_lease
    reconciliation = charges.create(lease, D(2025, 1, 1), D(2025, 12, 31))
    url = reverse("rental:compose_email", args=[lease.pk, "charges_reconciliation"])
    assert user_client.get(url).status_code == 404
    response = user_client.get(url, {"reconciliation": reconciliation.pk})
    form = response.context["form"]
    assert form.initial["subject"] == (
        "Régularisation des charges du 1 janvier 2025 au 31 décembre 2025"
    )
    assert "à régler : 220,00 €" in form.initial["body"]
    assert response.context["attachment"] == "regularisation-charges-2025.pdf"
    with django_capture_on_commit_callbacks(execute=True):
        user_client.post(
            url,
            {
                "reconciliation": reconciliation.pk,
                "to": "jean@example.com",
                "subject": "Charges",
                "body": "Bonjour",
            },
        )
    (message,) = mail.outbox
    assert message.attachments[0].filename == "regularisation-charges-2025.pdf"
    reconciliation.refresh_from_db()
    assert reconciliation.status == ChargesReconciliation.Status.SENT
    assert Document.objects.filter(kind=Document.Kind.STATEMENT).count() == 1
    delete = reverse("rental:delete_reconciliation", args=[reconciliation.pk])
    user_client.post(delete)
    assert ChargesReconciliation.objects.exists()  # sent: kept
    draft = charges.create(lease, D(2025, 1, 1), D(2025, 6, 30))
    user_client.post(reverse("rental:delete_reconciliation", args=[draft.pk]))
    assert not ChargesReconciliation.objects.filter(pk=draft.pk).exists()
    # The other emails leave the reconciliation out.
    response = user_client.get(reverse("rental:lease_emails", args=[lease.pk]))
    assert "charges_reconciliation" not in [k.key for k in response.context["kinds"]]


@pytest.mark.django_db
def test_sent_reconciliation_is_read_only(user_client, year_lease):
    lease, _provisions = year_lease
    reconciliation = charges.create(lease, D(2025, 1, 1), D(2025, 12, 31))
    reconciliation.status = ChargesReconciliation.Status.SENT
    reconciliation.save()
    url = reverse("rental:reconciliation_detail", args=[reconciliation.pk])
    user_client.post(url, {"adjustment_label": ["X"], "adjustment_amount": ["5"]})
    reconciliation.refresh_from_db()
    assert reconciliation.adjustments == []


@pytest.mark.django_db
def test_flat_charges_tab(user_client, lease):
    lease.charges_mode = Lease.ChargesMode.FLAT
    lease.save()
    response = user_client.get(reverse("rental:lease_charges", args=[lease.pk]))
    assert "flat rate" in response.content.decode()


@pytest.mark.django_db
def test_reconciliation_due(year_lease):
    lease, _provisions = year_lease
    params = {"date": "03-01"}
    assert list(notifications._charges_due(params, D(2026, 2, 1))) == []
    (event,) = notifications._charges_due(params, D(2026, 3, 1))
    assert event.key == f"{lease.pk}:2025"
    charges.create(lease, D(2025, 1, 1), D(2025, 12, 31))
    assert list(notifications._charges_due(params, D(2026, 3, 1))) == []
    lease.charges_mode = Lease.ChargesMode.FLAT
    lease.save()
    assert list(notifications._charges_due(params, D(2027, 3, 1))) == []


@pytest.mark.django_db
def test_edge_cases(user_client, year_lease):
    lease, provisions = year_lease
    url = reverse("rental:create_reconciliation", args=[lease.pk])
    user_client.post(url, {"period_start": "bad", "period_end": "2025-12-31"})
    assert not ChargesReconciliation.objects.exists()
    reconciliation = charges.create(lease, D(2025, 1, 1), D(2025, 12, 31))
    detail = reverse("rental:reconciliation_detail", args=[reconciliation.pk])
    user_client.post(detail, {"adjustment_label": ["X"], "adjustment_amount": ["5"]})
    reconciliation.refresh_from_db()
    assert reconciliation.adjustments == [{"label": "X", "amount": "5.00"}]
    record = reverse("rental:record_reconciliation", args=[reconciliation.pk])
    user_client.post(record)
    user_client.post(record)
    assert (
        PropertyLedgerEntry.objects.filter(description__startswith="Charges").count()
        == 1
    )
    provisions.recurrence_end_date = D(2025, 6, 30)
    provisions.save()
    assert charges.update_provision(lease, Decimal(70), D(2026, 1, 1)) == 0
