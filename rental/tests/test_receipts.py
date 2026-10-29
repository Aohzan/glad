"""Tests for the rent receipts."""

import datetime
from decimal import Decimal

import pytest
from moneyed import Money

from base.models import Document
from property.services.checks import check_occurrence
from rental.services.payments import lease_periods, period_of_month
from rental.services.receipts import receipt_for, receipt_pdf, store_receipt_pdf

TODAY = datetime.date(2026, 10, 20)
JULY = datetime.date(2026, 7, 1)


def _july(lease):
    period = period_of_month(lease_periods(lease, TODAY), JULY)
    assert period is not None
    return period


@pytest.mark.django_db
def test_full_receipt(lease, rent_schedule, user):
    rent, charges = rent_schedule
    check_occurrence(rent, datetime.date(2026, 7, 5))
    check_occurrence(charges, datetime.date(2026, 7, 5), datetime.date(2026, 7, 6))
    receipt = receipt_for(lease, _july(lease))
    assert (receipt.number, receipt.period_end) == (
        "2026-07",
        datetime.date(2026, 7, 31),
    )
    assert receipt.rent == Money(800, "EUR")
    assert receipt.charges == Money(50, "EUR")
    assert receipt.paid_amount == Money(850, "EUR")
    assert receipt.paid_date == datetime.date(2026, 7, 6)
    assert receipt.is_full
    assert receipt.filename == "quittance-2026-07.pdf"
    assert str(receipt) == "2026-07 — Jean Dupont (2026-07-01)"
    assert receipt_pdf(receipt, TODAY).startswith(b"%PDF")
    # Refreshed, not duplicated.
    assert receipt_for(lease, _july(lease)).pk == receipt.pk
    document = store_receipt_pdf(receipt, user)
    assert (document.kind, document.original_name) == (
        Document.Kind.RECEIPT,
        "quittance-2026-07.pdf",
    )
    assert document.content_object == lease


@pytest.mark.django_db
def test_partial_receipt(lease, rent_schedule):
    rent, _charges = rent_schedule
    check_occurrence(rent, datetime.date(2026, 7, 5), None, Money(Decimal(600), "EUR"))
    receipt = receipt_for(lease, _july(lease))
    assert receipt.paid_amount == Money(600, "EUR")
    assert not receipt.is_full
    assert receipt.filename == "recu-2026-07.pdf"
    assert receipt_pdf(receipt, TODAY).startswith(b"%PDF")
