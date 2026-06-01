"""Models for SCPI (Société Civile de Placement Immobilier) management."""

import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.manager import Manager
from django.utils.translation import gettext_lazy as _
from djmoney.models.fields import MoneyField
from moneyed import Money

from base.models import BaseModel

if TYPE_CHECKING:
    pass


class SCPI(BaseModel):
    """A SCPI fund (the investment vehicle).

    Stores the fund's metadata and current fee structure.
    Historical share prices are tracked in SCPISharePrice.
    """

    if TYPE_CHECKING:
        share_prices: Manager["SCPISharePrice"]
        dividends: Manager["SCPIDividend"]
        investments: Manager["SCPIInvestment"]

    class DividendRecurrence(models.TextChoices):
        MONTHLY = "monthly", _("Monthly")
        QUARTERLY = "quarterly", _("Quarterly")
        ANNUAL = "annual", _("Annual")

    class Meta:
        verbose_name = _("SCPI")
        verbose_name_plural = _("SCPI")
        ordering = ["name"]

    name = models.CharField(max_length=255, verbose_name=_("Name"))
    management_company = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Management company"),
    )
    entry_fee_rate = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name=_("Entry fee rate (%)"),
        help_text=_("Subscription fee as a percentage, e.g. 8.0000 for 8%."),

    )
    exit_fee_rate = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name=_("Exit fee rate (%)"),
        help_text=_("Redemption fee as a percentage, e.g. 0.0000 for 0%."),
    )
    management_fee_rate = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name=_("Management fee rate (%)"),
        help_text=_("Annual management fee as a percentage, e.g. 10.0000 for 10%."),
    )
    notes = models.TextField(blank=True, default="", verbose_name=_("Notes"))
    dividend_recurrence = models.CharField(
        max_length=10,
        choices=DividendRecurrence.choices,
        default=DividendRecurrence.QUARTERLY,
        verbose_name=_("Dividend recurrence"),
        help_text=_("How often dividends are paid: monthly, quarterly, or annually."),
    )

    def __str__(self) -> str:
        return str(self.name)

    def get_share_price(
        self, as_of_date: datetime.date | None = None
    ) -> "SCPISharePrice | None":
        """Return the most recent SCPISharePrice on or before as_of_date.

        Returns None if no share price has been recorded yet.
        """
        if as_of_date is None:
            as_of_date = datetime.date.today()
        return self.share_prices.filter(date__lte=as_of_date).order_by("-date").first()

    @property
    def current_subscription_value(self) -> Money | None:
        """Current (latest) share subscription value."""
        price = self.get_share_price()
        return price.subscription_value if price else None

    @property
    def current_withdrawal_value(self) -> Money | None:
        """Current (latest) share withdrawal (redemption) value."""
        price = self.get_share_price()
        if price is None:
            return None
        return price.withdrawal_value or price.subscription_value

    def get_total_dividends_received(self) -> "Money":
        """Return the total net dividends received across all recorded payments."""
        total = sum(
            (d.net_amount.amount for d in self.dividends.all()),
            Decimal("0"),
        )
        currency = "EUR"
        div = self.dividends.first()
        if div and hasattr(div.net_amount, "currency"):
            currency = str(div.net_amount.currency)
        return Money(total, currency)

    def get_dividends_received_in_period(
        self, start_date: "datetime.date", end_date: "datetime.date"
    ) -> "Money":
        """Return the total net dividends received in a specific date range."""
        total = sum(
            (
                d.net_amount.amount
                for d in self.dividends.filter(
                    payment_date__range=(start_date, end_date)
                )
            ),
            Decimal("0"),
        )
        currency = "EUR"
        div = self.dividends.first()
        if div and hasattr(div.net_amount, "currency"):
            currency = str(div.net_amount.currency)
        return Money(total, currency)


class SCPISharePrice(BaseModel):
    """Historical share price record for a SCPI fund.

    Analogous to PropertyValue — allows tracking the subscription and
    withdrawal prices over time to compute accurate capital gains.
    """

    class Meta:
        verbose_name = _("SCPI share price")
        verbose_name_plural = _("SCPI share prices")
        ordering = ["-date"]
        unique_together = [("scpi", "date")]

    scpi = models.ForeignKey(
        SCPI,
        on_delete=models.CASCADE,
        related_name="share_prices",
        verbose_name=_("SCPI"),
    )
    date = models.DateField(verbose_name=_("Date"))
    subscription_value = MoneyField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("Subscription value"),
        help_text=_("Price per share for new subscriptions at this date."),
    )
    withdrawal_value = MoneyField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Withdrawal value"),
        help_text=_(
            "Price per share for redemptions at this date."
            " Leave blank if equal to subscription value."
        ),
    )

    def __str__(self) -> str:
        return f"{self.scpi} — {self.date}"


class SCPIInvestment(BaseModel):
    """Shares held by the user in a given SCPI fund.

    Supports full ownership, bare ownership (nue-propriété) and usufruct
    (usufruit) as part of a dismemberment (démembrement) operation.
    """

    class OwnershipType(models.TextChoices):
        FULL = "full", _("Full ownership")
        BARE = "bare", _("Bare ownership (nue-propriété)")
        USUFRUCT = "usufruct", _("Usufruct (usufruit)")

    class Meta:
        verbose_name = _("SCPI investment")
        verbose_name_plural = _("SCPI investments")
        ordering = ["-subscription_date"]

    scpi = models.ForeignKey(
        SCPI,
        on_delete=models.PROTECT,
        related_name="investments",
        verbose_name=_("SCPI"),
    )
    subscription_date = models.DateField(
        verbose_name=_("Subscription date"),
        help_text=_("Date on which the shares were purchased."),
    )
    shares_count = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        verbose_name=_("Number of shares"),
        help_text=_("Number of shares held, e.g. 100.0000."),
    )
    unit_purchase_price = MoneyField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("Unit purchase price"),
        help_text=_(
            "Total price paid per share at subscription (entry fees included)."
        ),
    )
    enjoyment_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Enjoyment date"),
        help_text=_(
            "Date from which dividends start being paid (usually a few months"
            " after subscription)."
        ),
    )
    ownership_type = models.CharField(
        max_length=10,
        choices=OwnershipType.choices,
        default=OwnershipType.FULL,
        verbose_name=_("Ownership type"),
    )
    # ── Dismemberment fields (only relevant for BARE / USUFRUCT) ─────────────
    dismemberment_start_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Dismemberment start date"),
    )
    dismemberment_end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Dismemberment end date"),
        help_text=_(
            "Date on which the dismemberment ends and the bare owner"
            " recovers full ownership."
        ),
    )
    bare_ownership_ratio = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Bare ownership ratio at purchase (%)"),
        help_text=_(
            "Percentage of the full share value attributed to bare ownership at"
            " the time of purchase, e.g. 65.00 for 65%."
        ),
    )
    notes = models.TextField(blank=True, default="")

    def __str__(self) -> str:
        return f"{self.scpi} — {self.shares_count} shares ({self.subscription_date})"

    def clean(self) -> None:
        """Validate dismemberment fields are present when ownership type requires them."""
        if self.ownership_type in (
            self.OwnershipType.BARE,
            self.OwnershipType.USUFRUCT,
        ):
            missing = []
            if not self.dismemberment_start_date:
                missing.append("dismemberment_start_date")
            if not self.dismemberment_end_date:
                missing.append("dismemberment_end_date")
            if self.bare_ownership_ratio is None:
                missing.append("bare_ownership_ratio")
            if missing:
                raise ValidationError(
                    _(
                        "The following fields are required for dismembered ownership:"
                        " %(fields)s"
                    )
                    % {"fields": ", ".join(missing)}
                )
        if (
            self.dismemberment_start_date
            and self.dismemberment_end_date
            and self.dismemberment_start_date >= self.dismemberment_end_date
        ):
            raise ValidationError(_("Dismemberment end date must be after start date."))
        if self.bare_ownership_ratio is not None and not (
            Decimal("0") <= self.bare_ownership_ratio <= Decimal("100")
        ):
            raise ValidationError(_("Bare ownership ratio must be between 0 and 100."))

    # ── Financial calculations ─────────────────────────────────────────────────

    @property
    def currency(self) -> str:
        """Return the ISO currency code for this investment."""
        if hasattr(self.unit_purchase_price, "currency"):
            return str(self.unit_purchase_price.currency)
        return "EUR"  # pragma: no cover

    def get_purchase_value(self) -> Money:
        """Return the raw purchase value: shares × unit purchase price (excl. fees)."""
        return Money(
            self.shares_count * self.unit_purchase_price.amount,
            self.currency,
        )

    def get_entry_fees(self) -> Money:
        """Return the total entry fees paid: purchase value × entry_fee_rate %."""
        rate = self.scpi.entry_fee_rate
        if not rate:
            return Money(Decimal("0"), self.currency)
        return Money(
            (self.get_purchase_value().amount * rate / Decimal("100")).quantize(
                Decimal("0.01")
            ),
            self.currency,
        )

    def get_total_invested(self) -> Money:
        """Return the total amount invested (what the user paid, entry fees already included)."""
        return self.get_purchase_value()

    def _get_subscription_value_at(self, as_of_date: datetime.date) -> Money | None:
        """Return the subscription value per share at as_of_date."""
        price = self.scpi.get_share_price(as_of_date)
        return price.subscription_value if price else None

    def _get_withdrawal_value_at(self, as_of_date: datetime.date) -> Money | None:
        """Return the withdrawal value per share at as_of_date.

        Falls back to the subscription value when no withdrawal price is set.
        """
        price = self.scpi.get_share_price(as_of_date)
        if price is None:
            return None
        return price.withdrawal_value or price.subscription_value

    def get_current_full_value(self, as_of_date: datetime.date | None = None) -> Money:
        """Return the gross value of all shares at as_of_date: shares × subscription price.

        Uses the purchase price as fallback when no share price history is available.
        """
        if as_of_date is None:
            as_of_date = datetime.date.today()
        sub_value = self._get_subscription_value_at(as_of_date)
        if sub_value is None:
            return self.get_purchase_value()
        return Money(
            (self.shares_count * sub_value.amount).quantize(Decimal("0.01")),
            self.currency,
        )

    def get_estimated_value(self, as_of_date: datetime.date | None = None) -> Money:
        """Return the estimated value accounting for the ownership type.

        - Full ownership: same as get_current_full_value.
        - Bare ownership: linear revaluation from bare_ownership_ratio% → 100%
          between dismemberment_start_date and dismemberment_end_date.
          Past the end date, the value is 100% (full reconstitution).
        - Usufruct: symmetrical — starts at (100 - bare_ownership_ratio)%
          and decreases to 0% at the end date.

        Linear formula for bare ownership:
            current_pct = bare_ratio + (100 - bare_ratio) × elapsed / total_days

        This deterministic, rate-free approach matches standard notarial
        valuation tables used in French SCPI démembrement practice.
        """
        if as_of_date is None:
            as_of_date = datetime.date.today()

        full_value = self.get_current_full_value(as_of_date)

        if self.ownership_type == self.OwnershipType.FULL:
            return full_value

        if self.ownership_type in (
            self.OwnershipType.BARE,
            self.OwnershipType.USUFRUCT,
        ):
            if (
                self.dismemberment_start_date is None
                or self.dismemberment_end_date is None
                or self.bare_ownership_ratio is None
            ):
                return full_value

            bare_ratio = self.bare_ownership_ratio
            start = self.dismemberment_start_date
            end = self.dismemberment_end_date
            total_days = (end - start).days

            if total_days <= 0:
                # Degenerate case: treat as fully reconstituted
                ratio = Decimal("100")
            elif as_of_date >= end:
                ratio = Decimal("100")
            else:
                elapsed = max(0, (as_of_date - start).days)
                ratio = bare_ratio + (Decimal("100") - bare_ratio) * Decimal(
                    elapsed
                ) / Decimal(total_days)

            if self.ownership_type == self.OwnershipType.USUFRUCT:
                # Usufruct pct = 100 - bare pct
                ratio = Decimal("100") - ratio

            return Money(
                (full_value.amount * ratio / Decimal("100")).quantize(Decimal("0.01")),
                self.currency,
            )

        return full_value  # pragma: no cover

    def get_estimated_resale_value(
        self, as_of_date: datetime.date | None = None
    ) -> Money:
        """Return the estimated net resale proceeds.

        Formula: shares × withdrawal price × (1 - exit fee %) - entry fees on purchase value.

        The entry fees (sunk cost) are deducted from the gross resale to give
        the true economic recovery relative to the total amount invested.
        Uses the withdrawal value at as_of_date (falls back to subscription value
        when no separate withdrawal price is recorded).
        Uses purchase value as fallback when no share price history is available.
        """
        if as_of_date is None:
            as_of_date = datetime.date.today()

        withdrawal = self._get_withdrawal_value_at(as_of_date)
        if withdrawal is None:
            gross = self.get_purchase_value()
        else:
            gross = Money(
                (self.shares_count * withdrawal.amount).quantize(Decimal("0.01")),
                self.currency,
            )

        exit_rate = self.scpi.exit_fee_rate
        if exit_rate:
            exit_fee_amount = (gross.amount * exit_rate / Decimal("100")).quantize(
                Decimal("0.01")
            )
            gross = Money(gross.amount - exit_fee_amount, self.currency)

        # Subtract entry fees (sunk cost based on purchase value)
        entry_fees = self.get_entry_fees()
        return Money(gross.amount - entry_fees.amount, self.currency)

    def get_exit_fees(self, as_of_date: datetime.date | None = None) -> Money:
        """Return the exit fees that would be deducted at resale."""
        if as_of_date is None:
            as_of_date = datetime.date.today()
        withdrawal = self._get_withdrawal_value_at(as_of_date)
        if withdrawal is None:
            gross = self.get_purchase_value()
        else:
            gross = Money(
                (self.shares_count * withdrawal.amount).quantize(Decimal("0.01")),
                self.currency,
            )
        rate = self.scpi.exit_fee_rate
        if not rate:
            return Money(Decimal("0"), self.currency)
        return Money(
            (gross.amount * rate / Decimal("100")).quantize(Decimal("0.01")),
            self.currency,
        )

    def get_capital_gain(self, as_of_date: datetime.date | None = None) -> Money:
        """Return the latent capital gain: estimated resale value − total invested.

        A negative value indicates a latent loss.
        """
        if as_of_date is None:
            as_of_date = datetime.date.today()
        return Money(
            self.get_estimated_resale_value(as_of_date).amount
            - self.get_total_invested().amount,
            self.currency,
        )


class SCPIDividend(BaseModel):
    """A dividend payment received from a SCPI fund.

    Dividends are attached directly to the fund, not to individual investments.
    Both gross and net amounts can be stored to track withholding taxes.
    """

    class Meta:
        verbose_name = _("SCPI dividend")
        verbose_name_plural = _("SCPI dividends")
        ordering = ["-payment_date"]

    scpi = models.ForeignKey(
        SCPI,
        on_delete=models.CASCADE,
        related_name="dividends",
        verbose_name=_("SCPI"),
    )
    payment_date = models.DateField(verbose_name=_("Payment date"))
    gross_amount = MoneyField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Gross amount"),
        help_text=_("Gross dividend before any withholding tax."),
    )
    net_amount = MoneyField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("Net amount"),
        help_text=_("Net dividend received after withholding tax."),
    )
    notes = models.TextField(blank=True, default="")

    def __str__(self) -> str:
        return f"{self.scpi} — {self.payment_date} — {self.net_amount}"
