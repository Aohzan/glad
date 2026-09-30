"""Assets that are neither accounts nor real estate: vehicles, gold, crypto…

A single model covers every kind of asset: the category only sets sensible
defaults (liquidity for now), so new kinds of assets need no new model. The
value comes from a value history, which can be filled from a market quote
(quantity × price of a Yahoo Finance symbol) for listed assets.
"""

import datetime
from typing import TYPE_CHECKING

from django.db import models
from django.utils.translation import gettext_lazy as _
from djmoney.models.fields import MoneyField
from moneyed import Money

from base.choices import Liquidity
from base.models import BaseModel

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager


class OtherAsset(BaseModel):
    """A tangible or intangible asset tracked by its estimated value."""

    values: RelatedManager[OtherAssetValue]

    class Category(models.TextChoices):
        VEHICLE = "vehicle", _("Vehicle")
        PRECIOUS_METALS = "precious_metals", _("Precious metals")
        CRYPTO = "crypto", _("Crypto-assets")
        COMPANY_SHARES = "company_shares", _("Unlisted company shares")
        COLLECTIBLES = "collectibles", _("Art and collectibles")
        OTHER = "other", _("Other")

    #: Liquidity of each category when the asset does not set its own.
    CATEGORY_LIQUIDITY = {
        Category.VEHICLE: Liquidity.ILLIQUID,
        Category.PRECIOUS_METALS: Liquidity.CONDITIONAL,
        Category.CRYPTO: Liquidity.IMMEDIATE,
        Category.COMPANY_SHARES: Liquidity.ILLIQUID,
        Category.COLLECTIBLES: Liquidity.ILLIQUID,
        Category.OTHER: Liquidity.ILLIQUID,
    }
    CATEGORY_ICONS = {
        Category.VEHICLE: "bi-car-front",
        Category.PRECIOUS_METALS: "bi-coin",
        Category.CRYPTO: "bi-currency-bitcoin",
        Category.COMPANY_SHARES: "bi-briefcase",
        Category.COLLECTIBLES: "bi-palette",
        Category.OTHER: "bi-box-seam",
    }

    class Meta:
        verbose_name = _("other asset")
        verbose_name_plural = _("other assets")
        ordering = ["-is_active", "category", "name"]

    name = models.CharField(max_length=255, verbose_name=_("Name"))
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.OTHER,
        verbose_name=_("Category"),
    )
    owner = models.CharField(
        max_length=255, blank=True, default="", verbose_name=_("Owner")
    )
    acquisition_date = models.DateField(
        default=datetime.date.today, verbose_name=_("Acquisition date")
    )
    acquisition_value = MoneyField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name=_("Acquisition value"),
        help_text=_("Price paid, fees included."),
    )
    quantity = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        verbose_name=_("Quantity"),
        help_text=_("Units held, e.g. 0.5 for half a bitcoin or 10 gold coins."),
    )
    ticker = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name=_("Market symbol"),
        help_text=_(
            "Yahoo Finance symbol quoted in the asset currency (e.g. BTC-EUR), "
            "used with the quantity to update the value."
        ),
    )
    liquidity = models.CharField(
        max_length=20,
        choices=Liquidity.choices,
        blank=True,
        default="",
        verbose_name=_("Liquidity"),
        help_text=_("Leave empty to use the default of the category."),
    )
    is_active = models.BooleanField(default=True, verbose_name=_("Active"))
    sold_date = models.DateField(null=True, blank=True, verbose_name=_("Sold date"))
    notes = models.TextField(blank=True, verbose_name=_("Notes"))

    def __str__(self) -> str:
        return str(self.name)

    @property
    def currency(self) -> str:
        """Currency of the acquisition value."""
        return str(self.acquisition_value.currency)

    @property
    def icon(self) -> str:
        """Bootstrap icon of the category."""
        return self.CATEGORY_ICONS.get(self.category, "bi-box-seam")

    @property
    def effective_liquidity(self) -> str:
        """The asset liquidity, or the default of its category."""
        return self.liquidity or self.CATEGORY_LIQUIDITY.get(
            self.category, Liquidity.ILLIQUID
        )

    def get_effective_liquidity_display(self) -> str:
        """Human-readable liquidity."""
        return str(Liquidity(self.effective_liquidity).label)

    @property
    def has_market_price(self) -> bool:
        """True when the value can be computed from a market quote."""
        return bool(self.ticker and self.quantity)

    def get_value(self, max_date: datetime.date | None = None) -> Money:
        """Value at *max_date* (default today).

        Zero before the acquisition and from the sale date, otherwise the last
        recorded value, or the acquisition value when none is recorded yet.
        """
        max_date = max_date or datetime.date.today()
        if max_date < self.acquisition_date or (
            self.sold_date and max_date >= self.sold_date
        ):
            return Money(0, self.currency)
        last = self.values.filter(value_date__lte=max_date).order_by("-value_date")
        latest = last.first()
        return latest.value if latest else self.acquisition_value

    @property
    def current_value(self) -> Money:
        """Value today."""
        return self.get_value()

    @property
    def capital_gain(self) -> Money:
        """Current value minus the acquisition value."""
        return self.current_value - self.acquisition_value


class OtherAssetValue(BaseModel):
    """Estimated value of an asset at a date."""

    class Meta:
        verbose_name = _("other asset value")
        verbose_name_plural = _("other asset values")
        ordering = ["asset", "-value_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "value_date"], name="unique_other_asset_value"
            ),
        ]

    asset = models.ForeignKey(
        OtherAsset, related_name="values", on_delete=models.CASCADE
    )
    value = MoneyField(max_digits=12, decimal_places=2, verbose_name=_("Value"))
    value_date = models.DateField(default=datetime.date.today, verbose_name=_("Date"))

    def __str__(self) -> str:
        return f"{self.asset} - {self.value} ({self.value_date})"
