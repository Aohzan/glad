"""Tests for the Documenso API client."""

import json

import httpx
import pytest

from rental.services import documenso
from rental.services.documenso import Documenso, DocumensoError, Field, Signer


@pytest.fixture
def calls(monkeypatch):
    recorded = []
    answers = {}

    def fake_request(method, url, **kwargs):
        recorded.append((method, url, kwargs))
        answer = answers.get((method, url.rsplit("/api/v2", 1)[1]))
        if isinstance(answer, Exception):
            raise answer
        status, body = answer or (200, {})
        content = body if isinstance(body, bytes) else json.dumps(body).encode()
        return httpx.Response(
            status, content=content, request=httpx.Request(method, url)
        )

    monkeypatch.setattr(documenso.httpx, "request", fake_request)
    return recorded, answers


def test_is_configured(settings):
    settings.DOCUMENSO_URL = ""
    settings.DOCUMENSO_API_TOKEN = "token"
    assert not documenso.is_configured()
    settings.DOCUMENSO_URL = "https://sign.example.com"
    assert documenso.is_configured()


def test_send(calls):
    recorded, answers = calls
    answers["POST", "/envelope/create"] = (200, {"id": "envelope_1"})
    client = Documenso("https://sign.example.com/", "api_token")
    envelope_id = client.send(
        title="Bail",
        pdf=b"%PDF",
        signers=[
            Signer("Anne", "anne@example.com", (Field("SIGNATURE", 3, 10, 22, 45, 9),))
        ],
        external_id="glad-lease-1",
        subject="Signature",
        message="Merci",
    )
    assert envelope_id == "envelope_1"
    (_method, url, create), (_m, distribute_url, distribute) = recorded
    assert url == "https://sign.example.com/api/v2/envelope/create"
    assert create["headers"] == {"Authorization": "api_token"}
    payload = json.loads(create["data"]["payload"])
    (recipient,) = payload["recipients"]
    assert recipient["email"] == "anne@example.com"
    assert recipient["fields"][0] == {
        "identifier": 0,
        "type": "SIGNATURE",
        "page": 3,
        "positionX": 10,
        "positionY": 22,
        "width": 45,
        "height": 9,
    }
    assert create["files"]["files"][1] == b"%PDF"
    assert distribute_url.endswith("/envelope/distribute")
    assert distribute["json"] == {"envelopeId": "envelope_1"}


def test_send_without_id(calls):
    client = Documenso("https://sign.example.com", "t")
    with pytest.raises(DocumensoError, match="no envelope id"):
        client.send(
            title="T", pdf=b"", signers=[], external_id="x", subject="", message=""
        )


def test_errors(calls):
    _recorded, answers = calls
    client = Documenso("https://sign.example.com", "t")
    answers["GET", "/envelope/e1"] = (404, {"message": "not found"})
    with pytest.raises(DocumensoError, match="answered 404"):
        client.envelope("e1")
    answers["GET", "/envelope/e1"] = httpx.ConnectError("down")
    with pytest.raises(DocumensoError, match="unreachable"):
        client.envelope("e1")


def test_download_signed(calls):
    recorded, answers = calls
    answers["GET", "/envelope/item/item_1/download"] = (200, b"%PDF-signed")
    client = Documenso("https://sign.example.com", "t")
    assert (
        client.download_signed({"envelopeItems": [{"id": "item_1"}]}) == b"%PDF-signed"
    )
    assert recorded[-1][2]["params"] == {"version": "signed"}
    with pytest.raises(DocumensoError, match="no document"):
        client.download_signed({"envelopeItems": []})
