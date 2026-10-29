"""Tests for the identity of the landlord."""

from typing import cast

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import UserManager

from base.models import Ownership
from rental.services.landlord import landlord_of


@pytest.mark.django_db
def test_landlord_fields_of_the_property(prop):
    landlord = landlord_of(prop)
    assert landlord.name == "SCI Lilas"
    assert landlord.address == "1 rue des Lilas\n75000 Paris"
    assert landlord.is_complete


@pytest.mark.django_db
def test_landlord_from_the_owners(prop, user):
    prop.landlord_name = prop.landlord_address = ""
    other = cast(UserManager, get_user_model().objects).create_user(
        "other", first_name="Anne", last_name="Martin"
    )
    other.profile.postal_address = "3 place du Marché"
    other.profile.save()
    user.first_name, user.last_name = "Paul", "Durand"
    user.save()
    for owner in (user, other):
        Ownership.objects.create(asset=prop, user=owner, share=50)
    landlord = landlord_of(prop)
    assert landlord.name == "Paul Durand & Anne Martin"
    assert landlord.address == "3 place du Marché"


@pytest.mark.django_db
def test_landlord_of_a_household_property(prop, user):
    prop.landlord_name = prop.landlord_address = ""
    child = cast(UserManager, get_user_model().objects).create_user("kid")
    child.profile.is_child = True
    child.profile.save()
    landlord = landlord_of(prop)
    assert landlord.name == "testuser"
    assert landlord.address == ""
    assert not landlord.is_complete
