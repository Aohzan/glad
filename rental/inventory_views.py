"""Views of the inventories of fixtures: rooms, elements, photos and PDF."""

import datetime

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from base.models import Document
from base.services.documents import attach_upload, documents_of
from rental.forms import InventoryForm, InventoryItemFormSet, NameForm
from rental.models import Inventory, InventoryItem, InventoryRoom
from rental.services.documenso import is_configured
from rental.services.inventories import create_entry, create_exit, inventory_pdf
from rental.views import get_lease, lease_context


def lease_inventories(request: HttpRequest, pk: int) -> HttpResponse:
    """The entry and exit inventories of a lease."""
    lease = get_lease(pk)
    by_kind = {i.kind: i for i in Inventory.objects.filter(lease=lease)}
    return render(
        request,
        "rental/lease_inventories.html",
        {
            **lease_context(lease, "inventories"),
            "entry": by_kind.get(Inventory.Kind.ENTRY),
            "exit": by_kind.get(Inventory.Kind.EXIT),
            "today": datetime.date.today(),
        },
    )


@require_POST  # type: ignore
def create_inventory(request: HttpRequest, pk: int, kind: str) -> HttpResponse:
    """Start the entry inventory (usual rooms) or the exit one (rooms of the entry)."""
    lease = get_lease(pk)
    try:
        date = datetime.date.fromisoformat(request.POST.get("date", ""))
    except ValueError:
        date = datetime.date.today()
    create = {"entry": create_entry, "exit": create_exit}
    if kind not in create:
        return redirect("rental:lease_inventories", pk=lease.pk)
    try:
        inventory = create[kind](lease, date)
    except IntegrityError:
        messages.warning(request, _("This inventory already exists."))
        return redirect("rental:lease_inventories", pk=lease.pk)
    return redirect("rental:inventory_detail", pk=inventory.pk)


def get_inventory(pk: int) -> Inventory:
    return get_object_or_404(
        Inventory.objects.select_related("lease__property").prefetch_related(
            "lease__parties", "lease__property__mandates", "rooms__items"
        ),
        pk=pk,
    )


def inventory_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Date, meters and keys of an inventory, and its rooms."""
    inventory = get_inventory(pk)
    if request.method == "POST":
        form = InventoryForm(request.POST, instance=inventory)
        if form.is_valid():
            form.save()
            messages.success(request, _("Inventory saved."))
            return redirect("rental:inventory_detail", pk=inventory.pk)
        messages.error(request, _("Please correct the errors below."))
    else:
        form = InventoryForm(instance=inventory)
    rooms = [
        {
            "room": room,
            "count": len(room.items.all()),
            "done": sum(bool(item.condition) for item in room.items.all()),
        }
        for room in inventory.rooms.all()  # ty: ignore[unresolved-attribute]
    ]
    return render(
        request,
        "rental/inventory_detail.html",
        {
            **lease_context(inventory.lease, "inventories"),
            "inventory": inventory,
            "form": form,
            "rooms": rooms,
            "can_sign": is_configured(),
        },
    )


def inventory_download(request: HttpRequest, pk: int) -> HttpResponse:
    inventory = get_inventory(pk)
    response = HttpResponse(inventory_pdf(inventory), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="etat-des-lieux-{inventory.kind}-{inventory.date}.pdf"'
    )
    return response


@require_POST  # type: ignore
def add_room(request: HttpRequest, pk: int) -> HttpResponse:
    inventory = get_object_or_404(Inventory, pk=pk)
    form = NameForm(request.POST)
    if form.is_valid():
        last = inventory.rooms.order_by("-position").first()  # ty: ignore[unresolved-attribute]
        room = InventoryRoom.objects.create(
            inventory=inventory,
            name=form.cleaned_data["name"],
            position=(last.position + 1) if last else 0,
        )
        return redirect("rental:inventory_room", pk=inventory.pk, room_pk=room.pk)
    return redirect("rental:inventory_detail", pk=inventory.pk)


def _room(pk: int, room_pk: int) -> InventoryRoom:
    return get_object_or_404(
        InventoryRoom.objects.select_related("inventory__lease__property"),
        pk=room_pk,
        inventory_id=pk,
    )


def inventory_room(request: HttpRequest, pk: int, room_pk: int) -> HttpResponse:
    """The elements of a room: condition, comment and photos."""
    room = _room(pk, room_pk)
    items = room.items.all()  # ty: ignore[unresolved-attribute]
    if request.method == "POST":
        formset = InventoryItemFormSet(request.POST, queryset=items)
        if formset.is_valid():
            formset.save()
            messages.success(request, _("%(room)s saved.") % {"room": room.name})
            return redirect("rental:inventory_detail", pk=pk)
        messages.error(request, _("Please correct the errors below."))
    else:
        formset = InventoryItemFormSet(queryset=items)
    return render(
        request,
        "rental/inventory_room.html",
        {
            **lease_context(get_lease(room.inventory.lease_id), "inventories"),
            "inventory": room.inventory,
            "room": room,
            "formset": formset,
            "rows": [
                (form, list(documents_of(form.instance))) for form in formset.forms
            ],
            "item_form": NameForm(),
        },
    )


@require_POST  # type: ignore
def add_item(request: HttpRequest, pk: int, room_pk: int) -> HttpResponse:
    room = _room(pk, room_pk)
    form = NameForm(request.POST)
    if form.is_valid():
        InventoryItem.objects.create(room=room, name=form.cleaned_data["name"])
    return redirect("rental:inventory_room", pk=pk, room_pk=room.pk)


@require_POST  # type: ignore
def delete_item(request: HttpRequest, pk: int, item_pk: int) -> HttpResponse:
    item = get_object_or_404(InventoryItem, pk=item_pk, room__inventory_id=pk)
    room_pk = item.room_id  # ty: ignore[unresolved-attribute]
    item.delete()
    return redirect("rental:inventory_room", pk=pk, room_pk=room_pk)


@require_POST  # type: ignore
def delete_room(request: HttpRequest, pk: int, room_pk: int) -> HttpResponse:
    room = _room(pk, room_pk)
    room.delete()
    messages.success(request, _("%(room)s deleted.") % {"room": room.name})
    return redirect("rental:inventory_detail", pk=pk)


@require_POST  # type: ignore
def add_photo(request: HttpRequest, pk: int, item_pk: int) -> HttpResponse:
    """A photo of an element, taken with the phone camera or chosen in a file."""
    item = get_object_or_404(InventoryItem, pk=item_pk, room__inventory_id=pk)
    upload = request.FILES.get("photo")
    if upload is None:
        messages.error(request, _("Choose a photo."))
    else:
        try:
            attach_upload(
                item,
                upload,
                title=item.name,
                kind=Document.Kind.PHOTO,
                user=request.user,
            )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, _("Photo added."))
    return redirect(
        "rental:inventory_room",
        pk=pk,
        room_pk=item.room_id,  # ty: ignore[unresolved-attribute]
    )
