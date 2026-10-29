"""Tests for the inventories of fixtures."""

import datetime
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from base.models import Document
from base.services.documents import attach_upload, documents_of
from property.models import Lease
from rental import rules
from rental.models import Inventory, InventoryItem
from rental.services.inventories import (
    _thumbnail,
    create_entry,
    create_exit,
    inventory_pdf,
)
from rental.services.signature import page_count

TODAY = datetime.date.today()


def _image(fmt="JPEG", size=(1600, 1200)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "teal").save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.mark.django_db
def test_entry_of_an_empty_lease(lease):
    inventory = create_entry(lease, TODAY)
    names = [room.name for room in inventory.rooms.all()]  # ty: ignore[unresolved-attribute]
    assert names == [name for name, _items in rules.DEFAULT_ROOMS]
    kitchen = inventory.rooms.get(name="Cuisine")  # ty: ignore[unresolved-attribute]
    assert "Évier" in [item.name for item in kitchen.items.all()]


@pytest.mark.django_db
def test_entry_of_a_furnished_lease(lease):
    lease.lease_type = Lease.LeaseType.FURNISHED
    inventory = create_entry(lease, TODAY)
    furniture = inventory.rooms.get(name=rules.FURNITURE_ROOM)  # ty: ignore[unresolved-attribute]
    assert furniture.items.count() == len(rules.MANDATORY_FURNITURE)


@pytest.mark.django_db
def test_exit_copies_the_entry(lease):
    exit_without_entry = create_exit(lease, TODAY)
    assert exit_without_entry.rooms.count() == len(rules.DEFAULT_ROOMS)  # ty: ignore[unresolved-attribute]
    exit_without_entry.delete()
    entry = create_entry(lease, TODAY)
    room = entry.rooms.first()  # ty: ignore[unresolved-attribute]
    room.items.update(condition=InventoryItem.Condition.GOOD)
    room.items.create(name="Placard encastré")
    exit_inventory = create_exit(lease, TODAY)
    copied = exit_inventory.rooms.get(name=room.name)  # ty: ignore[unresolved-attribute]
    assert "Placard encastré" in [item.name for item in copied.items.all()]
    assert set(copied.items.values_list("condition", flat=True)) == {""}


@pytest.mark.django_db
def test_pdf_with_photos(lease, user):
    inventory = create_entry(lease, TODAY)
    inventory.meters = {"electricity": "12345", "cold_water": "42"}
    inventory.keys = "2 clés"
    inventory.comment = "RAS"
    item = InventoryItem.objects.filter(room__inventory=inventory).first()
    assert item is not None
    item.condition = InventoryItem.Condition.WORN
    item.save()
    for index in range(5):
        attach_upload(item, SimpleUploadedFile(f"p{index}.jpg", _image()), user=user)
    for index in range(40):  # enough rows of photos to fill a page
        small = _image("PNG", (30 + index, 20))
        attach_upload(item, SimpleUploadedFile(f"s{index}.png", small), user=user)
    heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 32
    attach_upload(item, SimpleUploadedFile("iphone.heic", heic), user=user)
    content = inventory_pdf(inventory)
    assert content.startswith(b"%PDF")
    assert page_count(content) >= 2


def test_unreadable_photo(tmp_path):
    broken = tmp_path / "broken.heic"
    broken.write_bytes(b"\x00\x00\x00\x18ftypheic not an image")
    assert _thumbnail(str(broken)) is None
    good = tmp_path / "good.jpg"
    good.write_bytes(_image())
    thumbnail = _thumbnail(str(good))
    assert thumbnail is not None
    with Image.open(thumbnail) as image:
        assert max(image.size) == 900


# ── Views ───────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_create_and_fill_an_inventory(user_client, lease):
    tab = reverse("rental:lease_inventories", args=[lease.pk])
    assert user_client.get(tab).context["entry"] is None
    url = reverse("rental:create_inventory", args=[lease.pk, "entry"])
    response = user_client.post(url, {"date": "2026-09-01"})
    inventory = Inventory.objects.get(lease=lease)
    assert inventory.date == datetime.date(2026, 9, 1)
    assert response.url == reverse("rental:inventory_detail", args=[inventory.pk])
    response = user_client.post(url, {"date": "bad"})
    assert response.url == tab
    assert user_client.get(tab).context["entry"] == inventory
    # Header: meters and keys.
    detail = reverse("rental:inventory_detail", args=[inventory.pk])
    response = user_client.get(detail)
    assert response.context["rooms"][0]["count"] > 0
    response = user_client.post(
        detail,
        {
            "date": "2026-09-02",
            "keys": "2 clés",
            "comment": "",
            "meter_electricity": "123",
        },
    )
    assert response.status_code == 302
    inventory.refresh_from_db()
    assert inventory.meters == {"electricity": "123"}
    assert user_client.post(detail, {"date": ""}).status_code == 200


@pytest.mark.django_db
def test_unknown_inventory_kind(user_client, lease):
    response = user_client.post(
        reverse("rental:create_inventory", args=[lease.pk, "x"])
    )
    assert response.url == reverse("rental:lease_inventories", args=[lease.pk])
    assert not Inventory.objects.exists()


@pytest.mark.django_db
def test_exit_inventory_view(user_client, lease):
    user_client.post(reverse("rental:create_inventory", args=[lease.pk, "exit"]))
    assert Inventory.objects.get().kind == Inventory.Kind.EXIT


@pytest.mark.django_db
def test_rooms_and_items(user_client, lease):
    inventory = create_entry(lease, TODAY)
    response = user_client.post(
        reverse("rental:inventory_add_room", args=[inventory.pk]), {"name": "Cave"}
    )
    room = inventory.rooms.get(name="Cave")  # ty: ignore[unresolved-attribute]
    room_url = reverse("rental:inventory_room", args=[inventory.pk, room.pk])
    assert response.url == room_url
    user_client.post(
        reverse("rental:inventory_add_room", args=[inventory.pk]), {"name": ""}
    )
    user_client.post(
        reverse("rental:inventory_add_item", args=[inventory.pk, room.pk]),
        {"name": "Porte"},
    )
    item = room.items.get()
    response = user_client.get(room_url)
    assert response.status_code == 200
    assert 'capture="environment"' in response.content.decode()
    response = user_client.post(
        room_url,
        {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-0-id": str(item.pk),
            "form-0-condition": "damaged",
            "form-0-comment": "Rayée",
        },
    )
    assert response.status_code == 302
    item.refresh_from_db()
    assert (item.condition, item.comment) == ("damaged", "Rayée")
    response = user_client.post(
        room_url,
        {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-0-id": str(item.pk),
            "form-0-condition": "nope",
        },
    )
    assert response.status_code == 200
    user_client.post(
        reverse("rental:inventory_delete_item", args=[inventory.pk, item.pk])
    )
    assert not room.items.exists()
    user_client.post(
        reverse("rental:inventory_delete_room", args=[inventory.pk, room.pk])
    )
    assert not inventory.rooms.filter(name="Cave").exists()  # ty: ignore[unresolved-attribute]


@pytest.mark.django_db
def test_photos(user_client, lease):
    inventory = create_entry(lease, TODAY)
    item = InventoryItem.objects.filter(room__inventory=inventory).first()
    assert item is not None
    url = reverse("rental:inventory_add_photo", args=[inventory.pk, item.pk])
    user_client.post(url)
    user_client.post(url, {"photo": SimpleUploadedFile("x.txt", b"hello")})
    assert not documents_of(item).exists()
    response = user_client.post(url, {"photo": SimpleUploadedFile("mur.jpg", _image())})
    assert response.url == reverse(
        "rental:inventory_room",
        args=[inventory.pk, item.room_id],
    )
    (photo,) = documents_of(item)
    assert photo.kind == Document.Kind.PHOTO
    response = user_client.get(response.url)
    assert reverse("download_document", args=[photo.pk]) in response.content.decode()


@pytest.mark.django_db
def test_inventory_pdf_view(user_client, lease):
    inventory = create_entry(lease, TODAY)
    response = user_client.get(reverse("rental:inventory_pdf", args=[inventory.pk]))
    assert response["Content-Type"] == "application/pdf"
    assert f"etat-des-lieux-entry-{TODAY}.pdf" in response["Content-Disposition"]


@pytest.mark.django_db
def test_names(lease, user_client):
    inventory = create_entry(lease, TODAY)
    room = inventory.rooms.first()  # ty: ignore[unresolved-attribute]
    item = room.items.first()
    assert str(inventory) == f"Entry — {lease}"
    assert (str(room), str(item)) == (room.name, item.name)
    response = user_client.post(
        reverse("rental:inventory_add_item", args=[inventory.pk, room.pk]), {"name": ""}
    )
    assert response.status_code == 302
