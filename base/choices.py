"""Choices shared by the finance and property apps."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Liquidity(models.TextChoices):
    """How quickly an asset can be turned into cash without losing its tax benefits."""

    IMMEDIATE = "immediate", _("Available immediately")
    CONDITIONAL = "conditional", _("Available with conditions")
    ILLIQUID = "illiquid", _("Illiquid (sale needed)")
    LOCKED = "locked", _("Locked until a term")
