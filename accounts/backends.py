"""Authentication backends of the accounts app."""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from .models import is_child


class HouseholdModelBackend(ModelBackend):
    """Model backend refusing the children of the household, who cannot log in."""

    def user_can_authenticate(self, user) -> bool:
        return super().user_can_authenticate(user) and not is_child(user)

    def get_user(self, user_id):
        """User of the session, with its profile to check it in the same query.

        A session opened for a user later flagged as a child is dropped.
        """
        user_model = get_user_model()
        try:
            user = user_model._default_manager.select_related("profile").get(pk=user_id)
        except user_model.DoesNotExist:
            return None
        return user if self.user_can_authenticate(user) else None
