"""General models for the application."""

from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django_countries.fields import CountryField


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """Create or update user profile when user is created or updated."""
    if created:
        instance.userprofile = UserProfile.objects.create(
            user=instance)  # pylint: disable=no-member
        instance.userprofile.save()


class UserProfile(models.Model):
    """Extended user model."""

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    household = models.ForeignKey(
        "Household", on_delete=models.CASCADE, null=True, blank=True
    )

    def __str__(self):
        return str(self.user)


class BaseModel(models.Model):
    """Base model with common fields."""

    id = models.AutoField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Household(BaseModel):
    """Household model."""

    id = models.AutoField(primary_key=True)
    country = CountryField()
    name = models.CharField(max_length=255)

    def __str__(self):
        return str(self.name)

    @property
    def accounts(self):
        """Get all accounts for the household."""
        return self.account_set.all()

    @property
    def properties(self):
        """Get all properties for the household."""
        return self.property_set.all()

    @property
    def users(self):
        """Get all users for the household."""
        return self.userprofile_set.all()

    @property
    def total_accounts_value(self) -> float:
        """Get the total wealth value of the household."""
        return sum([account.current_balance for account in self.accounts])

    @property
    def total_properties_value(self) -> float:
        """Get the total properties value of the household."""
        return sum([property.current_value for property in self.properties])

    @property
    def total_net_worth(self) -> float:
        """Get the total wealth value of the household."""
        return self.total_accounts_value + self.total_properties_value
