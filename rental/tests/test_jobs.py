"""Tests for the daily rent emails."""

import datetime

import pytest
from django.core import mail
from django.test import override_settings

from base.models import SentEmail
from property.models import ManagementMandate
from property.services.checks import check_occurrence
from rental import jobs
from rental.models import RentReceipt

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


@pytest.fixture
def automatic(lease, rent_schedule):
    lease.send_rent_calls = lease.send_receipts = True
    lease.save()
    return rent_schedule


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_rent_call_sent_once(lease, automatic, django_capture_on_commit_callbacks):
    today = datetime.date(2026, 10, 29)
    with django_capture_on_commit_callbacks(execute=True):
        assert jobs.send_rent_emails(today) == "1 rent call(s), 0 receipt(s) sent"
        assert jobs.send_rent_emails(today) == "0 rent call(s), 0 receipt(s) sent"
    (message,) = mail.outbox
    assert message.subject == "Avis d'échéance — loyer de novembre 2026"
    assert message.to == ["jean@example.com"]
    email = SentEmail.objects.get()
    assert (email.kind, email.reference, email.related) == (
        "rent_call",
        "2026-11",
        lease,
    )


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_receipts_of_the_recent_paid_periods(
    lease, automatic, django_capture_on_commit_callbacks
):
    rent, charges = automatic
    for month in (7, 8, 9):
        for entry in (rent, charges):
            check_occurrence(entry, datetime.date(2026, month, 5))
    check_occurrence(rent, datetime.date(2026, 10, 5))  # partial: no receipt
    lease.send_rent_calls = False
    lease.save()
    today = datetime.date(2026, 10, 20)
    with django_capture_on_commit_callbacks(execute=True):
        assert jobs.send_rent_emails(today) == "0 rent call(s), 2 receipt(s) sent"
        assert jobs.send_rent_emails(today) == "0 rent call(s), 0 receipt(s) sent"
    assert sorted(m.subject for m in mail.outbox) == [
        "Quittance de loyer — août 2026",
        "Quittance de loyer — septembre 2026",
    ]
    assert mail.outbox[0].attachments[0].filename.startswith("quittance-2026-0")
    assert RentReceipt.objects.filter(sent_at__isnull=False).count() == 2


@pytest.mark.django_db
def test_skipped_leases(lease, automatic):
    today = datetime.date(2026, 10, 29)
    ManagementMandate.objects.create(
        property=lease.property, manager_name="Foncia", start_date=lease.start_date
    )
    assert jobs.send_rent_emails(today) == "0 rent call(s), 0 receipt(s) sent"
    ManagementMandate.objects.all().delete()
    lease.parties.update(email="")
    assert jobs.send_rent_emails(today) == "0 rent call(s), 0 receipt(s) sent"
    lease.send_rent_calls = lease.send_receipts = False
    lease.save()
    assert jobs.send_rent_emails(today) == "0 rent call(s), 0 receipt(s) sent"


def test_job_is_registered():
    from base.scheduler import get_job

    assert get_job("rental_daily").at == datetime.time(7, 30)
