"""Tests for property models."""

import datetime
from decimal import Decimal

from django.test import TestCase
from moneyed import Money

from property.models import Property, PropertyValue


class PropertyTestCase(TestCase):
    """Test cases for Property model."""

    def setUp(self):
        """Set up test data."""
        self.property = Property.objects.create(
            name="Test Property",
            address="123 Test Street",
            property_type=Property.HOUSE,
            buying_value=Money(200000, "EUR"),
            buying_date=datetime.date.today() - datetime.timedelta(days=365),
        )

    def test_property_creation(self):
        """Test basic property creation."""
        self.assertEqual(self.property.name, "Test Property")
        self.assertEqual(self.property.property_type, Property.HOUSE)
        self.assertEqual(self.property.buying_value.amount, Decimal("200000"))
        self.assertEqual(str(self.property.currency), "EUR")
        self.assertTrue(self.property.is_active)

    def test_get_value_without_valuations(self):
        """Test get_value returns initial value when no valuations exist."""
        value = self.property.get_value()
        self.assertEqual(value.amount, Decimal("200000"))
        self.assertEqual(str(value.currency), "EUR")

    def test_get_value_with_valuations(self):
        """Test get_value returns latest valuation."""
        # Create older valuation
        PropertyValue.objects.create(
            property=self.property,
            value=Money(220000, "EUR"),
            valuation_date=datetime.date.today() - datetime.timedelta(days=100),
        )

        # Create newer valuation
        PropertyValue.objects.create(
            property=self.property,
            value=Money(250000, "EUR"),
            valuation_date=datetime.date.today() - datetime.timedelta(days=30),
        )

        value = self.property.get_value()
        self.assertEqual(value.amount, Decimal("250000"))

    def test_get_value_with_date_filter(self):
        """Test get_value with specific date returns correct valuation."""
        # Create valuations
        PropertyValue.objects.create(
            property=self.property,
            value=Money(210000, "EUR"),
            valuation_date=datetime.date.today() - datetime.timedelta(days=200),
        )

        PropertyValue.objects.create(
            property=self.property,
            value=Money(230000, "EUR"),
            valuation_date=datetime.date.today() - datetime.timedelta(days=100),
        )

        PropertyValue.objects.create(
            property=self.property,
            value=Money(250000, "EUR"),
            valuation_date=datetime.date.today() - datetime.timedelta(days=50),
        )

        # Get value from 120 days ago - should return the 200-day old valuation
        target_date = datetime.datetime.now() - datetime.timedelta(days=120)
        value = self.property.get_value(max_date=target_date)
        self.assertEqual(value.amount, Decimal("210000"))

    def test_string_representation(self):
        """Test string representation of Property."""
        self.assertEqual(str(self.property), "Test Property")

    def test_property_currency_property(self):
        """Test currency property returns correct currency."""
        self.assertEqual(str(self.property.currency), "EUR")


class PropertyValueTestCase(TestCase):
    """Test cases for PropertyValue model."""

    def setUp(self):
        """Set up test data."""
        self.property = Property.objects.create(
            name="Test Property",
            address="123 Test Street",
            property_type=Property.APARTMENT,
            buying_value=Money(150000, "EUR"),
            buying_date=datetime.date.today(),
        )

    def test_property_value_creation(self):
        """Test basic property value creation."""
        property_value = PropertyValue.objects.create(
            property=self.property,
            value=Money(160000, "EUR"),
            valuation_date=datetime.date.today(),
        )

        self.assertEqual(property_value.property, self.property)
        self.assertEqual(property_value.value.amount, Decimal("160000"))
        self.assertEqual(property_value.valuation_date, datetime.date.today())

    def test_property_value_ordering(self):
        """Test that property values are ordered by valuation date descending."""
        # Create values in random order
        PropertyValue.objects.create(
            property=self.property,
            value=Money(150000, "EUR"),
            valuation_date=datetime.date(2023, 1, 1),
        )

        PropertyValue.objects.create(
            property=self.property,
            value=Money(170000, "EUR"),
            valuation_date=datetime.date(2023, 6, 1),
        )

        PropertyValue.objects.create(
            property=self.property,
            value=Money(160000, "EUR"),
            valuation_date=datetime.date(2023, 3, 1),
        )

        values = PropertyValue.objects.all()

        # Should be ordered by valuation_date descending
        self.assertEqual(values[0].valuation_date, datetime.date(2023, 6, 1))
        self.assertEqual(values[1].valuation_date, datetime.date(2023, 3, 1))
        self.assertEqual(values[2].valuation_date, datetime.date(2023, 1, 1))

    def test_related_name_works(self):
        """Test that the related_name 'property_values' works correctly."""
        PropertyValue.objects.create(
            property=self.property,
            value=Money(160000, "EUR"),
            valuation_date=datetime.date.today(),
        )

        PropertyValue.objects.create(
            property=self.property,
            value=Money(165000, "EUR"),
            valuation_date=datetime.date.today() - datetime.timedelta(days=30),
        )

        # Access values through the related name
        property_values = self.property.property_values.all()
        self.assertEqual(property_values.count(), 2)
