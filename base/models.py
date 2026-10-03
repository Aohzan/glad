"""General models for the application."""

from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _


class BaseModel(models.Model):
    """Base model with common fields."""

    id = models.AutoField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta options for the base model."""

        abstract = True


class EconomicIndex(models.TextChoices):
    """Official French indices published by INSEE."""

    IRL = "irl", _("Rent reference index (IRL)")
    CPI = "cpi", _("Consumer price index")


class EconomicIndexValue(BaseModel):
    """One published value of an economic index for a period (quarter or month)."""

    class Meta:
        verbose_name = _("economic index value")
        verbose_name_plural = _("economic index values")
        ordering = ["index", "-period"]
        constraints = [
            models.UniqueConstraint(
                fields=["index", "period"], name="unique_economic_index_period"
            ),
        ]

    index = models.CharField(max_length=10, choices=EconomicIndex.choices)
    #: First day of the quarter (IRL) or of the month (CPI).
    period = models.DateField()
    value = models.DecimalField(max_digits=10, decimal_places=3)
    published_on = models.DateField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{EconomicIndex(self.index).label} {self.period_label}: {self.value}"

    @property
    def quarter(self) -> int:
        """Quarter (1–4) of the period."""
        return (self.period.month - 1) // 3 + 1

    @property
    def period_label(self) -> str:
        """``Q2 2026`` for a quarterly index, ``2026-08`` for a monthly one."""
        if self.index == EconomicIndex.IRL:
            return gettext("Q{quarter} {year}").format(
                quarter=self.quarter, year=self.period.year
            )
        return self.period.strftime("%Y-%m")


class NetWorthSnapshot(BaseModel):
    """Net worth at the start of a past month, stored to draw the history quickly.

    Snapshots are derived data: they are deleted whenever a value they depend
    on changes and recomputed on the next request.
    """

    class Meta:
        verbose_name = _("net worth snapshot")
        verbose_name_plural = _("net worth snapshots")
        ordering = ["-month"]
        constraints = [
            models.UniqueConstraint(
                fields=["month", "currency"], name="unique_net_worth_snapshot"
            ),
        ]

    month = models.DateField()
    currency = models.CharField(max_length=3)
    savings = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    investments = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    properties_net = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    properties_gross = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    scpi = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    other = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    def __str__(self) -> str:
        return f"{self.month:%Y-%m} {self.currency}: {self.total}"

    @property
    def total(self):
        """Net worth of the month."""
        return (
            self.savings
            + self.investments
            + self.properties_net
            + self.scpi
            + self.other
        )


def display_name(user) -> str:
    """Full name of a user, or the username when the name is empty."""
    return user.get_full_name() or user.get_username()


def household_members():
    """Users who can own assets: the active users, adults first then children."""
    return (
        get_user_model()
        .objects.filter(is_active=True)
        .select_related("profile")
        .order_by("profile__is_child", "pk")
    )


class Ownership(BaseModel):
    """Share of an asset held by a household member (a Django user, adult or child).

    Any asset model can be owned (saving and investment accounts, properties,
    SCPI investments, other assets) through a generic relation. An asset
    without ownership row is considered held by the whole household.
    """

    class Right(models.TextChoices):
        FULL = "full", _("Full ownership")
        BARE = "bare", _("Bare ownership (nue-propriété)")
        USUFRUCT = "usufruct", _("Usufruct (usufruit)")

    class Meta:
        verbose_name = _("ownership")
        verbose_name_plural = _("ownerships")
        ordering = ["content_type", "object_id", "-share"]
        constraints = [
            models.UniqueConstraint(
                fields=["content_type", "object_id", "user"],
                name="unique_ownership_per_user",
            ),
        ]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    asset = GenericForeignKey("content_type", "object_id")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ownerships",
        verbose_name=_("Owner"),
    )
    share = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal(100),
        validators=[MinValueValidator(Decimal("0.01")), MaxValueValidator(100)],
        verbose_name=_("Share (%)"),
        help_text=_("Part of the asset held, e.g. 50 for a couple in indivision."),
    )
    right = models.CharField(
        max_length=10,
        choices=Right.choices,
        default=Right.FULL,
        verbose_name=_("Right"),
    )
    usufructuary_birth_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Usufructuary birth date"),
        help_text=_("For a life usufruct, valued with the scale of article 669 CGI."),
    )
    usufruct_end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Usufruct end date"),
        help_text=_("For a temporary usufruct: 23 % per period of ten years."),
    )

    def __str__(self) -> str:
        right = Ownership.Right(self.right).label
        return f"{self.user} {self.share}% {right} ({self.asset})"
