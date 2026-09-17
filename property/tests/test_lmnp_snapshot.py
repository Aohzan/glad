"""Tests for frozen LMNP declarations (snapshots) and their views."""

import datetime
import json
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils.functional import lazy
from moneyed import Money

from property.models import (
    AmortizationSetup,
    LmnpDeclarationSnapshot,
    Property,
    PropertyLedgerEntry,
)
from property.services.lmnp_rules import RULES_VERSION
from property.services.lmnp_snapshot import (
    build_snapshot_payload,
    create_snapshot,
    freeze,
    thaw,
)


@pytest.fixture
def lmnp_property(db):
    prop = Property.objects.create(
        name="Orléans",
        property_type=Property.APARTMENT,
        buying_value=Money(110_000, "EUR"),
        buying_date=datetime.date(2024, 11, 6),
        lmnp_start_date=datetime.date(2025, 1, 1),
        tax_regime=Property.TaxRegime.LMNP_REEL,
        is_active=True,
    )
    AmortizationSetup.objects.create(
        property=prop, total_value=Money(110_000, "EUR"), land_percentage=Decimal(15)
    ).initialize_components()
    PropertyLedgerEntry.objects.create(
        property=prop,
        flow_type=PropertyLedgerEntry.FlowType.INCOME,
        management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
        amount=Money(Decimal("7352.17"), "EUR"),
        entry_date=datetime.date(2025, 12, 31),
    )
    return prop


class TestFreezeThaw:
    def test_freeze_converts_every_non_json_type(self):
        lazy_label = lazy(lambda: "Loyers", str)()
        frozen = freeze(
            {
                "amount": Decimal("1234.5"),
                "money": Money(Decimal(10), "EUR"),
                "date": datetime.date(2025, 1, 31),
                "label": lazy_label,
                2025: [Decimal(1), ("a", None, True)],
            }
        )
        assert frozen == {
            "amount": "1234.50",
            "money": "10.00",
            "date": "2025-01-31",
            "label": "Loyers",
            "2025": ["1.00", ["a", None, True]],
        }
        json.dumps(frozen)

    def test_freeze_model_instance(self, lmnp_property):
        assert freeze(lmnp_property) == {"id": lmnp_property.pk, "name": "Orléans"}

    def test_thaw_restores_decimals_only(self):
        thawed = thaw({"a": "-3796.02", "b": "2025-01-31", "c": ["12.00", 3, "x"]})
        assert thawed == {
            "a": Decimal("-3796.02"),
            "b": "2025-01-31",
            "c": [Decimal("12.00"), 3, "x"],
        }
        assert thawed["a"] < 0  # templates can compare frozen amounts again


@pytest.mark.django_db
class TestSnapshotPayload:
    def test_payload_contains_every_section(self, lmnp_property):
        payload = build_snapshot_payload([lmnp_property], 2025)
        assert payload["fiscal_year"] == 2025
        assert payload["rules_version"] == RULES_VERSION
        assert payload["properties"][0]["amortization_start_date"] == "2025-01-01"
        assert payload["accounting"]["form_2033b"]["recettes"] == "7352.17"
        assert "cerfa_352" in payload["accounting"]["form_2033b"]
        assert payload["checklist"]["forms"]
        assert str(lmnp_property.pk) in payload["amortization"]
        json.dumps(payload)  # JSON-serialisable end to end

    def test_create_snapshot_stores_frozen_data(self, lmnp_property, admin_user):
        snapshot = create_snapshot(
            [lmnp_property], 2025, notes="déposée", user=admin_user
        )
        assert snapshot.fiscal_year == 2025
        assert snapshot.property_names == ["Orléans"]
        assert snapshot.created_by == admin_user
        assert list(snapshot.properties.all()) == [lmnp_property]
        assert snapshot.data["accounting"]["form_2033b"]["recettes"] == "7352.17"
        assert str(snapshot) == "LMNP 2025 — Orléans"

    def test_frozen_figures_survive_ledger_changes(self, lmnp_property):
        snapshot = create_snapshot([lmnp_property], 2025)
        PropertyLedgerEntry.objects.create(
            property=lmnp_property,
            flow_type=PropertyLedgerEntry.FlowType.INCOME,
            management_category=PropertyLedgerEntry.ManagementCategory.RENT_COLLECTED,
            amount=Money(Decimal(1000), "EUR"),
            entry_date=datetime.date(2025, 6, 1),
        )
        snapshot.refresh_from_db()
        assert snapshot.data["accounting"]["form_2033b"]["recettes"] == "7352.17"
        assert (
            build_snapshot_payload([lmnp_property], 2025)["accounting"]["form_2033b"][
                "recettes"
            ]
            == "8352.17"
        )


@pytest.mark.django_db
class TestSnapshotViews:
    def test_create_requires_post(self, admin_client, lmnp_property):
        response = admin_client.get(reverse("property:lmnp_snapshot_create"))
        assert response.status_code == 302
        assert LmnpDeclarationSnapshot.objects.count() == 0

    def test_create_then_detail(self, admin_client, lmnp_property):
        response = admin_client.post(
            reverse("property:lmnp_snapshot_create"), {"year": 2025, "notes": "test"}
        )
        snapshot = LmnpDeclarationSnapshot.objects.get()
        assert response.status_code == 302
        assert response.url == reverse(
            "property:lmnp_snapshot_detail", kwargs={"pk": snapshot.pk}
        )
        assert snapshot.notes == "test"

        detail = admin_client.get(response.url)
        assert detail.status_code == 200
        assert detail.context["accounting"]["form_2033b"]["recettes"] == Decimal(
            "7352.17"
        )
        assert "7 352" in detail.content.decode() or "7352" in detail.content.decode()

    def test_create_without_property_shows_error(self, admin_client):
        response = admin_client.post(
            reverse("property:lmnp_snapshot_create"), {"year": 2025}
        )
        assert response.status_code == 302
        assert LmnpDeclarationSnapshot.objects.count() == 0

    def test_list_view(self, admin_client, lmnp_property):
        create_snapshot([lmnp_property], 2025, notes="dépôt")
        response = admin_client.get(reverse("property:lmnp_snapshot_list"))
        assert response.status_code == 200
        assert "dépôt" in response.content.decode()

    def test_dashboard_mentions_existing_snapshot(self, admin_client, lmnp_property):
        create_snapshot([lmnp_property], 2025)
        response = admin_client.get(reverse("property:lmnp_accounting") + "?year=2025")
        assert response.status_code == 200
        assert response.context["snapshot_count"] == 1
        assert "déjà été figé" in response.content.decode()

    def test_delete_requires_post(self, admin_client, lmnp_property):
        snapshot = create_snapshot([lmnp_property], 2025)
        url = reverse("property:lmnp_snapshot_delete", kwargs={"pk": snapshot.pk})
        assert admin_client.get(url).status_code == 302
        assert LmnpDeclarationSnapshot.objects.count() == 1
        assert admin_client.post(url).status_code == 302
        assert LmnpDeclarationSnapshot.objects.count() == 0

    def test_anonymous_is_redirected_to_login(self, client, lmnp_property):
        snapshot = create_snapshot([lmnp_property], 2025)
        urls = [
            reverse("property:lmnp_pdf"),
            reverse("property:lmnp_snapshot_list"),
            reverse("property:lmnp_snapshot_detail", kwargs={"pk": snapshot.pk}),
            reverse("property:lmnp_snapshot_pdf", kwargs={"pk": snapshot.pk}),
        ]
        for url in urls:
            response = client.get(url)
            assert response.status_code == 302
            assert "login" in response.url
