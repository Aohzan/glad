"""Client address of a request, behind the reverse proxy."""

from collections.abc import Mapping


def client_ip(meta: Mapping[str, str]) -> str:
    """The client IP from WSGI-style *meta* (``HTTP_X_FORWARDED_FOR``…)."""
    if x_forwarded_for := meta.get("HTTP_X_FORWARDED_FOR"):
        return x_forwarded_for.split(",")[0].strip()
    if x_real_ip := meta.get("HTTP_X_REAL_IP"):
        return x_real_ip.strip()
    return meta.get("REMOTE_ADDR", "")
