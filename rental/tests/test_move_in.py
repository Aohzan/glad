"""Tests for the move-in steps and the security deposit."""

import datetime

import pytest
from django.urls import reverse
from moneyed import Money

from property.models import Lease
from rental.services.compliance import lease_checks
from rental.services.move_in import deposit_entry, move_in_steps


@pytest.mark.django_db
def test_steps(complete_lease):
    steps = move_in_steps(complete_lease, lease_checks(complete_lease))
    assert [(s.label, s.done) for s in steps] == [
        ("Lease signed", True),
        ("Entry inventory signed", True),
        ("Security deposit received", False),
        ("Insurance certificate", True),
        ("Rent schedule", False),
    ]
    complete_lease.deposit_amount = Money(0, "EUR")
    steps = move_in_steps(complete_lease, lease_checks(complete_lease))
    assert "Security deposit received" not in [s.label for s in steps]


@pytest.mark.django_db
def test_receive_deposit(user_client, lease):
    detail = reverse("rental:lease_detail", args=[lease.pk])
    assert not user_client.get(detail).context["show_steps"]  # started long ago
    lease.status = Lease.Status.UPCOMING
    lease.start_date = datetime.date.today() + datetime.timedelta(days=10)
    lease.save()
    response = user_client.get(detail)
    assert response.context["show_steps"]
    url = reverse("rental:receive_deposit", args=[lease.pk])
    user_client.post(url)
    user_client.post(url)
    entry = deposit_entry(lease)
    assert entry is not None
    assert entry.amount == lease.deposit_amount
    assert lease.ledger_entries.count() == 1
