"""Forms for the finance app."""

from django import forms


class IndexForm(forms.Form):
    """Form for the finance index view."""

    days = forms.IntegerField(
        label="Days",
        initial=30,
        min_value=1,
        help_text="Number of days for progression calculation.",
    )
