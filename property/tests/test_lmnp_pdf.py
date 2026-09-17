"""Tests for the fpdf2 rendering of the LMNP liasse."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from moneyed import Money

from property.models import AmortizationSetup, Property, PropertyLedgerEntry
from property.services.lmnp_pdf import money, render_lmnp_pdf
from property.services.lmnp_snapshot import build_snapshot_payload, create_snapshot


@pytest.fixture
def lmnp_property(db):
    prop = Property.objects.create(
        name="Orléans — T2 « Cœur de ville »",
        property_type=Property.APARTMENT,
        buying_value=Money(110_000, "EUR"),
        buying_date=datetime.date(2025, 1, 1),
        tax_regime=Property.TaxRegime.LMNP_REEL,
        is_active=True,
    )
    AmortizationSetup.objects.create(
        property=prop, total_value=Money(110_000, "EUR"), land_percentage=Decimal(15)
    ).initialize_components()
    PropertyLedgerEntry.objects.create(
        property=prop,
        flow_type=PropertyLedgerEntry.FlowType.EXPENSE,
        management_category=PropertyLedgerEntry.ManagementCategory.COOWNERSHIP,
        amount=Money(Decimal("1316.18"), "EUR"),
        entry_date=datetime.date(2025, 12, 31),
    )
    return prop


def test_money_formatting():
    assert money("1234.5") == "1 234,50 €"
    assert money(Decimal("-3796.02")) == "-3 796,02 €"
    assert money(None) == ""


@pytest.mark.django_db
def test_render_pdf_with_euro_and_accents(lmnp_property):
    payload = build_snapshot_payload([lmnp_property], 2025)
    pdf = render_lmnp_pdf(payload)
    assert pdf.startswith(b"%PDF")
    assert pdf.count(b"/Type /Page\n") >= 6 or pdf.count(b"/Type /Page") >= 6


@pytest.mark.django_db
def test_render_pdf_without_property_or_data():
    payload = build_snapshot_payload([], 2025)
    assert render_lmnp_pdf(payload).startswith(b"%PDF")


@pytest.mark.django_db
def test_live_pdf_view(admin_client, lmnp_property):
    response = admin_client.get(reverse("property:lmnp_pdf") + "?year=2025")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"] == 'attachment; filename="lmnp_2025.pdf"'
    assert response.content.startswith(b"%PDF")


@pytest.mark.django_db
def test_snapshot_pdf_view(admin_client, lmnp_property):
    snapshot = create_snapshot([lmnp_property], 2025)
    response = admin_client.get(
        reverse("property:lmnp_snapshot_pdf", kwargs={"pk": snapshot.pk})
    )
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
