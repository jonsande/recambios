from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db.models import Count

from apps.users.roles import is_restricted_supplier_user

from .models import Inquiry, InquiryItem, InquiryOffer


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


@admin.register(InquiryOffer)
class InquiryOfferAdmin(InternalInquiryAccessMixin, admin.ModelAdmin):
    LOCKED_AFTER_SEND_FIELDS = (
        "confirmed_total",
        "currency",
        "lead_time_text",
        "customer_message",
    )

    list_display = (
        "reference_code",
        "inquiry_reference",
        "status",
        "confirmed_total",
        "currency",
        "sent_at",
        "accepted_at",
        "rejected_at",
        "updated_at",
    )
    list_filter = (
        "status",
        "currency",
        "sent_at",
        "accepted_at",
        "rejected_at",
        "created_at",
    )
    search_fields = (
        "reference_code",
        "inquiry__reference_code",
        "inquiry__guest_name",
        "inquiry__guest_email",
        "inquiry__user__username",
        "inquiry__user__email",
    )
    ordering = ("-created_at",)
    list_select_related = ("inquiry",)
    autocomplete_fields = ("inquiry",)
    readonly_fields = (
        "reference_code",
        "status",
        "access_token",
        "sent_at",
        "accepted_at",
        "rejected_at",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"
    actions = ("mark_selected_as_sent",)
    fieldsets = (
        (
            "Offer",
            {
                "fields": (
                    "reference_code",
                    "inquiry",
                    "status",
                    "access_token",
                )
            },
        ),
        (
            "Commercial Data",
            {
                "fields": (
                    "confirmed_total",
                    "currency",
                    "lead_time_text",
                    "customer_message",
                    "internal_notes",
                )
            },
        ),
        (
            "Lifecycle",
            {
                "fields": (
                    "sent_at",
                    "accepted_at",
                    "rejected_at",
                )
            },
        ),
        ("Audit", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj is not None and obj.status != InquiryOffer.Status.DRAFT:
            readonly_fields.extend(self.LOCKED_AFTER_SEND_FIELDS)
        return tuple(dict.fromkeys(readonly_fields))

    @admin.display(ordering="inquiry__reference_code", description="Inquiry")
    def inquiry_reference(self, obj: InquiryOffer) -> str:
        return obj.inquiry.reference_code

    @staticmethod
    def _render_validation_error(error: ValidationError) -> str:
        if hasattr(error, "message_dict"):
            parts = []
            for field_name, field_errors in error.message_dict.items():
                parts.extend(f"{field_name}: {message}" for message in field_errors)
            return "; ".join(parts)
        return "; ".join(error.messages)

    @admin.action(description="Mark selected offers as Sent")
    def mark_selected_as_sent(self, request, queryset):
        sent_count = 0
        skipped_count = 0

        for offer in queryset.select_related("inquiry"):
            try:
                offer.mark_sent(save=True)
            except ValidationError as error:
                skipped_count += 1
                details = self._render_validation_error(error)
                self.message_user(
                    request,
                    f"Offer {offer.reference_code} is not ready to send ({details}).",
                    level=messages.ERROR,
                )
            except ValueError:
                skipped_count += 1
                self.message_user(
                    request,
                    f"Offer {offer.reference_code} cannot be sent from its current status.",
                    level=messages.WARNING,
                )
            else:
                sent_count += 1

        if sent_count:
            self.message_user(request, f"Sent {sent_count} offer(s).")
        if skipped_count and not sent_count:
            self.message_user(request, "No offers were sent.", level=messages.WARNING)


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
