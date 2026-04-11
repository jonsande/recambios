from django.contrib import admin
from django.db.models import Count

from apps.users.roles import is_restricted_supplier_user

from .models import Inquiry, InquiryItem


class InternalInquiryAccessMixin:
    def has_module_permission(self, request):
        if is_restricted_supplier_user(request.user):
            return False
        return super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        if is_restricted_supplier_user(request.user):
            return False
        return super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        if is_restricted_supplier_user(request.user):
            return False
        return super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        if is_restricted_supplier_user(request.user):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if is_restricted_supplier_user(request.user):
            return False
        return super().has_delete_permission(request, obj)


class InquiryItemInline(admin.TabularInline):
    model = InquiryItem
    extra = 0
    autocomplete_fields = ("product",)
    fields = (
        "product",
        "requested_quantity",
        "last_known_price_snapshot",
        "customer_note",
        "created_at",
    )
    readonly_fields = ("created_at",)
    show_change_link = True


@admin.register(Inquiry)
class InquiryAdmin(InternalInquiryAccessMixin, admin.ModelAdmin):
    list_display = (
        "reference_code",
        "status",
        "requester",
        "item_count",
        "language",
        "response_due_at",
        "supplier_feedback_at",
        "updated_at",
    )
    list_filter = (
        "status",
        "language",
        "created_at",
        "response_due_at",
        "supplier_feedback_at",
    )
    search_fields = (
        "reference_code",
        "user__username",
        "user__email",
        "guest_name",
        "guest_email",
        "guest_phone",
        "company_name",
        "tax_id",
        "notes_from_customer",
        "internal_notes",
    )
    ordering = ("-created_at",)
    list_select_related = ("user",)
    autocomplete_fields = ("user",)
    readonly_fields = ("reference_code", "created_at", "updated_at")
    date_hierarchy = "created_at"
    inlines = (InquiryItemInline,)
    fieldsets = (
        (
            "Inquiry",
            {
                "fields": (
                    "reference_code",
                    "status",
                    "language",
                )
            },
        ),
        (
            "Requester",
            {
                "fields": (
                    "user",
                    "guest_name",
                    "guest_email",
                    "guest_phone",
                    "company_name",
                    "tax_id",
                )
            },
        ),
        (
            "Follow-up",
            {
                "fields": (
                    "response_due_at",
                    "supplier_feedback_at",
                )
            },
        ),
        (
            "Notes",
            {
                "fields": (
                    "notes_from_customer",
                    "internal_notes",
                )
            },
        ),
        ("Audit", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(items_count=Count("items"))

    @admin.display(description="Requester")
    def requester(self, obj: Inquiry) -> str:
        return obj.requester_display

    @admin.display(ordering="items_count", description="Items")
    def item_count(self, obj: Inquiry) -> int:
        return obj.items_count


@admin.register(InquiryItem)
class InquiryItemAdmin(InternalInquiryAccessMixin, admin.ModelAdmin):
    list_display = (
        "inquiry",
        "product",
        "requested_quantity",
        "last_known_price_snapshot",
        "updated_at",
    )
    list_filter = ("inquiry", "created_at")
    search_fields = (
        "inquiry__reference_code",
        "product__sku",
        "product__title",
        "customer_note",
    )
    ordering = ("-created_at",)
    list_select_related = ("inquiry", "product")
    autocomplete_fields = ("inquiry", "product")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "created_at"
