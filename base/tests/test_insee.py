"""Tests for the INSEE index download and the economic index model."""

import datetime
from decimal import Decimal
from io import StringIO

import httpx
import pytest
from django.core.management import CommandError, call_command
from django.urls import reverse

from base.models import EconomicIndex, EconomicIndexValue
from base.services import insee

PAYLOAD = """<?xml version='1.0'?><message:StructureSpecificData><message:DataSet>
<Series IDBANK="001515333" FREQ="T">
<Obs TIME_PERIOD="2026-Q2" OBS_VALUE="148.37" OBS_STATUS="A" DATE_JO="2026-07-12"/>
<Obs TIME_PERIOD="2026-Q1" OBS_VALUE="146.6" OBS_STATUS="A"/>
<Obs TIME_PERIOD="bad" OBS_VALUE="1"/>
<Obs TIME_PERIOD="2025-Q4" OBS_VALUE="NaN"/>
<Obs TIME_PERIOD="2025-Q3" OBS_VALUE="x"/>
</Series></message:DataSet></message:StructureSpecificData>"""


@pytest.fixture(autouse=True)
def _no_stored_index(request):
    """Start from an empty index table, whatever the session fixtures loaded."""
    if "db" in request.fixturenames or request.node.get_closest_marker("django_db"):
        EconomicIndexValue.objects.all().delete()


class _Response:
    def __init__(self, text: str, status: int = 200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://x")
            raise httpx.HTTPStatusError(
                "boom",
                request=request,
                response=httpx.Response(self.status_code, request=request),
            )


@pytest.fixture
def fake_get(monkeypatch):
    calls = []

    def _install(text=PAYLOAD, status=200, exc=None):
        def _get(url, params=None, timeout=None):
            calls.append((url, params))
            if exc is not None:
                raise exc
            return _Response(text, status)

        monkeypatch.setattr(insee.httpx, "get", _get)
        return calls

    return _install


class TestParsing:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("2026-Q2", datetime.date(2026, 4, 1)),
            ("2026-Q4", datetime.date(2026, 10, 1)),
            ("2026-08", datetime.date(2026, 8, 1)),
            ("2026-13", None),
            ("2026", None),
        ],
    )
    def test_parse_period(self, raw, expected):
        assert insee.parse_period(raw) == expected

    def test_parse_observations_skips_invalid(self):
        observations = insee.parse_observations(PAYLOAD)
        assert [o.period for o in observations] == [
            datetime.date(2026, 4, 1),
            datetime.date(2026, 1, 1),
        ]
        assert observations[0].value == Decimal("148.37")
        assert observations[0].published_on == datetime.date(2026, 7, 12)
        assert observations[1].published_on is None


class TestFetch:
    def test_start_period_formats(self, fake_get):
        calls = fake_get()
        insee.fetch_series(EconomicIndex.IRL, start=datetime.date(2026, 5, 1))
        insee.fetch_series(EconomicIndex.CPI, start=datetime.date(2026, 5, 1))
        insee.fetch_series(EconomicIndex.CPI)
        assert calls[0][1] == {"startPeriod": "2026-Q2"}
        assert calls[1][1] == {"startPeriod": "2026-05"}
        assert calls[2][1] == {}
        assert "001515333" in calls[0][0]

    def test_http_error(self, fake_get):
        fake_get(exc=httpx.ConnectError("down"))
        with pytest.raises(insee.InseeError):
            insee.fetch_series(EconomicIndex.IRL)

    def test_status_error(self, fake_get):
        fake_get(status=500)
        with pytest.raises(insee.InseeError):
            insee.fetch_series(EconomicIndex.IRL)

    def test_empty_answer(self, fake_get):
        fake_get(text="<xml/>")
        with pytest.raises(insee.InseeError):
            insee.fetch_series(EconomicIndex.IRL)


@pytest.mark.django_db
class TestRefresh:
    def test_refresh_upserts_from_last_period(self, fake_get):
        EconomicIndexValue.objects.create(
            index=EconomicIndex.IRL,
            period=datetime.date(2026, 1, 1),
            value=Decimal("146.00"),
        )
        calls = fake_get()
        assert insee.refresh_index(EconomicIndex.IRL) == 2
        assert calls[0][1] == {"startPeriod": "2026-Q1"}
        revised = EconomicIndexValue.objects.get(period=datetime.date(2026, 1, 1))
        assert revised.value == Decimal("146.600")
        assert EconomicIndexValue.objects.filter(index=EconomicIndex.IRL).count() == 2

    def test_command(self, fake_get):
        fake_get()
        out = StringIO()
        call_command("refresh_economic_indices", stdout=out)
        assert "2 value(s) updated" in out.getvalue()

    def test_command_failure(self, fake_get):
        fake_get(exc=httpx.ConnectError("down"))
        with pytest.raises(CommandError):
            call_command("refresh_economic_indices", stderr=StringIO())

    def test_view_refreshes_and_redirects(self, user_client, fake_get):
        fake_get()
        response = user_client.post(
            reverse("refresh_economic_indices"), {"next": "/property/"}
        )
        assert response.status_code == 302
        assert response.url == "/property/"
        assert EconomicIndexValue.objects.count() == 4

    def test_view_rejects_external_next(self, user_client, fake_get):
        fake_get(exc=httpx.ConnectError("down"))
        response = user_client.post(
            reverse("refresh_economic_indices"), {"next": "https://evil.example/"}
        )
        assert response.status_code == 302
        assert response.url == reverse("index")

    def test_view_requires_post(self, user_client):
        assert user_client.get(reverse("refresh_economic_indices")).status_code == 405


@pytest.mark.django_db
class TestModel:
    def test_labels(self):
        irl = EconomicIndexValue(
            index=EconomicIndex.IRL, period=datetime.date(2026, 4, 1), value=1
        )
        cpi = EconomicIndexValue(
            index=EconomicIndex.CPI, period=datetime.date(2026, 8, 1), value=2
        )
        assert irl.quarter == 2
        assert irl.period_label == "Q2 2026"
        assert cpi.period_label == "2026-08"
        assert str(irl) == "Rent reference index (IRL) Q2 2026: 1"
