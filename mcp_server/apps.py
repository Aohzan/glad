"""Configuration of the MCP server app."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class McpServerConfig(AppConfig):
    """API keys and MCP server giving an LLM client access to the data."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "mcp_server"
    verbose_name = _("MCP access")

    def ready(self):
        import mcp_server.tools  # noqa: F401  (registers the tools)
