from django.contrib import admin

from .models import (
    AttributeDefinition,
    Brand,
    Category,
    Condition,
    PartNumber,
    Product,
    ProductAttributeValue,
    ProductImage,
)


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "brand_type", "country", "is_active", "updated_at")
    list_filter = ("brand_type", "is_active", "country")
    search_fields = ("name", "slug")
    ordering = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    ordering = ("sort_order", "name")
    autocomplete_fields = ("parent",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Condition)
class ConditionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "code", "slug")
    ordering = ("name",)
    prepopulated_fields = {"slug": ("name",)}


class PartNumberInline(admin.TabularInline):
    model = PartNumber
    extra = 0
    fields = (
        "number_raw",
        "number_normalized",
        "part_number_type",
        "brand",
        "is_primary",
    )
    readonly_fields = ("number_normalized",)
    autocomplete_fields = ("brand",)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    fields = ("image", "alt_text", "sort_order", "is_primary")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "sku",
        "title",
        "supplier",
        "brand",
        "category",
        "publication_status",
        "price_visibility_mode",
        "is_active",
        "featured",
        "updated_at",
    )
    list_filter = (
        "publication_status",
        "price_visibility_mode",
        "is_active",
        "featured",
        "supplier",
        "brand",
        "category",
        "condition",
    )
    search_fields = ("sku", "slug", "title", "supplier_product_code")
    ordering = ("-updated_at",)
    autocomplete_fields = ("supplier", "brand", "category", "condition")
    prepopulated_fields = {"slug": ("title",)}
    inlines = (PartNumberInline, ProductImageInline)


@admin.register(PartNumber)
class PartNumberAdmin(admin.ModelAdmin):
    list_display = (
        "number_raw",
        "number_normalized",
        "part_number_type",
        "product",
        "brand",
        "is_primary",
    )
    list_filter = ("part_number_type", "is_primary", "brand")
    search_fields = ("number_raw", "number_normalized", "product__sku", "product__title")
    ordering = ("number_normalized",)
    autocomplete_fields = ("product", "brand")


@admin.register(AttributeDefinition)
class AttributeDefinitionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "data_type",
        "unit",
        "is_filterable",
        "is_visible_on_product",
        "allows_multiple_values",
        "sort_order",
    )
    list_filter = (
        "data_type",
        "is_filterable",
        "is_visible_on_product",
        "allows_multiple_values",
    )
    search_fields = ("name", "slug", "unit")
    ordering = ("sort_order", "name")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ProductAttributeValue)
class ProductAttributeValueAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "attribute_definition",
        "value_text",
        "value_number",
        "value_boolean",
    )
    list_filter = ("attribute_definition", "attribute_definition__data_type")
    search_fields = ("product__sku", "product__title", "value_text", "value_normalized")
    ordering = ("product", "attribute_definition")
    autocomplete_fields = ("product", "attribute_definition")


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "sort_order", "is_primary", "updated_at")
    list_filter = ("is_primary",)
    search_fields = ("product__sku", "product__title", "alt_text")
    ordering = ("product", "sort_order", "id")
    autocomplete_fields = ("product",)
