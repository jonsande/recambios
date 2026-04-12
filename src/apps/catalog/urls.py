from django.urls import path
from django.utils.translation import gettext_lazy as _

from .views import CategoryListView, ProductDetailView, ProductListView

app_name = "catalog"

urlpatterns = [
    path(_("categorias/"), CategoryListView.as_view(), name="category_list"),
    path(
        _("categorias/<slug:category_slug>/"),
        ProductListView.as_view(),
        name="category_products",
    ),
    path(_("productos/"), ProductListView.as_view(), name="product_list"),
    path(_("productos/<slug:slug>/"), ProductDetailView.as_view(), name="product_detail"),
]
