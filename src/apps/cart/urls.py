from django.urls import path
from django.utils.translation import gettext_lazy as _

from .views import (
    RequestCartAddView,
    RequestCartClearView,
    RequestCartDetailView,
    RequestCartRemoveView,
    RequestCartUpdateView,
)

app_name = "cart"

urlpatterns = [
    path(_("solicitud/carrito/"), RequestCartDetailView.as_view(), name="request_cart_detail"),
    path(
        _("solicitud/carrito/anadir/<int:product_id>/"),
        RequestCartAddView.as_view(),
        name="request_cart_add",
    ),
    path(
        _("solicitud/carrito/actualizar/<int:product_id>/"),
        RequestCartUpdateView.as_view(),
        name="request_cart_update",
    ),
    path(
        _("solicitud/carrito/eliminar/<int:product_id>/"),
        RequestCartRemoveView.as_view(),
        name="request_cart_remove",
    ),
    path(_("solicitud/carrito/vaciar/"), RequestCartClearView.as_view(), name="request_cart_clear"),
]
