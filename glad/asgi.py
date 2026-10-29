"""
ASGI config for glad project.

It exposes the ASGI callable as a module-level variable named ``application``:
``/mcp`` goes to the MCP server, everything else to Django.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "glad.settings")

django_application = get_asgi_application()

# Imported once Django is set up: the MCP server loads the models.
from mcp_server.server import build_http_app, mcp

MCP_PATH = "/mcp"


class Application:
    """Route ``/mcp`` to the MCP app and run its session manager in the lifespan."""

    def __init__(self):
        self.mcp_app = build_http_app()
        self.session_manager = mcp.session_manager

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self.lifespan(receive, send)
        elif scope["type"] == "http" and self.is_mcp(scope):
            await self.mcp_app(scope, receive, send)
        else:
            await django_application(scope, receive, send)

    @staticmethod
    def is_mcp(scope) -> bool:
        # Behind ``uvicorn --root-path``, the path starts with the sub-path.
        path = scope["path"].removeprefix(scope.get("root_path", ""))
        return path == MCP_PATH or path.startswith(f"{MCP_PATH}/")

    async def lifespan(self, receive, send):
        await receive()  # lifespan.startup
        async with self.session_manager.run():
            await send({"type": "lifespan.startup.complete"})
            await receive()  # lifespan.shutdown
        await send({"type": "lifespan.shutdown.complete"})


application = Application()
