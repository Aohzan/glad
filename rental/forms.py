"""Forms of the rental app."""

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _

from base.models import Document
from rental import rules
from rental.models import Inventory, InventoryItem, RentalApplication

#: Kinds of document offered on a lease; diagnostics go to the property.
LEASE_DOCUMENT_KINDS = [
    Document.Kind.LEASE,
    Document.Kind.INVENTORY,
    Document.Kind.INSURANCE,
    Document.Kind.GUARANTEE,
    Document.Kind.DIAGNOSTIC,
    Document.Kind.IDENTITY,
    Document.Kind.INCOME,
    Document.Kind.LETTER,
    Document.Kind.OTHER,
]
#: Kinds of document of a rental application.
APPLICATION_DOCUMENT_KINDS = [
    Document.Kind.IDENTITY,
    Document.Kind.INCOME,
    Document.Kind.GUARANTEE,
    Document.Kind.OTHER,
]


class DocumentUploadForm(forms.Form):
    """Upload of a document to a lease, or to its property for a diagnostic."""

    file = forms.FileField(
        label=_("File"),
        widget=forms.ClearableFileInput(
            attrs={"accept": ".pdf,.jpg,.jpeg,.png,.webp,.heic,.heif"}
        ),
    )
    kind = forms.ChoiceField(
        label=_("Type"),
        choices=[(kind.value, kind.label) for kind in LEASE_DOCUMENT_KINDS],
    )
    title = forms.CharField(
        label=_("Title"),
        max_length=200,
        required=False,
        help_text=_("Defaults to the file name."),
    )
    valid_until = forms.DateField(
        label=_("Valid until"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text=_("For an insurance certificate or a diagnostic."),
    )

    def __init__(self, *args, kinds=LEASE_DOCUMENT_KINDS, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["kind"]
        assert isinstance(field, forms.ChoiceField)
        field.choices = [(kind.value, kind.label) for kind in kinds]


class EmailListField(forms.CharField):
    """Email addresses separated by commas."""

    def to_python(self, value) -> list[str]:  # ty: ignore[invalid-method-override]
        text = super().to_python(value) or ""
        return [
            part.strip() for part in text.replace(";", ",").split(",") if part.strip()
        ]

    def validate(self, value) -> None:
        if self.required and not value:
            raise ValidationError(self.error_messages["required"], code="required")
        for address in value:
            validate_email(address)


class LeaseEmailForm(forms.Form):
    """An email to the tenants, checked and edited before it is sent."""

    to = EmailListField(label=_("To"), help_text=_("Addresses separated by commas."))
    cc = EmailListField(label=_("Copy"), required=False)
    subject = forms.CharField(label=_("Subject"), max_length=200)
    body = forms.CharField(
        label=_("Message"), widget=forms.Textarea(attrs={"rows": 16})
    )


class RentalApplicationForm(forms.ModelForm):
    class Meta:
        model = RentalApplication
        fields = [
            "property",
            "first_name",
            "last_name",
            "email",
            "phone",
            "monthly_income",
            "rent_amount",
            "guarantor_name",
            "guarantee_type",
            "guarantor_income",
            "notes",
        ]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["property"]
        assert isinstance(field, forms.ModelChoiceField)
        field.queryset = field.queryset.filter(is_active=True).order_by("name")  # ty: ignore[unresolved-attribute]


class InventoryForm(forms.ModelForm):
    """Date, meters, keys and comment of an inventory."""

    class Meta:
        model = Inventory
        fields = ["date", "keys", "comment"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "keys": forms.Textarea(attrs={"rows": 2}),
            "comment": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        meters = self.instance.meters or {}
        for key, label in rules.METERS:
            self.fields[f"meter_{key}"] = forms.CharField(
                label=label, required=False, max_length=50, initial=meters.get(key, "")
            )

    def save(self, commit=True):
        self.instance.meters = {
            key: self.cleaned_data[f"meter_{key}"]
            for key, _label in rules.METERS
            if self.cleaned_data[f"meter_{key}"]
        }
        return super().save(commit)


class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = ["condition", "comment"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["condition"]
        assert isinstance(field, forms.ChoiceField)
        field.choices = [("", _("Condition…")), *InventoryItem.Condition.choices]


InventoryItemFormSet = forms.modelformset_factory(
    InventoryItem, form=InventoryItemForm, extra=0
)


class NameForm(forms.Form):
    """Name of a new room or element of an inventory."""

    name = forms.CharField(label=_("Name"), max_length=100)
