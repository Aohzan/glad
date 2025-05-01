"""General models for the application."""

from django.db import models


class BaseModel(models.Model):
    """Base model with common fields."""

    id = models.AutoField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta options for the base model."""

        abstract = True
