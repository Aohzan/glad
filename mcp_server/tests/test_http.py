"""End-to-end tests of /mcp through the ASGI application."""

import json

import httpx
import pytest
from asgiref.sync import async_to_sync

from glad.asgi import Application
from mcp_server.models import ApiKey, McpCallLog

HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
    "MCP-Protocol-Version": "2025-06-18",
}
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"},
    },
}


def post(messages: list[dict], raw_key: str | None = None, path: str = "/mcp"):
    """POST each JSON-RPC message to a fresh application, return the responses."""

    async def run():
        app = Application()
        headers = dict(HEADERS)
        if raw_key is not None:
            headers["Authorization"] = f"Bearer {raw_key}"
        transport = httpx.ASGITransport(app=app, client=("203.0.113.7", 1234))
        async with (
            app.session_manager.run(),
            httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client,
        ):
            return [
                await client.post(path, headers=headers, json=message)
                for message in messages
            ]

    return async_to_sync(run)()


def tool_call(name: str, arguments: dict | None = None) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    }


@pytest.mark.django_db
def test_without_key_answers_401():
    (response,) = post([INITIALIZE])
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Bearer realm="glad"'


@pytest.mark.django_db
@pytest.mark.parametrize(
    "header", ["Bearer glad_abcd1234_wrong", "Basic abc", "Bearer "]
)
def test_with_a_wrong_key_answers_401(user, header):
    ApiKey.create(user, "Laptop")

    async def run():
        app = Application()
        async with (
            app.session_manager.run(),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client,
        ):
            return await client.post(
                "/mcp", headers={**HEADERS, "Authorization": header}, json=INITIALIZE
            )

    assert async_to_sync(run)().status_code == 401


@pytest.mark.django_db
def test_a_disabled_user_cannot_use_their_key(user):
    _key, raw = ApiKey.create(user, "Laptop")
    user.is_active = False
    user.save()
    (response,) = post([INITIALIZE], raw)
    assert response.status_code == 401


@pytest.mark.django_db
def test_a_child_cannot_use_a_key(user):
    _key, raw = ApiKey.create(user, "Laptop")
    user.profile.is_child = True
    user.profile.save()
    (response,) = post([INITIALIZE], raw)
    assert response.status_code == 401


@pytest.mark.django_db
def test_initialize_list_and_call_with_a_valid_key(user):
    key, raw = ApiKey.create(user, "Laptop")
    initialized, listed, called = post(
        [
            INITIALIZE,
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
            tool_call("get_upcoming_deadlines", {"limit": 3}),
        ],
        raw,
    )
    assert initialized.status_code == 200
    assert initialized.json()["result"]["serverInfo"]["name"] == "glad"
    names = {tool["name"] for tool in listed.json()["result"]["tools"]}
    assert {"get_net_worth", "get_property", "get_lease", "get_budget"} <= names
    result = called.json()["result"]
    assert result["isError"] is False
    assert isinstance(json.loads(result["content"][0]["text"]), list)
    key.refresh_from_db()
    assert key.last_used_at is not None
    assert key.last_used_ip == "203.0.113.7"
    log = McpCallLog.objects.get(api_key=key)
    assert log.tool == "get_upcoming_deadlines"
    assert log.arguments == {"limit": 3}
    assert log.success


@pytest.mark.django_db
def test_other_paths_go_to_django():
    (response,) = post([{}], path="/health")
    assert response.status_code != 401


@pytest.mark.parametrize(
    ("path", "root_path", "expected"),
    [
        ("/mcp", "", True),
        ("/mcp/", "", True),
        ("/glad/mcp", "/glad", True),
        ("/mcp-access/", "", False),
        ("/glad/finance/", "/glad", False),
    ],
)
def test_mcp_routing(path, root_path, expected):
    assert Application.is_mcp({"path": path, "root_path": root_path}) is expected


def test_lifespan_starts_and_stops_the_session_manager():
    app = Application()
    messages = iter([{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}])
    sent = []

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message["type"])

    async_to_sync(app)({"type": "lifespan"}, receive, send)
    assert sent == ["lifespan.startup.complete", "lifespan.shutdown.complete"]
