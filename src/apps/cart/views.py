from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import TemplateView

from apps.catalog.public import get_public_products_queryset

from .services import (
    add_product_to_request_cart,
    clear_request_cart,
    get_request_cart_items,
    remove_product_from_request_cart,
    update_request_cart_item,
)


class RequestCartDetailView(TemplateView):
    template_name = "cart/request_cart.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cart_items = get_request_cart_items(self.request.session)
        total_quantity = sum(item.quantity for item in cart_items)

        context.update(
            {
                "page_title": _("Carrito de solicitud"),
                "cart_items": cart_items,
                "line_count": len(cart_items),
                "total_quantity": total_quantity,
            }
        )
        return context


class RequestCartAddView(View):
    def post(self, request, *args, **kwargs):
        product = get_object_or_404(get_public_products_queryset(), pk=kwargs["product_id"])
        quantity = _parse_quantity(request.POST.get("quantity"), allow_zero=False)
        if quantity is None:
            messages.error(request, _("La cantidad debe ser un número válido."))
            return redirect(_resolve_next_url(request))

        note = request.POST.get("note", "")

        item_added = add_product_to_request_cart(
            request.session,
            product=product,
            quantity=quantity,
            note=note,
        )
        if item_added:
            messages.success(request, _("Producto añadido al carrito de solicitud."))
        else:
            messages.error(request, _("La cantidad debe ser un número válido."))
        return redirect(_resolve_next_url(request))


class RequestCartUpdateView(View):
    def post(self, request, *args, **kwargs):
        raw_quantity = request.POST.get("quantity")
        parsed_quantity = _parse_quantity(raw_quantity, allow_zero=True)
        if parsed_quantity is None:
            messages.error(request, _("La cantidad debe ser un número válido."))
            return redirect("cart:request_cart_detail")

        update_request_cart_item(
            request.session,
            product_id=kwargs["product_id"],
            quantity=parsed_quantity,
            note=request.POST.get("note", ""),
        )
        messages.success(request, _("Carrito de solicitud actualizado."))
        return redirect("cart:request_cart_detail")


class RequestCartRemoveView(View):
    def post(self, request, *args, **kwargs):
        remove_product_from_request_cart(request.session, product_id=kwargs["product_id"])
        messages.success(request, _("Producto eliminado del carrito de solicitud."))
        return redirect("cart:request_cart_detail")


class RequestCartClearView(View):
    def post(self, request, *args, **kwargs):
        clear_request_cart(request.session)
        messages.success(request, _("Carrito de solicitud vaciado."))
        return redirect("cart:request_cart_detail")


def _resolve_next_url(request) -> str:
    next_url = (request.POST.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return reverse("cart:request_cart_detail")


def _parse_quantity(value: str | None, *, allow_zero: bool) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None

    if parsed < 0 or (parsed == 0 and not allow_zero):
        return None
    return parsed
