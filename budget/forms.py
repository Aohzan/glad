"""Forms of the budget pages."""

from collections.abc import Collection
from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _

from base.forms import MoneyInputGroupMixin, UserChoiceField
from base.models import display_name, household_members
from budget.models import BudgetCategory, BudgetKind, BudgetLine, BudgetYear
from budget.services.categories import category_tree

#: Largest file accepted by the CSV import (1 MB).
MAX_IMPORT_SIZE = 1024 * 1024


class CategoryChoiceField(forms.ModelChoiceField):
    """Categories in tree order, indented by level and grouped by kind."""

    #: Indentation of a sub-category in the list (non-breaking spaces).
    INDENT = "\u00a0" * 3

    def __init__(self, *, exclude: Collection[int] = (), **kwargs):
        nodes = [n for n in category_tree() if n.category.pk not in exclude]
        super().__init__(
            queryset=BudgetCategory.objects.filter(
                pk__in=[n.category.pk for n in nodes]
            ),
            **kwargs,
        )
        groups = [
            (
                label,
                [
                    (n.category.pk, f"{self.INDENT * (n.depth - 1)}{n.category.name}")
                    for n in nodes
                    if n.category.kind == kind
                ],
            )
            for kind, label in BudgetKind.choices
        ]
        empty = [("", self.empty_label)] if self.empty_label is not None else []
        self.choices = empty + [group for group in groups if group[1]]


class BudgetYearForm(forms.ModelForm):
    """Year, settings and notes of a budget."""

    class Meta:
        model = BudgetYear
        fields = [
            "year",
            "include_properties",
            "include_finance",
            "excluded_properties",
            "notes",
        ]
        widgets = {
            "excluded_properties": forms.CheckboxSelectMultiple,
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class BudgetLineForm(MoneyInputGroupMixin, forms.ModelForm):
    """A line of a budget."""

    class Meta:
        model = BudgetLine
        fields = ["category", "label", "amount", "person", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"] = CategoryChoiceField(
            label=_("Category"), empty_label=None
        )
        self.fields["person"] = UserChoiceField(
            queryset=household_members(),
            required=False,
            label=_("Person"),
            empty_label=str(_("Whole household")),
            help_text=_(
                "Shared lines are split between the adults in a person's view."
            ),
        )
        amount = self.fields["amount"]
        amount.widget.widgets[0].attrs.update({"min": "0", "step": "0.01"})


class BudgetCategoryForm(forms.ModelForm):
    """A category of the tree."""

    class Meta:
        model = BudgetCategory
        fields = ["name", "parent", "kind", "position", "counts_as_debt"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = self.instance
        exclude = set()
        if instance.pk:
            exclude = {instance.pk, *instance.descendant_ids()}
        self.fields["parent"] = CategoryChoiceField(
            label=_("Parent category"),
            required=False,
            empty_label=str(_("None (top level)")),
            exclude=exclude,
        )
        self.fields["parent"].initial = instance.parent_id


class BudgetCopyForm(forms.Form):
    """Year and revaluation of a copied budget."""

    year = forms.IntegerField(label=_("Year"), min_value=1900, max_value=2200)
    revaluation = forms.DecimalField(
        label=_("Revaluation (%)"),
        max_digits=5,
        decimal_places=1,
        min_value=Decimal(-50),
        max_value=Decimal(100),
        initial=Decimal(0),
        help_text=_(
            "Raise every amount by this percentage, e.g. the inflation of the year."
        ),
    )

    def clean_year(self) -> int:
        year = self.cleaned_data["year"]
        if BudgetYear.objects.filter(year=year).exists():
            raise forms.ValidationError(_("A budget already exists for this year."))
        return year


class BudgetImportForm(forms.Form):
    """CSV file of budget lines."""

    csv_file = forms.FileField(
        label=_("CSV file"),
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,text/csv"}),
    )
    create_missing = forms.BooleanField(
        label=_("Create the missing categories"),
        required=False,
        initial=True,
    )

    def clean_csv_file(self):
        csv_file = self.cleaned_data["csv_file"]
        if csv_file.size > MAX_IMPORT_SIZE:
            raise forms.ValidationError(_("The file must not exceed 1 MB."))
        return csv_file


class PersonFilterForm(forms.Form):
    """Whole household or one of its members."""

    person = forms.TypedChoiceField(
        label=_("View"),
        required=False,
        coerce=int,
        empty_value=None,
        widget=forms.Select(attrs={"data-submit-on-change": ""}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.members = {user.pk: user for user in household_members()}
        self.fields["person"].choices = [("", _("Whole household"))] + [  # ty: ignore[unresolved-attribute]
            (pk, display_name(user)) for pk, user in self.members.items()
        ]

    def selected(self):
        """The chosen member, None for the whole household."""
        if not self.is_valid():
            return None
        return self.members.get(self.cleaned_data["person"])
