from django.contrib import admin

from .models import SupplierImport, SupplierImportRow


class SupplierImportRowInline(admin.TabularInline):
    model = SupplierImportRow
    extra = 0
    fields = ("row_number", "processing_status", "linked_product", "error_message")
    readonly_fields = ("row_number", "processing_status", "error_message")
    autocomplete_fields = ("linked_product",)
    show_change_link = True


@admin.register(SupplierImport)
class SupplierImportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "supplier",
        "import_status",
        "total_rows",
        "successful_rows",
        "failed_rows",
        "started_at",
        "finished_at",
        "updated_at",
    )
    list_filter = ("import_status", "supplier")
    search_fields = ("id", "supplier__name", "supplier__code")
    ordering = ("-created_at",)
    autocomplete_fields = ("supplier", "uploaded_by")
    inlines = (SupplierImportRowInline,)


@admin.register(SupplierImportRow)
class SupplierImportRowAdmin(admin.ModelAdmin):
    list_display = (
        "supplier_import",
        "row_number",
        "processing_status",
        "linked_product",
        "updated_at",
    )
    list_filter = ("processing_status", "supplier_import__supplier")
    search_fields = ("supplier_import__id", "linked_product__sku", "error_message")
    ordering = ("supplier_import", "row_number")
    autocomplete_fields = ("supplier_import", "linked_product")
