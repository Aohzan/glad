"""Fixtures of the MCP server tests."""

import json

import pytest
from asgiref.sync import async_to_sync
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent

from mcp_server.models import ApiKey
from mcp_server.server import current_key, mcp


@pytest.fixture
def api_key(user):
    """A read-only key of the test user."""
    key, _raw = ApiKey.create(user, "Laptop")
    return key


@pytest.fixture
def write_key(user):
    key, _raw = ApiKey.create(user, "Writer", can_write=True)
    return key


def call_tool(key: ApiKey | None, name: str, **arguments):
    """Call a tool as *key*; returns the decoded JSON result, or raises."""
    token = current_key.set(key)
    try:
        result = async_to_sync(mcp.call_tool)(name, arguments)
    except ToolError as exc:
        raise ToolFailed(str(exc)) from exc
    finally:
        current_key.reset(token)
    assert isinstance(result, CallToolResult)
    content = result.content[0]
    assert isinstance(content, TextContent)
    if result.is_error:
        raise ToolFailed(content.text)
    return json.loads(content.text)


class ToolFailed(Exception):
    """The tool answered with an error."""
