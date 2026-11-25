"""Client address of a request, behind the reverse proxy."""

from collections.abc import Mapping

from django.http import HttpRequest


def client_ip(meta: Mapping[str, str]) -> str:
    """The client IP from WSGI-style *meta*: its ``REMOTE_ADDR``.

    The ``X-Forwarded-For`` and ``X-Real-IP`` headers are not read: any client
    can send them. Behind a reverse proxy, uvicorn replaces the address of the
    proxy with the forwarded one when the proxy is trusted
    (``--forwarded-allow-ips``, see the README).
    """
    return meta.get("REMOTE_ADDR", "")


def request_client_ip(request: HttpRequest) -> str:
    """The client IP of *request* (``AXES_CLIENT_IP_CALLABLE``)."""
    return client_ip(request.META)
