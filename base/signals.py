"""Delete the net worth snapshots affected by a change of any value or asset."""

from django.db.models.signals import post_delete, post_save, pre_save

from base.services.snapshots import invalidate_from
from finance.models.investment_account import (
    InvestmentAccount,
    InvestmentAccountCash,
    InvestmentAccountHolding,
    InvestmentAccountHoldingHistory,
)
from finance.models.other_asset import OtherAsset, OtherAssetValue
from finance.models.saving_account import SavingAccount, SavingAccountValue
from property.models import Property, PropertyLoan, PropertyValue
from property.models.asset import PropertyLoanAmortizationEntry
from property.models.scpi import (
    SCPI,
    SCPIBareOwnershipTheoreticalValue,
    SCPIInvestment,
    SCPISharePrice,
)

#: Dated values: only the snapshots from their date are affected.
DATED_MODELS = {
    SavingAccountValue: "value_date",
    InvestmentAccountCash: "value_date",
    InvestmentAccountHoldingHistory: "valuation_date",
    PropertyValue: "valuation_date",
    PropertyLoanAmortizationEntry: "date",
    SCPISharePrice: "date",
    SCPIBareOwnershipTheoreticalValue: "date",
    OtherAssetValue: "value_date",
}
#: Accounts and assets: any change may affect the whole history.
UNDATED_MODELS = (
    SavingAccount,
    InvestmentAccount,
    InvestmentAccountHolding,
    Property,
    PropertyLoan,
    SCPI,
    SCPIInvestment,
    OtherAsset,
)


def _dated_pre_save(sender, instance, **kwargs):
    field = DATED_MODELS[sender]
    day = getattr(instance, field)
    if instance.pk:
        old = sender.objects.filter(pk=instance.pk).values_list(field, flat=True)
        old_day = old.first()
        if old_day is not None and (day is None or old_day < day):
            day = old_day
    invalidate_from(day)


def _dated_post_delete(sender, instance, **kwargs):
    invalidate_from(getattr(instance, DATED_MODELS[sender]))


#: Fields that never change a value (saving only them keeps the snapshots).
_COSMETIC_FIELDS = frozenset({"is_favorite"})


def _undated_change(sender, instance, update_fields=None, **kwargs):
    if update_fields and set(update_fields) <= _COSMETIC_FIELDS:
        return
    invalidate_from(None)


for _model in DATED_MODELS:
    pre_save.connect(_dated_pre_save, sender=_model, dispatch_uid=f"nw-pre-{_model}")
    post_delete.connect(
        _dated_post_delete, sender=_model, dispatch_uid=f"nw-del-{_model}"
    )
for _model in UNDATED_MODELS:
    post_save.connect(_undated_change, sender=_model, dispatch_uid=f"nw-save-{_model}")
    post_delete.connect(_undated_change, sender=_model, dispatch_uid=f"nw-del-{_model}")
