"""API keys giving an MCP client access to the data, and the log of its calls."""

import hashlib
import hmac
import secrets

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils.translation import gettext_lazy as _

from base.models import BaseModel

#: Start of every key, so a leaked one is easy to recognise.
KEY_SCHEME = "glad"
PREFIX_LENGTH = 8


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class ApiKey(BaseModel):
    """A key of a household member, read-only or allowed to write.

    Only the SHA-256 of the key is stored: it is shown once at creation. The
    key reads ``glad_<prefix>_<secret>``; the prefix finds the row without
    scanning the table.
    """

    class Meta:
        verbose_name = _("API key")
        verbose_name_plural = _("API keys")
        ordering = ["-created_at", "-pk"]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_keys"
    )
    name = models.CharField(max_length=100, verbose_name=_("Name"))
    prefix = models.CharField(max_length=PREFIX_LENGTH, unique=True)
    key_hash = models.CharField(max_length=64)
    can_write = models.BooleanField(default=False, verbose_name=_("Write access"))
    is_active = models.BooleanField(default=True, verbose_name=_("Active"))
    last_used_at = models.DateTimeField(null=True, blank=True)
    last_used_ip = models.CharField(max_length=45, blank=True)

    def __str__(self) -> str:
        return self.name

    @classmethod
    def create(cls, user, name: str, can_write: bool = False) -> tuple[ApiKey, str]:
        """Create a key; returns it with its clear value, never readable again."""
        prefix = secrets.token_hex(PREFIX_LENGTH // 2)
        secret = secrets.token_urlsafe(32)
        raw = f"{KEY_SCHEME}_{prefix}_{secret}"
        key = cls.objects.create(
            user=user,
            name=name,
            prefix=prefix,
            key_hash=_hash(raw),
            can_write=can_write,
        )
        return key, raw

    @classmethod
    def lookup(cls, raw: str) -> ApiKey | None:
        """The active key matching *raw*, None when unknown or revoked."""
        scheme, _sep, rest = raw.partition("_")
        prefix, _sep, secret = rest.partition("_")
        if scheme != KEY_SCHEME or len(prefix) != PREFIX_LENGTH or not secret:
            return None
        key = (
            cls.objects.filter(prefix=prefix, is_active=True)
            .select_related("user__profile")
            .first()
        )
        if key is None or not hmac.compare_digest(key.key_hash, _hash(raw)):
            return None
        return key


class McpCallLog(BaseModel):
    """One tool call made with an API key."""

    class Meta:
        verbose_name = _("MCP call")
        verbose_name_plural = _("MCP calls")
        ordering = ["-created_at", "-pk"]

    api_key = models.ForeignKey(ApiKey, on_delete=models.CASCADE, related_name="calls")
    tool = models.CharField(max_length=100)
    arguments = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)
    is_write = models.BooleanField(default=False)
    success = models.BooleanField(default=True)
    error = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.tool
