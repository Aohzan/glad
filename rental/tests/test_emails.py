"""Tests for the emails to the tenants."""

import datetime

import pytest

from property.services.checks import check_occurrence
from rental import emails
from rental.services.payments import lease_periods, period_of_month

TODAY = datetime.date(2026, 10, 20)


def _render(kind, lease, month=None):
    periods = lease_periods(lease, TODAY)
    period = period_of_month(periods, month) if month else None
    return emails.render(emails.KINDS[kind], lease, periods, period, TODAY)


@pytest.mark.django_db
def test_rent_call(lease, rent_schedule):
    subject, body = _render("rent_call", lease, datetime.date(2026, 11, 1))
    assert subject == "Avis d'échéance — loyer de novembre 2026"
    assert "Bonjour Jean Dupont," in body
    assert "payable le 5 novembre 2026" in body
    assert "Total à régler : 850,00 €" in body
    assert body.endswith("SCI Lilas\n")


@pytest.mark.django_db
def test_receipt(lease, rent_schedule):
    rent, charges = rent_schedule
    check_occurrence(rent, datetime.date(2026, 7, 5))
    subject, body = _render("receipt", lease, datetime.date(2026, 7, 1))
    assert subject == "Reçu de paiement — juillet 2026"
    assert "qui ne vaut pas quittance" in body
    check_occurrence(charges, datetime.date(2026, 7, 5))
    subject, body = _render("receipt", lease, datetime.date(2026, 7, 1))
    assert subject == "Quittance de loyer — juillet 2026"


@pytest.mark.django_db
def test_reminder_and_formal_notice(lease, rent_schedule, guarantor):
    guarantor.email = "marc@example.com"
    guarantor.save()
    _subject, body = _render("reminder", lease)
    assert "- septembre 2026 (échéance du 5 septembre 2026) : 850,00 €" in body
    assert "Soit un total de 3 400,00 €." in body
    subject, body = _render("formal_notice", lease)
    assert subject == "Mise en demeure de payer les loyers impayés"
    assert "Le 20 octobre 2026" in body
    assert emails.copies(lease, emails.KINDS["formal_notice"]) == ["marc@example.com"]
    assert emails.copies(lease, emails.KINDS["reminder"]) == []


@pytest.mark.django_db
def test_rent_revision_and_insurance(lease):
    lease.irl_reference_quarter = 2
    lease.irl_reference_value = "145.17"
    lease.last_rent_revision_date = datetime.date(2026, 7, 1)
    _subject, body = _render("rent_revision", lease)
    assert (
        "à compter du 1 juillet 2026" in body or "à compter du 1er juillet 2026" in body
    )
    assert "du 2e trimestre, d'une valeur de 145.17" in body
    assert "Nouveau loyer hors charges : 800,00 €" in body
    subject, _body = _render("insurance_request", lease)
    assert subject == "Attestation d'assurance habitation"


@pytest.mark.django_db
def test_names_are_not_escaped(lease):
    tenant = lease.tenants[0]
    tenant.last_name = "D'Artagnan & fils"
    tenant.save()
    lease.refresh_from_db()
    _subject, body = _render("insurance_request", lease)
    assert "Bonjour Jean D'Artagnan & fils," in body


@pytest.mark.django_db
def test_recipients(lease):
    lease.tenants  # noqa: B018
    lease.parties.create(last_name="Sans email")
    assert emails.recipients(lease) == ["jean@example.com"]
