"""Choices shared by the finance and property apps."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Liquidity(models.TextChoices):
    """How quickly an asset can be turned into cash without losing its tax benefits."""

    IMMEDIATE = "immediate", _("Available immediately")
    CONDITIONAL = "conditional", _("Available with conditions")
    ILLIQUID = "illiquid", _("Illiquid (sale needed)")
    LOCKED = "locked", _("Locked until a term")


class AssetClass(models.TextChoices):
    """Economic nature of an asset, used for the allocation breakdown."""

    CASH = "cash", _("Cash and savings books")
    EURO_FUND = "euro_fund", _("Euro funds")
    MONEY_MARKET = "money_market", _("Money market")
    BONDS = "bonds", _("Bonds")
    EQUITIES = "equities", _("Equities")
    MIXED = "mixed", _("Diversified funds")
    REAL_ESTATE = "real_estate", _("Real estate")
    COMMODITIES = "commodities", _("Commodities and precious metals")
    CRYPTO = "crypto", _("Crypto-assets")
    PRIVATE_EQUITY = "private_equity", _("Unlisted shares")
    TANGIBLE = "tangible", _("Tangible assets")
    OTHER = "other", _("Other")
