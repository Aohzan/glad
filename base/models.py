"""General models for the application."""

import datetime
import uuid
from decimal import Decimal
from pathlib import Path

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

    def latest_related(self, relation: str, date_field: str, day: datetime.date):
        """Latest object of *relation* whose *date_field* is on or before *day*.

        Reads the objects loaded by ``prefetch_related(relation)`` when there are
        some, so a value computed month by month runs no query; queries the
        latest one otherwise. None when there is none.
        """
        manager = getattr(self, relation)
        if relation in getattr(self, "_prefetched_objects_cache", {}):
            return max(
                (o for o in manager.all() if getattr(o, date_field) <= day),
                key=lambda o: getattr(o, date_field),
                default=None,
            )
        return (
            manager.filter(**{f"{date_field}__lte": day})
            .order_by(f"-{date_field}")
            .first()
        )


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
    """First name of a user, or the username when it is empty."""
    return user.first_name.strip() or user.get_username()


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


class ScheduledJob(models.Model):
    """Run state of a periodic job declared in ``base.scheduler``.

    ``last_enqueued_at`` doubles as a lock: the scheduler claims a run with a
    conditional update on its previous value, so two schedulers never enqueue
    the same run twice.
    """

    class Status(models.TextChoices):
        ENQUEUED = "enqueued", _("Enqueued")
        RUNNING = "running", _("Running")
        SUCCESS = "success", _("Succeeded")
        FAILED = "failed", _("Failed")

    class Meta:
        verbose_name = _("scheduled job")
        verbose_name_plural = _("scheduled jobs")
        ordering = ["name"]

    name = models.CharField(max_length=64, unique=True)
    last_enqueued_at = models.DateTimeField(null=True, blank=True)
    last_started_at = models.DateTimeField(null=True, blank=True)
    last_finished_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=10, choices=Status.choices, blank=True)
    last_message = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.name


def document_upload_to(instance: Document, filename: str) -> str:
    """Store uploads under a random name: the original one is kept in the row."""
    suffix = Path(filename).suffix.lower()
    today = datetime.date.today()
    return f"documents/{today:%Y/%m}/{uuid.uuid4().hex}{suffix}"


class Document(BaseModel):
    """File attached to any object (lease, tenant application, inventory…)."""

    class Kind(models.TextChoices):
        LEASE = "lease", _("Lease")
        INVENTORY = "inventory", _("Inventory of fixtures")
        DIAGNOSTIC = "diagnostic", _("Diagnostic")
        INSURANCE = "insurance", _("Insurance certificate")
        IDENTITY = "identity", _("Identity document")
        INCOME = "income", _("Proof of income")
        GUARANTEE = "guarantee", _("Guarantee")
        RECEIPT = "receipt", _("Rent receipt")
        STATEMENT = "statement", _("Statement")
        LETTER = "letter", _("Letter")
        PHOTO = "photo", _("Photo")
        OTHER = "other", _("Other")

    class Meta:
        verbose_name = _("document")
        verbose_name_plural = _("documents")
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    kind = models.CharField(
        max_length=20, choices=Kind.choices, default=Kind.OTHER, verbose_name=_("Type")
    )
    title = models.CharField(max_length=200, verbose_name=_("Title"))
    file = models.FileField(upload_to=document_upload_to, verbose_name=_("File"))
    original_name = models.CharField(max_length=255, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    valid_until = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Valid until"),
        help_text=_("For a certificate or a diagnostic that expires."),
    )
    notes = models.TextField(blank=True, verbose_name=_("Notes"))
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    def __str__(self) -> str:
        return self.title

    @property
    def is_image(self) -> bool:
        return self.mime_type.startswith("image/")

    @property
    def is_expired(self) -> bool:
        return self.valid_until is not None and self.valid_until < datetime.date.today()


class SentEmail(BaseModel):
    """Email sent from the application, kept as a record of what was sent."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        SENT = "sent", _("Sent")
        FAILED = "failed", _("Failed")

    class Meta:
        verbose_name = _("sent email")
        verbose_name_plural = _("sent emails")
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )
    object_id = models.PositiveBigIntegerField(null=True, blank=True)
    related = GenericForeignKey("content_type", "object_id")
    kind = models.CharField(max_length=40, blank=True)
    #: What the email is about within its kind, e.g. the period of a rent call.
    reference = models.CharField(max_length=40, blank=True)
    to = models.JSONField(default=list)
    cc = models.JSONField(default=list, blank=True)
    reply_to = models.EmailField(blank=True)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    attachments = models.ManyToManyField(Document, blank=True, related_name="emails")
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    error = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    def __str__(self) -> str:
        return self.subject
