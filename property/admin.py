"""Admin interface for managing properties."""

from django.contrib import admin

from property.models import Property, PropertyValue

admin.site.register(Property)
admin.site.register(PropertyValue)
