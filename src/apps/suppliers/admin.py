from django import forms
from django.contrib import admin
from django.db import models
from django.db.models import Count, Q

from apps.users.roles import is_restricted_supplier_user

from .access import get_active_supplier_ids_for_user, user_can_manage_supplier
from .models import Supplier, SupplierUserAssignment


class SupplierUserAssignmentInline(admin.TabularInline):
    model = SupplierUserAssignment
    extra = 0
    autocomplete_fields = ("user",)
    fields = ("user", "is_active", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "country",
        "orders_email",
        "auto_send_inquiry_submitted_notification",
        "auto_send_offer_sent_notification",
        "auto_send_offer_accepted_notification",
        "auto_send_offer_rejected_notification",
        "auto_send_payment_paid_notification",
        "is_active",
        "active_assignments_count",
        "updated_at",
    )
    list_filter = (
        "is_active",
        "country",
        "auto_send_inquiry_submitted_notification",
        "auto_send_offer_sent_notification",
        "auto_send_offer_accepted_notification",
        "auto_send_offer_rejected_notification",
        "auto_send_payment_paid_notification",
    )
    search_fields = (
        "name",
        "code",
        "slug",
        "contact_email",
        "orders_email",
        "inquiry_submitted_notification_email",
        "offer_sent_notification_email",
        "offer_accepted_notification_email",
        "offer_rejected_notification_email",
        "payment_paid_notification_email",
    )
    ordering = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "updated_at"
    inlines = (SupplierUserAssignmentInline,)
    fieldsets = (
        (
            "Supplier",
            {
                "fields": (
                    "name",
                    "slug",
                    "code",
                    "is_active",
                )
            },
        ),
        (
            "Contact",
            {
                "fields": (
                    "country",
                    "website",
                    "contact_name",
                    "contact_email",
                    "orders_email",
                    "contact_phone",
                )
            },
        ),
        (
            "Automatic Supplier Notifications",
            {
                "description": (
                    "If a custom template field is empty, the default email template is used. "
                    "If an event-specific destination email is empty, orders_email is used."
                ),
                "fields": (
                    "auto_send_inquiry_submitted_notification",
                    "inquiry_submitted_notification_email",
                    "send_inquiry_submitted_notification_internal_copy",
                    "inquiry_submitted_email_subject_template",
                    "inquiry_submitted_email_body_template",
                ),
            },
        ),
        (
            "Automatic Supplier Notifications - Offer Sent",
            {
                "fields": (
                    "auto_send_offer_sent_notification",
                    "offer_sent_notification_email",
                    "send_offer_sent_notification_internal_copy",
                    "offer_sent_email_subject_template",
                    "offer_sent_email_body_template",
                ),
            },
        ),
        (
            "Automatic Supplier Notifications - Offer Accepted",
            {
                "fields": (
                    "auto_send_offer_accepted_notification",
                    "offer_accepted_notification_email",
                    "send_offer_accepted_notification_internal_copy",
                ),
            },
        ),
        (
            "Automatic Supplier Notifications - Offer Rejected",
            {
                "fields": (
                    "auto_send_offer_rejected_notification",
                    "offer_rejected_notification_email",
                    "send_offer_rejected_notification_internal_copy",
                ),
            },
        ),
        (
            "Automatic Supplier Notifications - Payment Paid",
            {
                "fields": (
                    "auto_send_payment_paid_notification",
                    "payment_paid_notification_email",
                    "send_payment_paid_notification_internal_copy",
                ),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )
    formfield_overrides = {
        models.TextField: {
            "widget": forms.Textarea(attrs={"rows": 6}),
        }
    }

    @admin.display(description="Active Assignments", ordering="active_assignments_count")
    def active_assignments_count(self, obj: Supplier) -> int:
        return obj.active_assignments_count

    def get_queryset(self, request):
        queryset = super().get_queryset(request).annotate(
            active_assignments_count=Count(
                "user_assignments",
                filter=Q(user_assignments__is_active=True),
                distinct=True,
            )
        )
        if is_restricted_supplier_user(request.user):
            supplier_ids = get_active_supplier_ids_for_user(request.user)
            return queryset.filter(id__in=supplier_ids)
        return queryset

    def has_view_permission(self, request, obj=None):
        if is_restricted_supplier_user(request.user):
            if obj is None:
                return bool(get_active_supplier_ids_for_user(request.user))
            return user_can_manage_supplier(request.user, obj.id)
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


@admin.register(SupplierUserAssignment)
class SupplierUserAssignmentAdmin(admin.ModelAdmin):
    list_display = ("supplier", "user", "is_active", "updated_at")
    list_filter = ("is_active", "supplier")
    search_fields = (
        "supplier__name",
        "supplier__code",
        "user__username",
        "user__email",
    )
    autocomplete_fields = ("supplier", "user")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("supplier__name", "user__username")
    date_hierarchy = "updated_at"

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
