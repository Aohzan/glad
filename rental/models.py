"""Models of the rental management."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from djmoney.models.fields import MoneyField

from base.models import BaseModel


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
