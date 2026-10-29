"""Models of the rental management."""

import builtins
from decimal import Decimal

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _
from djmoney.models.fields import MoneyField

from base.models import BaseModel

#: Alias kept usable in the models whose ``property`` field shadows the builtin.
_property = builtins.property


class RentReceipt(BaseModel):
    """Receipt of the rent of a period: a quittance once the rent is fully paid.

    The law only allows a quittance for a full payment; a partial payment gets a
    receipt that does not discharge the tenant (art. 21, loi du 6 juillet 1989).
    """

    class Meta:
        verbose_name = _("rent receipt")
        verbose_name_plural = _("rent receipts")
        ordering = ["-period_start"]
        constraints = [
            models.UniqueConstraint(
                fields=["lease", "period_start"], name="unique_receipt_per_period"
            )
        ]

    lease = models.ForeignKey(
        "property.Lease",
        on_delete=models.CASCADE,
        related_name="receipts",
        verbose_name=_("Lease"),
    )
    period_start = models.DateField(verbose_name=_("Start of the period"))
    period_end = models.DateField(verbose_name=_("End of the period"))
    rent = MoneyField(max_digits=10, decimal_places=2, verbose_name=_("Rent"))
    charges = MoneyField(max_digits=10, decimal_places=2, verbose_name=_("Charges"))
    paid_amount = MoneyField(
        max_digits=10, decimal_places=2, verbose_name=_("Amount paid")
    )
    paid_date = models.DateField(null=True, blank=True, verbose_name=_("Paid on"))
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Sent on"))

    def __str__(self) -> str:
        return f"{self.number} — {self.lease}"

    @property
    def number(self) -> str:
        return f"{self.period_start:%Y-%m}"

    @property
    def total(self):
        return self.rent + self.charges

    @property
    def is_full(self) -> bool:
        """A quittance when the whole rent is paid, else a receipt."""
        return self.paid_amount.amount >= self.total.amount

    @property
    def filename(self) -> str:
        prefix = "quittance" if self.is_full else "recu"
        return f"{prefix}-{self.number}.pdf"


class RentalApplication(BaseModel):
    """A candidate for a property, with the documents of the application."""

    class Status(models.TextChoices):
        NEW = "new", _("New")
        REVIEWING = "reviewing", _("Under review")
        ACCEPTED = "accepted", _("Accepted")
        REJECTED = "rejected", _("Rejected")

    #: Statuses of an application still to decide on.
    OPEN_STATUSES = (Status.NEW, Status.REVIEWING)

    class Meta:
        verbose_name = _("rental application")
        verbose_name_plural = _("rental applications")
        ordering = ["-created_at", "-pk"]

    property = models.ForeignKey(
        "property.Property",
        on_delete=models.CASCADE,
        related_name="applications",
        verbose_name=_("Property"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        verbose_name=_("Status"),
    )
    first_name = models.CharField(
        max_length=100, blank=True, verbose_name=_("First name")
    )
    last_name = models.CharField(max_length=100, verbose_name=_("Last name"))
    email = models.EmailField(blank=True, verbose_name=_("Email"))
    phone = models.CharField(max_length=30, blank=True, verbose_name=_("Phone"))
    monthly_income = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Monthly net income"),
        help_text=_("Of every tenant of the application, together."),
    )
    rent_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Rent and charges"),
        help_text=_("Monthly rent and charges offered to the candidate."),
    )
    guarantor_name = models.CharField(
        max_length=200, blank=True, verbose_name=_("Guarantor")
    )
    guarantee_type = models.CharField(
        max_length=20,
        choices=[
            ("joint", _("Joint and several guarantee")),
            ("visale", _("Visale")),
            ("other", _("Other guarantee")),
        ],
        blank=True,
        verbose_name=_("Guarantee"),
    )
    guarantor_income = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Monthly net income of the guarantor"),
    )
    notes = models.TextField(blank=True, verbose_name=_("Notes"))
    lease = models.ForeignKey(
        "property.Lease",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Lease"),
    )

    def __str__(self) -> str:
        return self.name

    @_property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @_property
    def is_open(self) -> bool:
        return self.status in self.OPEN_STATUSES

    @_property
    def effort_rate(self):
        """Share of the income spent on the rent, in %, None when unknown."""
        if not self.monthly_income or not self.rent_amount:
            return None
        return (self.rent_amount * 100 / self.monthly_income).quantize(Decimal("0.1"))


class Inventory(BaseModel):
    """Inventory of fixtures (état des lieux) at the entry or the exit."""

    class Kind(models.TextChoices):
        ENTRY = "entry", _("Entry")
        EXIT = "exit", _("Exit")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        SIGNED = "signed", _("Signed")

    class Meta:
        verbose_name = _("inventory of fixtures")
        verbose_name_plural = _("inventories of fixtures")
        ordering = ["lease", "kind"]
        constraints = [
            models.UniqueConstraint(
                fields=["lease", "kind"], name="unique_inventory_per_kind"
            )
        ]

    lease = models.ForeignKey(
        "property.Lease",
        on_delete=models.CASCADE,
        related_name="inventories",
        verbose_name=_("Lease"),
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, verbose_name=_("Type"))
    date = models.DateField(verbose_name=_("Date"))
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name=_("Status"),
    )
    meters = models.JSONField(default=dict, blank=True, verbose_name=_("Meters"))
    keys = models.TextField(
        blank=True,
        verbose_name=_("Keys"),
        help_text=_("Keys and badges handed over, e.g. 2 door keys, 1 mailbox key."),
    )
    comment = models.TextField(blank=True, verbose_name=_("Comment"))

    def __str__(self) -> str:
        return f"{self.get_kind_display()} — {self.lease}"  # ty: ignore[unresolved-attribute]


class InventoryRoom(BaseModel):
    inventory = models.ForeignKey(
        Inventory, on_delete=models.CASCADE, related_name="rooms"
    )
    name = models.CharField(max_length=100, verbose_name=_("Room"))
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = _("room")
        verbose_name_plural = _("rooms")
        ordering = ["position", "pk"]

    def __str__(self) -> str:
        return self.name


class InventoryItem(BaseModel):
    """An element of a room (walls, floor, oven…) and its condition."""

    class Condition(models.TextChoices):
        NEW = "new", _("New")
        GOOD = "good", _("Good")
        WORN = "worn", _("Worn")
        POOR = "poor", _("Poor")
        DAMAGED = "damaged", _("Damaged")

    room = models.ForeignKey(
        InventoryRoom, on_delete=models.CASCADE, related_name="items"
    )
    name = models.CharField(max_length=100, verbose_name=_("Element"))
    condition = models.CharField(
        max_length=10,
        choices=Condition.choices,
        blank=True,
        verbose_name=_("Condition"),
    )
    comment = models.CharField(max_length=500, blank=True, verbose_name=_("Comment"))

    class Meta:
        verbose_name = _("inventory element")
        verbose_name_plural = _("inventory elements")
        ordering = ["pk"]

    def __str__(self) -> str:
        return self.name


class SignatureRequest(BaseModel):
    """A document sent for electronic signature to the landlord and the tenants."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Waiting for the signatures")
        COMPLETED = "completed", _("Signed")
        REJECTED = "rejected", _("Rejected")

    class Meta:
        verbose_name = _("signature request")
        verbose_name_plural = _("signature requests")
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    #: The lease or the inventory being signed.
    target = GenericForeignKey("content_type", "object_id")
    title = models.CharField(max_length=200)
    provider = models.CharField(max_length=20, default="documenso")
    external_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    #: [{"name", "email", "status", "signed_at"}] as reported by the provider.
    signers = models.JSONField(default=list)
    error = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    signed_document = models.ForeignKey(
        "base.Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    def __str__(self) -> str:
        return self.title


class ChargesReconciliation(BaseModel):
    """Yearly reconciliation of the charges provisions with the actual expenses.

    The recoverable expenses of the property are kept as computed when the
    reconciliation was made (``expenses``), with the manual adjustments
    (``adjustments``), so that the statement sent stays as it was.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        SENT = "sent", _("Sent")

    class Meta:
        verbose_name = _("charges reconciliation")
        verbose_name_plural = _("charges reconciliations")
        ordering = ["-period_end", "-pk"]

    lease = models.ForeignKey(
        "property.Lease",
        on_delete=models.CASCADE,
        related_name="charges_reconciliations",
        verbose_name=_("Lease"),
    )
    period_start = models.DateField(verbose_name=_("Start of the period"))
    period_end = models.DateField(verbose_name=_("End of the period"))
    provisions = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0),
        verbose_name=_("Provisions paid"),
    )
    #: [{"label", "date", "amount", "share"}]: the tenant pays ``share``.
    expenses = models.JSONField(default=list, blank=True)
    #: [{"label", "amount"}], negative to deduct.
    adjustments = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    ledger_entry = models.ForeignKey(
        "property.PropertyLedgerEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    def __str__(self) -> str:
        return f"{self.period_start} → {self.period_end} — {self.lease}"

    @_property
    def actual(self) -> Decimal:
        """Charges actually due by the tenant over the period."""
        return sum(
            (Decimal(str(line["share"])) for line in self.expenses), Decimal(0)
        ) + sum((Decimal(str(line["amount"])) for line in self.adjustments), Decimal(0))

    @_property
    def balance(self) -> Decimal:
        """Owed by the tenant when positive, to refund when negative."""
        return self.actual - self.provisions
