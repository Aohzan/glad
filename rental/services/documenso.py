"""Client of the Documenso API v2 (self-hosted electronic signature).

Configured through ``DOCUMENSO_URL`` (the instance, e.g.
``https://sign.example.com``) and ``DOCUMENSO_API_TOKEN``. The field positions
are percentages of the page, as the API expects.
"""

import json
from dataclasses import dataclass

from django.conf import settings
lazy import httpx

TIMEOUT = 30


class DocumensoError(Exception):
    """The Documenso API could not be reached or refused the request."""


@dataclass(frozen=True)
class Field:
    """A signature or date field of a signer, in % of the page."""

    type: str
    page: int
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class Signer:
    name: str
    email: str
    fields: tuple[Field, ...] = ()


def is_configured() -> bool:
    return bool(settings.DOCUMENSO_URL and settings.DOCUMENSO_API_TOKEN)


class Documenso:
    def __init__(self, url: str | None = None, token: str | None = None) -> None:
        self.base_url = (url or settings.DOCUMENSO_URL).rstrip("/") + "/api/v2"
        self.token = token or settings.DOCUMENSO_API_TOKEN

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                headers={"Authorization": self.token},
                timeout=TIMEOUT,
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise DocumensoError(f"Documenso is unreachable: {exc}") from exc
        if response.is_error:
            raise DocumensoError(
                f"Documenso answered {response.status_code}: {response.text[:300]}"
            )
        return response

    def send(
        self,
        *,
        title: str,
        pdf: bytes,
        signers: list[Signer],
        external_id: str,
        subject: str,
        message: str,
    ) -> str:
        """Create an envelope, send it to the signers; its id."""
        payload = {
            "type": "DOCUMENT",
            "title": title,
            "externalId": external_id,
            "recipients": [
                {
                    "email": signer.email,
                    "name": signer.name,
                    "role": "SIGNER",
                    "signingOrder": index + 1,
                    "fields": [
                        {
                            "identifier": 0,
                            "type": field.type,
                            "page": field.page,
                            "positionX": field.x,
                            "positionY": field.y,
                            "width": field.width,
                            "height": field.height,
                        }
                        for field in signer.fields
                    ],
                }
                for index, signer in enumerate(signers)
            ],
            "meta": {"subject": subject, "message": message, "language": "fr"},
        }
        response = self._request(
            "POST",
            "/envelope/create",
            data={"payload": json.dumps(payload)},
            files={"files": (f"{external_id}.pdf", pdf, "application/pdf")},
        )
        envelope_id = response.json().get("id")
        if not envelope_id:
            raise DocumensoError("Documenso returned no envelope id.")
        self._request("POST", "/envelope/distribute", json={"envelopeId": envelope_id})
        return envelope_id

    def envelope(self, envelope_id: str) -> dict:
        return self._request("GET", f"/envelope/{envelope_id}").json()

    def download_signed(self, envelope: dict) -> bytes:
        items = envelope.get("envelopeItems") or []
        if not items:
            raise DocumensoError("The envelope holds no document.")
        response = self._request(
            "GET",
            f"/envelope/item/{items[0]['id']}/download",
            params={"version": "signed"},
        )
        return response.content
