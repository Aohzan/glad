"""Client address and internal host checks."""

import socket

import pytest
from django.test import RequestFactory

from base.services.network import client_ip, is_internal_host, request_client_ip


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


@pytest.mark.parametrize(
    ("host", "internal"),
    [
        ("127.0.0.1", True),
        ("127.1.2.3", True),
        ("[::1]", True),
        ("::ffff:127.0.0.1", True),
        ("2130706433", True),  # 127.0.0.1 written as an integer
        ("0.0.0.0", True),
        ("169.254.169.254", True),  # cloud metadata service
        ("fe80::1", True),
        ("224.0.0.1", True),
        ("localhost", True),
        ("192.168.1.10", False),
        ("10.0.0.5", False),
        ("203.0.113.7", False),
        ("", False),
    ],
)
def test_is_internal_host(host, internal):
    assert is_internal_host(host) is internal


def test_is_internal_host_checks_every_resolved_address(monkeypatch):
    def getaddrinfo(host, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.7", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
        ]

    monkeypatch.setattr("base.services.network.socket.getaddrinfo", getaddrinfo)
    assert is_internal_host("rebind.example")


def test_unknown_host_is_not_internal(monkeypatch):
    def getaddrinfo(host, *args, **kwargs):
        raise socket.gaierror(socket.EAI_NONAME, "Name not known")

    monkeypatch.setattr("base.services.network.socket.getaddrinfo", getaddrinfo)
    assert not is_internal_host("discord-webhook-id")
