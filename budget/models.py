"""Yearly budget of the household: categories, years and budget lines.

Every amount is entered for a whole calendar year; the pages divide it by 12
to show the monthly equivalent. The property and finance flows of the year are
not stored here: they are read from the ledger, the loan schedules and the
deposits of the accounts each time a budget is shown.
"""

from decimal import Decimal
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from djmoney.models.fields import MoneyField

from base.models import BaseModel

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager

#: Longest label of a budget line.
LABEL_MAX_LENGTH = 200
#: Longest name of a budget category.
CATEGORY_NAME_MAX_LENGTH = 100


class BudgetKind(models.TextChoices):
    """Side of the budget a category belongs to."""

    INCOME = "income", pgettext_lazy("budget", "Income")
    EXPENSE = "expense", pgettext_lazy("budget", "Expenses")
    SAVING = "saving", pgettext_lazy("budget", "Savings")


class BudgetCategory(BaseModel):
    """A node of the category tree shared by every budget year.

    A child category has the kind of its parent; the tree is at most
    MAX_DEPTH levels deep so the sankey diagram stays readable.
    """

    MAX_DEPTH = 3

    if TYPE_CHECKING:
        parent_id: int | None
        children: RelatedManager[BudgetCategory]
        lines: RelatedManager[BudgetLine]

    class Meta:
        verbose_name = _("budget category")
        verbose_name_plural = _("budget categories")
        ordering = ["kind", "position", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "name"], name="unique_budget_category_name"
            ),
            models.UniqueConstraint(
                fields=["kind", "name"],
                condition=Q(parent__isnull=True),
                name="unique_budget_root_category_name",
            ),
        ]

    name = models.CharField(max_length=CATEGORY_NAME_MAX_LENGTH, verbose_name=_("Name"))
    kind = models.CharField(
        max_length=10,
        choices=BudgetKind.choices,
        default=BudgetKind.EXPENSE,
        verbose_name=_("Kind"),
        help_text=_("A sub-category takes the kind of its parent."),
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
        verbose_name=_("Parent category"),
    )
    position = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_("Position"),
        help_text=_("Order among the categories of the same level."),
    )
    counts_as_debt = models.BooleanField(
        default=False,
        verbose_name=_("Loan repayments"),
        help_text=_(
            "Lines of this category are loan installments (car, consumer credit) "
            "counted in the debt ratio."
        ),
    )

    def __str__(self) -> str:
        return self.path

    def ancestors(self) -> list[BudgetCategory]:
        """Parent categories, from the root down to the direct parent."""
        chain = []
        node = self.parent
        while node is not None and node not in chain:
            chain.insert(0, node)
            node = node.parent
        return chain

    @property
    def depth(self) -> int:
        """1 for a root category, 2 for its children…"""
        return len(self.ancestors()) + 1

    @property
    def path(self) -> str:
        """Names from the root, e.g. ``Transport > Fuel``."""
        return " > ".join(c.name for c in [*self.ancestors(), self])

    def descendant_ids(self) -> list[int]:
        """Primary keys of every category below this one."""
        if self.pk is None:
            return []
        ids: list[int] = []
        level = [self.pk]
        while level:
            level = list(
                BudgetCategory.objects.filter(parent__in=level)
                .exclude(pk__in=ids)
                .values_list("pk", flat=True)
            )
            ids.extend(level)
        return ids

    def _subtree_height(self) -> int:
        """Levels of the tree below this category (0 without children)."""
        if self.pk is None:
            return 0
        height = 0
        level = [self.pk]
        while level:
            level = list(
                BudgetCategory.objects.filter(parent__in=level).values_list(
                    "pk", flat=True
                )
            )
            if level:
                height += 1
        return height

    def clean(self) -> None:
        super().clean()
        if self.parent is None:
            return
        if self.pk is not None and (
            self.parent.pk == self.pk
            or self.parent.pk in self.descendant_ids()
            or any(a.pk == self.pk for a in self.parent.ancestors())
        ):
            raise ValidationError(
                {"parent": _("A category cannot be placed under itself.")}
            )
        self.kind = self.parent.kind
        if self.parent.depth + 1 + self._subtree_height() > self.MAX_DEPTH:
            raise ValidationError(
                {
                    "parent": _("Categories are limited to %(depth)d levels.")
                    % {"depth": self.MAX_DEPTH}
                }
            )

    def save(self, *args, **kwargs) -> None:
        """Save, then give the kind of the category to its sub-categories."""
        super().save(*args, **kwargs)
        descendants = self.descendant_ids()
        if descendants:
            BudgetCategory.objects.filter(pk__in=descendants).exclude(
                kind=self.kind
            ).update(kind=self.kind)


class BudgetYear(BaseModel):
    """The budget of one calendar year."""

    if TYPE_CHECKING:
        lines: RelatedManager[BudgetLine]

    class Meta:
        verbose_name = _("budget year")
        verbose_name_plural = _("budget years")
        ordering = ["-year"]

    year = models.PositiveSmallIntegerField(
        unique=True,
        validators=[MinValueValidator(1900), MaxValueValidator(2200)],
        verbose_name=_("Year"),
    )
    notes = models.TextField(blank=True, default="", verbose_name=_("Notes"))
    include_properties = models.BooleanField(
        default=True,
        verbose_name=_("Include the properties"),
        help_text=_(
            "Add the rents, charges and loan installments of the properties, "
            "and the SCPI dividends and subscriptions of the year."
        ),
    )
    include_finance = models.BooleanField(
        default=True,
        verbose_name=_("Include the account deposits"),
        help_text=_(
            "Add the deposits and withdrawals of the saving and investment "
            "accounts as savings."
        ),
    )
    excluded_properties = models.ManyToManyField(
        "property.Property",
        blank=True,
        related_name="+",
        verbose_name=_("Excluded properties"),
        help_text=_("Properties whose flows are left out of this budget."),
    )

    def __str__(self) -> str:
        return str(self.year)


class BudgetLine(BaseModel):
    """An income, expense or savings amount of a budget year."""

    class Meta:
        verbose_name = _("budget line")
        verbose_name_plural = _("budget lines")
        ordering = ["budget_year", "category", "label"]

    budget_year = models.ForeignKey(
        BudgetYear,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("Year"),
    )
    category = models.ForeignKey(
        BudgetCategory,
        on_delete=models.PROTECT,
        related_name="lines",
        verbose_name=_("Category"),
    )
    label = models.CharField(max_length=LABEL_MAX_LENGTH, verbose_name=_("Label"))
    amount = MoneyField(
        max_digits=14,
        decimal_places=2,
        default_currency=settings.DEFAULT_CURRENCY,
        verbose_name=_("Yearly amount"),
        help_text=_("Total for the whole year."),
    )
    person = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="budget_lines",
        verbose_name=_("Person"),
        help_text=_("Leave empty for the whole household."),
    )
    notes = models.TextField(blank=True, default="", verbose_name=_("Notes"))

    def __str__(self) -> str:
        return f"{self.budget_year} - {self.label}"

    @property
    def kind(self) -> str:
        """Kind of the category of the line."""
        return self.category.kind

    @property
    def monthly_amount(self) -> Decimal:
        """Yearly amount divided by 12."""
        return self.amount.amount / 12

    def clean(self) -> None:
        super().clean()
        if self.amount is not None and self.amount.amount < 0:
            raise ValidationError({"amount": _("The amount cannot be negative.")})
