"""Frozen LMNP declarations (snapshots of the liasse fiscale for one year)."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from base.models import BaseModel


class LmnpDeclarationSnapshot(BaseModel):
    """A frozen copy of the LMNP liasse fiscale computed for one fiscal year.

    The ledger keeps moving after a declaration has been filed; freezing the
    computed figures keeps a faithful record of what was declared. The PDF is
    regenerated on demand from ``data`` so nothing but JSON is stored.
    """

    class Meta:
        verbose_name = _("LMNP declaration snapshot")
        verbose_name_plural = _("LMNP declaration snapshots")
        ordering = ["-fiscal_year", "-created_at"]

    fiscal_year = models.PositiveSmallIntegerField(
        db_index=True, verbose_name=_("Fiscal year")
    )
    rules_version = models.CharField(
        max_length=8,
        verbose_name=_("Rules version"),
        help_text=_("Year of the tax rule set used for the computation."),
    )
    properties = models.ManyToManyField(
        "property.Property",
        related_name="lmnp_snapshots",
        verbose_name=_("Properties"),
    )
    property_names = models.JSONField(
        default=list,
        verbose_name=_("Property names"),
        help_text=_("Names of the properties at the time of the snapshot."),
    )
    data = models.JSONField(verbose_name=_("Frozen data"))
    notes = models.TextField(blank=True, default="", verbose_name=_("Notes"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lmnp_snapshots",
        verbose_name=_("Created by"),
    )

    def __str__(self) -> str:
        return f"LMNP {self.fiscal_year} — {', '.join(self.property_names)}"
