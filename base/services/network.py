"""Client address of a request, behind the reverse proxy."""

import ipaddress
import socket
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


def is_internal_host(host: str) -> bool:
    """True when *host* resolves to the machine itself or a link-local address.

    Those addresses reach the services listening on the server itself (the
    application, its admin endpoints…) or the metadata service of a cloud
    provider: a URL entered by a user must not target them. The private networks stay allowed, for the
    services self-hosted on the local network. An unknown host is not internal.
    """
    host = host.strip().strip("[]")
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError, UnicodeError:
        return False
    for *_rest, sockaddr in infos:
        address = ipaddress.ip_address(str(sockaddr[0]).split("%")[0])
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        if (
            address.is_loopback
            or address.is_link_local
            or address.is_unspecified
            or address.is_multicast
        ):
            return True
    return False
