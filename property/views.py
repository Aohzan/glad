"""Views for the property app."""

import datetime

from django.shortcuts import render

from property.models import Property, PropertyLoan


def index(request):
    """Property index view."""
    properties = Property.objects.filter().order_by("is_active", "name")
    property_list = []

    # Track total values
    total_gross_value = 0
    total_net_value = 0

    for prop in properties:
        # Get gross and net values
        gross_value = prop.gross_value
        net_value = prop.net_value

        # Add to totals
        if isinstance(total_gross_value, int) and total_gross_value == 0:
            # First property, set the initial values
            total_gross_value = gross_value
            total_net_value = net_value
        else:
            # Add to totals if currency matches
            if str(gross_value.currency) == str(total_gross_value.currency):
                total_gross_value += gross_value
                total_net_value += net_value

        property_list.append(
            {
                "model": prop,
                "current_value": prop.get_value(),
                "gross_value": gross_value,
                "net_value": net_value,
                "loans_count": PropertyLoan.objects.filter(property=prop).count(),
                "progression": prop.get_progression(),
            }
        )

    # Get data for the chart, both gross and net values
    properties_active = [p for p in properties if p.is_active]
    properties_months = []
    properties_gross_evolution = []
    properties_net_evolution = []

    # Find the earliest property purchase date
    earliest_date = None
    if properties_active:
        earliest_date = min(prop.buying_date for prop in properties_active)

    if earliest_date:
        # Generate data from the earliest property date to now
        now = datetime.datetime.now()
        start_date = datetime.datetime(earliest_date.year, earliest_date.month, 1)

        # Calculate all months from start to now
        current_date = start_date
        while current_date <= now:
            month_str = current_date.strftime("%b %Y")
            properties_months.append(month_str)

            # Get all properties that were active at that month (purchased before or during that month)
            month_properties = [
                p for p in properties_active if p.buying_date <= current_date.date()
            ]

            # Get property values for this month
            month_property_net_total = 0
            month_property_gross_total = 0
            for property_item in month_properties:
                try:
                    # For property net value at this specific month
                    net_value = property_item.net_value_at_date(current_date.date())
                    if net_value:
                        # Convert to same currency if needed
                        if (
                            isinstance(total_gross_value, int)
                            and total_gross_value == 0
                        ):
                            month_property_net_total += net_value.amount
                        elif hasattr(total_gross_value, "currency") and str(
                            net_value.currency
                        ) == str(total_gross_value.currency):
                            month_property_net_total += net_value.amount

                    # For property gross value at this specific month
                    gross_value = property_item.get_value(max_date=current_date)
                    if gross_value:
                        # Convert to same currency if needed
                        if (
                            isinstance(total_gross_value, int)
                            and total_gross_value == 0
                        ):
                            month_property_gross_total += gross_value.amount
                        elif hasattr(total_gross_value, "currency") and str(
                            gross_value.currency
                        ) == str(total_gross_value.currency):
                            month_property_gross_total += gross_value.amount
                except Exception:
                    # If there's an error, skip this property for this month
                    pass

            # Store the totals for the chart
            properties_gross_evolution.append(float(month_property_gross_total))
            properties_net_evolution.append(float(month_property_net_total))

            # Move to next month
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)

    context = {
        "properties": property_list,
        "inactive_properties_count": properties.filter(is_active=False).count(),
        "total_gross_value": total_gross_value,
        "total_net_value": total_net_value,
        "properties_months": properties_months,
        "properties_gross_evolution": properties_gross_evolution,
        "properties_net_evolution": properties_net_evolution,
    }
    return render(request, "property/index.html", context)
