from __future__ import annotations

from dataclasses import dataclass

from django.contrib.sessions.backends.base import SessionBase

from apps.catalog.models import Product
from apps.catalog.public import get_public_products_queryset

REQUEST_CART_SESSION_KEY = "request_cart_v1"
REQUEST_CART_MAX_QUANTITY = 999
REQUEST_CART_MAX_NOTE_LENGTH = 500


@dataclass(frozen=True)
class RequestCartItem:
    product: Product
    quantity: int
    note: str


def get_request_cart_items(session: SessionBase) -> list[RequestCartItem]:
    cart = _get_normalized_cart(session)
    if not cart:
        return []

    product_ids = [int(product_id) for product_id in cart.keys()]
    products = {
        product.id: product
        for product in get_public_products_queryset().filter(id__in=product_ids)
    }

    items: list[RequestCartItem] = []
    removable_product_ids: list[str] = []
    for product_id, payload in cart.items():
        quantity = _normalize_quantity(payload.get("quantity"))
        if quantity <= 0:
            removable_product_ids.append(product_id)
            continue

        product = products.get(int(product_id))
        if product is None:
            removable_product_ids.append(product_id)
            continue

        items.append(
            RequestCartItem(
                product=product,
                quantity=quantity,
                note=_normalize_note(payload.get("note")),
            )
        )

    if removable_product_ids:
        for product_id in removable_product_ids:
            cart.pop(product_id, None)
        _write_cart(session, cart)

    return items


def get_request_cart_counts(session: SessionBase) -> tuple[int, int]:
    items = get_request_cart_items(session)
    line_count = len(items)
    quantity_total = sum(item.quantity for item in items)
    return line_count, quantity_total


def add_product_to_request_cart(
    session: SessionBase,
    *,
    product: Product,
    quantity: int = 1,
    note: str = "",
) -> bool:
    cart = _get_normalized_cart(session)
    key = str(product.id)

    current_payload = cart.get(key, {"quantity": 0, "note": ""})
    current_quantity = _normalize_quantity(current_payload.get("quantity"))
    quantity_to_add = _normalize_quantity(quantity)
    if quantity_to_add <= 0:
        return False
    merged_quantity = min(REQUEST_CART_MAX_QUANTITY, current_quantity + quantity_to_add)

    incoming_note = _normalize_note(note)
    merged_note = incoming_note if incoming_note else _normalize_note(current_payload.get("note"))

    cart[key] = {
        "quantity": merged_quantity,
        "note": merged_note,
    }
    _write_cart(session, cart)
    return True


def update_request_cart_item(
    session: SessionBase,
    *,
    product_id: int,
    quantity: int,
    note: str = "",
) -> None:
    cart = _get_normalized_cart(session)
    key = str(product_id)
    if key not in cart:
        return

    normalized_quantity = _normalize_quantity(quantity)
    if normalized_quantity <= 0:
        cart.pop(key, None)
    else:
        cart[key] = {
            "quantity": normalized_quantity,
            "note": _normalize_note(note),
        }
    _write_cart(session, cart)


def remove_product_from_request_cart(session: SessionBase, *, product_id: int) -> None:
    cart = _get_normalized_cart(session)
    key = str(product_id)
    if key in cart:
        cart.pop(key, None)
        _write_cart(session, cart)


def clear_request_cart(session: SessionBase) -> None:
    if REQUEST_CART_SESSION_KEY in session:
        del session[REQUEST_CART_SESSION_KEY]
        session.modified = True


def _get_normalized_cart(session: SessionBase) -> dict[str, dict[str, int | str]]:
    raw_cart = session.get(REQUEST_CART_SESSION_KEY, {})
    if not isinstance(raw_cart, dict):
        return {}

    normalized_cart: dict[str, dict[str, int | str]] = {}
    for raw_product_id, payload in raw_cart.items():
        if not isinstance(raw_product_id, str) or not raw_product_id.isdigit():
            continue
        if not isinstance(payload, dict):
            continue

        normalized_cart[raw_product_id] = {
            "quantity": _normalize_quantity(payload.get("quantity")),
            "note": _normalize_note(payload.get("note")),
        }

    return normalized_cart


def _write_cart(session: SessionBase, cart: dict[str, dict[str, int | str]]) -> None:
    if cart:
        session[REQUEST_CART_SESSION_KEY] = cart
    elif REQUEST_CART_SESSION_KEY in session:
        del session[REQUEST_CART_SESSION_KEY]
    session.modified = True


def _normalize_quantity(value: int | str | None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 0

    if parsed < 0:
        return 0
    if parsed == 0:
        return 0
    return min(parsed, REQUEST_CART_MAX_QUANTITY)


def _normalize_note(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:REQUEST_CART_MAX_NOTE_LENGTH]
