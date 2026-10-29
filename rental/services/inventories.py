"""Inventories of fixtures: creation, photos and PDF.

The PDF is written in French: it is the document signed with the tenant.
"""

import datetime
import io
import logging

from django.db import transaction
from django.utils import formats, translation
lazy from PIL import Image, UnidentifiedImageError

from base.services.documents import documents_of
from base.services.pdf import BasePdf
from property.models import Lease
from rental import rules
from rental.models import Inventory, InventoryItem, InventoryRoom
from rental.services.landlord import landlord_of
from rental.services.signature import add_signature_page

logger = logging.getLogger(__name__)

#: Longest side of a photo in the PDF, in pixels.
PHOTO_PIXELS = 900
#: Width of a photo thumbnail in the PDF, in mm.
PHOTO_WIDTH = 42

_CONDITIONS_FR = {
    InventoryItem.Condition.NEW: "Neuf",
    InventoryItem.Condition.GOOD: "Bon état",
    InventoryItem.Condition.WORN: "Usage normal",
    InventoryItem.Condition.POOR: "Mauvais état",
    InventoryItem.Condition.DAMAGED: "Dégradé",
}


def _add_rooms(inventory: Inventory, rooms) -> None:
    for position, (name, items) in enumerate(rooms):
        room = InventoryRoom.objects.create(
            inventory=inventory, name=name, position=position
        )
        InventoryItem.objects.bulk_create(
            InventoryItem(room=room, name=item) for item in items
        )


@transaction.atomic
def create_entry(lease: Lease, date: datetime.date) -> Inventory:
    """The entry inventory with the usual rooms, and the furniture when furnished."""
    inventory = Inventory.objects.create(
        lease=lease, kind=Inventory.Kind.ENTRY, date=date
    )
    rooms = list(rules.DEFAULT_ROOMS)
    if lease.is_furnished:
        rooms.append((rules.FURNITURE_ROOM, rules.MANDATORY_FURNITURE))
    _add_rooms(inventory, rooms)
    return inventory


@transaction.atomic
def create_exit(lease: Lease, date: datetime.date) -> Inventory:
    """The exit inventory, with the rooms and elements of the entry one."""
    inventory = Inventory.objects.create(
        lease=lease, kind=Inventory.Kind.EXIT, date=date
    )
    entry = (
        Inventory.objects.filter(lease=lease, kind=Inventory.Kind.ENTRY)
        .prefetch_related("rooms__items")
        .first()
    )
    if entry is None:
        _add_rooms(inventory, rules.DEFAULT_ROOMS)
        return inventory
    _add_rooms(
        inventory,
        [
            (room.name, [item.name for item in room.items.all()])
            for room in entry.rooms.all()  # ty: ignore[unresolved-attribute]
        ],
    )
    return inventory


def _date(day: datetime.date) -> str:
    with translation.override("fr"):
        return formats.date_format(day, "j F Y")


def _thumbnail(path: str) -> io.BytesIO | None:
    """A JPEG copy of the photo, small enough for the PDF; None when unreadable."""
    try:
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((PHOTO_PIXELS, PHOTO_PIXELS))
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=80)
    except OSError, UnidentifiedImageError:
        logger.info("Photo %s left out of the inventory PDF", path)
        return None
    buffer.seek(0)
    return buffer


def _photos(pdf: BasePdf, item: InventoryItem) -> None:
    images = [d for d in documents_of(item) if d.is_image]
    x = pdf.l_margin
    for document in images:
        thumbnail = _thumbnail(document.file.path)
        if thumbnail is None:
            continue
        if x + PHOTO_WIDTH > pdf.w - pdf.r_margin:
            x = pdf.l_margin
            pdf.ln(PHOTO_WIDTH * 0.8)
        if pdf.get_y() + PHOTO_WIDTH > pdf.h - pdf.b_margin:
            pdf.add_page()
        pdf.image(thumbnail, x=x, y=pdf.get_y(), w=PHOTO_WIDTH)
        x += PHOTO_WIDTH + 3
    if images:
        pdf.ln(PHOTO_WIDTH * 0.8)


def inventory_pdf(inventory: Inventory) -> bytes:
    """The inventory with its photos, ending with the signature page."""
    lease = inventory.lease
    prop = lease.property
    landlord = landlord_of(prop)
    tenants = lease.tenants
    pdf = BasePdf()
    pdf.add_page()
    kind = "d'entrée" if inventory.kind == Inventory.Kind.ENTRY else "de sortie"
    pdf.heading(f"État des lieux {kind}")
    pdf.note(
        "Établi contradictoirement entre les parties (article 3-2 de la loi n° "
        "89-462 du 6 juillet 1989 et décret n° 2016-382 du 30 mars 2016)."
    )
    pdf.paragraph(
        f"Date : {_date(inventory.date)}\n"
        f"Logement : {prop.full_address or prop.name}\n"
        f"Bailleur : {landlord.name}\n"
        f"Locataire : {', '.join(t.name for t in tenants)}"
    )
    meters = [
        f"{label} : {inventory.meters.get(key)}"
        for key, label in (
            ("electricity", "Électricité"),
            ("gas", "Gaz"),
            ("cold_water", "Eau froide"),
            ("hot_water", "Eau chaude"),
        )
        if inventory.meters.get(key)
    ]
    if meters:
        pdf.subheading("Relevés des compteurs")
        pdf.paragraph("\n".join(meters))
    if inventory.keys:
        pdf.subheading("Clés remises")
        pdf.paragraph(inventory.keys)
    rooms = inventory.rooms.prefetch_related("items")  # ty: ignore[unresolved-attribute]
    for room in rooms:
        pdf.subheading(room.name)
        items = list(room.items.all())
        pdf.simple_table(
            ["Élément", "État", "Observations"],
            [
                [item.name, _CONDITIONS_FR.get(item.condition, ""), item.comment]
                for item in items
            ],
            [55, 30, 95],
            text_columns=3,
        )
        for item in items:
            _photos(pdf, item)
    if inventory.comment:
        pdf.subheading("Observations générales")
        pdf.paragraph(inventory.comment)
    add_signature_page(
        pdf,
        [("Bailleur", landlord.name)] + [("Locataire", t.name) for t in tenants],
        prop.city,
    )
    return pdf.render()
