from django.urls import path
from django.utils.translation import gettext_lazy as _

from .views import (
    CategoryListView,
    CompatibilityBrandListView,
    CompatibilityModelYearView,
    CompatibilityVehicleTypeListView,
    ProductDetailView,
    ProductFilterVehicleBrandFieldView,
    ProductFilterVehicleModelFieldView,
    ProductListView,
)

app_name = "catalog"

urlpatterns = [
    path(_("categorias/"), CategoryListView.as_view(), name="category_list"),
    path(
        _("categorias/<slug:category_slug>/"),
        ProductListView.as_view(),
        name="category_products",
    ),
    path(
        _("compatibilidad/"),
        CompatibilityVehicleTypeListView.as_view(),
        name="compatibility_vehicle_types",
    ),
    path(
        _("compatibilidad/<slug:vehicle_type>/"),
        CompatibilityBrandListView.as_view(),
        name="compatibility_vehicle_brands",
    ),
    path(
        _("compatibilidad/<slug:vehicle_type>/<slug:brand_slug>/"),
        CompatibilityModelYearView.as_view(),
        name="compatibility_vehicle_models",
    ),
    path(
        _("productos/filtros/vehiculo/marca/"),
        ProductFilterVehicleBrandFieldView.as_view(),
        name="product_filter_vehicle_brands_partial",
    ),
    path(
        _("productos/filtros/vehiculo/modelo/"),
        ProductFilterVehicleModelFieldView.as_view(),
        name="product_filter_vehicle_models_partial",
    ),
    path(_("productos/"), ProductListView.as_view(), name="product_list"),
    path(_("productos/<slug:slug>/"), ProductDetailView.as_view(), name="product_detail"),
]
