"""Client address and internal host checks."""

from django.test import RequestFactory

from base.services.network import client_ip, request_client_ip


def test_client_ip_is_the_connection_address():
    meta = {
        "REMOTE_ADDR": "172.22.1.1",
        "HTTP_X_FORWARDED_FOR": "9.8.7.6",
        "HTTP_X_REAL_IP": "203.0.113.50",
    }
    assert client_ip(meta) == "172.22.1.1"
    assert client_ip({}) == ""


def test_request_client_ip():
    request = RequestFactory().get("/", REMOTE_ADDR="198.51.100.4")
    assert request_client_ip(request) == "198.51.100.4"
