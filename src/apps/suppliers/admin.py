from django.contrib import admin

from .models import Supplier


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "country", "is_active", "updated_at")
    list_filter = ("is_active", "country")
    search_fields = ("name", "code", "slug", "contact_email")
    ordering = ("name",)
    prepopulated_fields = {"slug": ("name",)}
