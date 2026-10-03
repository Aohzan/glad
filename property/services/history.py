"""Property values at many dates, computed from one bulk query.

``Property.get_value(max_date=...)`` runs one query per call, once per property
and per month for a history chart. ``PropertyValues`` reads the valuations of
a set of properties once and gives the same amounts without querying again.
"""

import datetime
from collections.abc import Iterable
from decimal import Decimal

from base.services.timeline import DatedValues
from property.models import Property, PropertyValue


class PropertyValues:
    """Values of properties, read with one query.

    The net values read the loans of the properties: prefetch
    ``loans__amortization_entries`` to compute them without queries.
    """

    def __init__(self, properties: Iterable[Property]) -> None:
        self._values = DatedValues(
            PropertyValue.objects.filter(property__in=properties)
            .order_by("property_id", "valuation_date", "pk")
            .values_list("property_id", "valuation_date", "value")
        )

    def at(self, prop: Property, moment: datetime.date) -> Decimal:
        """Amount of ``prop.get_value(max_date=moment)``, read up to its day."""
        day = moment.date() if isinstance(moment, datetime.datetime) else moment
        value = self._values.at(prop.pk, day)
        return value if value is not None else prop.buying_value.amount

    def net_at(self, prop: Property, day: datetime.date) -> Decimal:
        """Amount of ``prop.net_value_at_date(day)``: value minus the loans owed."""
        return self.at(prop, day) - prop.total_remaining_loans_at_date(day).amount
