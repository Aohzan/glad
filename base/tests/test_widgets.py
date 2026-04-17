"""Tests for base widgets and form mixins."""

import pytest
from django import forms
from djmoney.forms.fields import MoneyField
from djmoney.forms.widgets import MoneyWidget
from moneyed import EUR, Money

from base.forms import MoneyInputGroupMixin
from base.widgets import BootstrapMoneyWidget


# ─── BootstrapMoneyWidget ─────────────────────────────────────────────────────


class TestBootstrapMoneyWidget:
    def test_is_subclass_of_money_widget(self):
        assert issubclass(BootstrapMoneyWidget, MoneyWidget)

    def test_render_wraps_in_input_group_div(self):
        widget = BootstrapMoneyWidget(default_currency="EUR")
        html = widget.render("price", Money(10, EUR))
        assert html.startswith('<div class="input-group">')
        assert html.endswith("</div>")

    def test_render_contains_amount_input(self):
        widget = BootstrapMoneyWidget(default_currency="EUR")
        html = widget.render("price", Money(42, EUR))
        assert 'name="price_0"' in html
        assert 'value="42"' in html

    def test_render_contains_currency_select(self):
        widget = BootstrapMoneyWidget(default_currency="EUR")
        html = widget.render("price", Money(42, EUR))
        assert 'name="price_1"' in html
        assert "<select" in html

    def test_render_with_none_value_uses_default_currency(self):
        widget = BootstrapMoneyWidget(default_currency="EUR")
        html = widget.render("price", None)
        assert '<div class="input-group">' in html
        # Currency select should still be present
        assert "<select" in html

    def test_render_preserves_custom_amount_attrs(self):
        from django.forms import NumberInput

        amount_widget = NumberInput(attrs={"class": "form-control", "step": "0.01"})
        widget = BootstrapMoneyWidget(
            amount_widget=amount_widget,  # type: ignore[arg-type]
            default_currency="EUR",
        )
        html = widget.render("price", Money(10, EUR))
        assert "form-control" in html
        assert 'step="0.01"' in html

    def test_render_constrains_currency_select_width(self):
        widget = BootstrapMoneyWidget(default_currency="EUR")
        html = widget.render("price", Money(10, EUR))
        assert "width: 150px" in html
        assert "flex: 0 0 150px" in html

    def test_render_does_not_duplicate_currency_style_on_repeated_calls(self):
        widget = BootstrapMoneyWidget(default_currency="EUR")
        widget.render("price", Money(10, EUR))
        html = widget.render("price", Money(10, EUR))
        # The style string should appear exactly once in the select attrs
        assert html.count("width: 150px") == 1


# ─── MoneyInputGroupMixin ─────────────────────────────────────────────────────


class _SimpleMoneyForm(MoneyInputGroupMixin, forms.Form):
    """Minimal form with one MoneyField for testing the mixin."""

    price = MoneyField(max_digits=10, decimal_places=2, default_currency="EUR")
    name = forms.CharField(max_length=100)


class _NoMoneyForm(MoneyInputGroupMixin, forms.Form):
    """Form with no MoneyFields — mixin should be a no-op."""

    name = forms.CharField(max_length=100)
    count = forms.IntegerField()


class _MultiMoneyForm(MoneyInputGroupMixin, forms.Form):
    """Form with multiple MoneyFields."""

    price = MoneyField(max_digits=10, decimal_places=2, default_currency="EUR")
    discount = MoneyField(
        max_digits=10, decimal_places=2, default_currency="EUR", required=False
    )
    label = forms.CharField(max_length=50)


class TestMoneyInputGroupMixin:
    def test_money_field_widget_replaced_with_bootstrap_widget(self):
        form = _SimpleMoneyForm()
        assert isinstance(form.fields["price"].widget, BootstrapMoneyWidget)

    def test_non_money_field_widget_unchanged(self):
        form = _SimpleMoneyForm()
        assert not isinstance(form.fields["name"].widget, BootstrapMoneyWidget)
        assert isinstance(form.fields["name"].widget, forms.TextInput)

    def test_no_money_fields_form_is_unaffected(self):
        form = _NoMoneyForm()
        for field in form.fields.values():
            assert not isinstance(field.widget, BootstrapMoneyWidget)

    def test_all_money_fields_replaced_in_multi_money_form(self):
        form = _MultiMoneyForm()
        assert isinstance(form.fields["price"].widget, BootstrapMoneyWidget)
        assert isinstance(form.fields["discount"].widget, BootstrapMoneyWidget)
        assert not isinstance(form.fields["label"].widget, BootstrapMoneyWidget)

    def test_sub_widgets_are_preserved(self):
        """The amount and currency sub-widgets must be kept intact."""
        form = _SimpleMoneyForm()
        widget = form.fields["price"].widget
        assert len(widget.widgets) == 2  # amount + currency

    def test_default_currency_is_preserved(self):
        form = _SimpleMoneyForm()
        widget = form.fields["price"].widget
        assert widget.default_currency == "EUR"

    def test_rendered_output_contains_input_group(self):
        form = _SimpleMoneyForm(initial={"price": Money(100, EUR)})
        html = str(form["price"])
        assert 'class="input-group"' in html

    def test_mixin_works_with_model_form(self):
        """Smoke-test: MoneyInputGroupMixin applied to a ModelForm instantiates OK."""
        from property.forms import PropertyEditForm

        form = PropertyEditForm()
        assert isinstance(form.fields["buying_value"].widget, BootstrapMoneyWidget)
        assert isinstance(
            form.fields["buying_value_gross"].widget, BootstrapMoneyWidget
        )
        assert isinstance(form.fields["selling_value"].widget, BootstrapMoneyWidget)

    @pytest.mark.parametrize(
        "form_class,money_fields",
        [
            (
                "property.forms.PropertyLoanForm",
                ["original_amount"],
            ),
            (
                "property.forms.LeaseForm",
                ["rent_amount", "charges_amount", "deposit_amount"],
            ),
            (
                "property.forms.ManagementMandateForm",
                ["fixed_fee"],
            ),
            (
                "property.forms.PropertyLedgerEntryQuickCreateForm",
                ["amount"],
            ),
            (
                "property.forms.PropertyLedgerEntryEditForm",
                ["amount"],
            ),
            (
                "property.forms.PropertyLoanScheduleForm",
                ["amount"],
            ),
            (
                "property.forms.PropertyValueQuickCreateForm",
                ["value"],
            ),
        ],
    )
    def test_all_property_forms_have_bootstrap_money_widgets(
        self, form_class, money_fields
    ):
        import importlib

        module_path, class_name = form_class.rsplit(".", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        form = cls()
        for field_name in money_fields:
            assert isinstance(
                form.fields[field_name].widget,
                BootstrapMoneyWidget,
            ), f"{class_name}.{field_name} widget is not BootstrapMoneyWidget"
