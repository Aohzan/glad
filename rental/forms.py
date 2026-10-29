"""Forms of the rental app."""

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _

from base.models import Document

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
