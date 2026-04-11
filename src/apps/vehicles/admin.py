from django.contrib import admin

from .models import ProductVehicleFitment, Vehicle


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = (
        "brand",
        "model",
        "generation",
        "variant",
        "vehicle_type",
        "fuel_type",
        "year_start",
        "year_end",
        "is_active",
    )
    list_filter = ("vehicle_type", "fuel_type", "is_active", "brand")
    search_fields = ("brand__name", "model", "generation", "variant", "engine_code")
    ordering = ("brand__name", "model", "generation", "variant")
    autocomplete_fields = ("brand",)


@admin.register(ProductVehicleFitment)
class ProductVehicleFitmentAdmin(admin.ModelAdmin):
    list_display = ("product", "vehicle", "source", "is_verified", "updated_at")
    list_filter = ("source", "is_verified", "vehicle__vehicle_type")
    search_fields = ("product__sku", "product__title", "vehicle__brand__name", "vehicle__model")
    ordering = ("product__sku", "vehicle__brand__name", "vehicle__model")
    autocomplete_fields = ("product", "vehicle")
