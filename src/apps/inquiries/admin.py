import logging

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db.models import Count

from apps.users.roles import is_restricted_supplier_user

from .emails import send_customer_offer_sent_email
from .models import Inquiry, InquiryItem, InquiryOffer, InquiryOfferPayment

logger = logging.getLogger(__name__)


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
        "payment_reference",
        "sent_at",
        "offer_response_deadline_at",
        "accepted_at",
        "rejected_at",
        "expired_at",
        "updated_at",
    )
    list_filter = (
        "status",
        "currency",
        "sent_at",
        "offer_response_deadline_at",
        "accepted_at",
        "rejected_at",
        "expired_at",
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
        "offer_response_deadline_at",
        "response_deadline_hours_snapshot",
        "payment_deadline_hours_snapshot",
        "accepted_at",
        "rejected_at",
        "expired_at",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"
    actions = (
        "mark_selected_as_sent",
        "resend_offer_email_to_customer",
        "initiate_payment_for_selected_offers",
    )
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
                    "offer_response_deadline_at",
                    "response_deadline_hours_snapshot",
                    "payment_deadline_hours_snapshot",
                    "accepted_at",
                    "rejected_at",
                    "expired_at",
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

    @admin.display(description="Payment")
    def payment_reference(self, obj: InquiryOffer) -> str:
        if not obj.has_payment_record:
            return "-"
        return obj.payment.reference_code

    @staticmethod
    def _render_validation_error(error: ValidationError) -> str:
        if hasattr(error, "message_dict"):
            parts = []
            for field_name, field_errors in error.message_dict.items():
                parts.extend(f"{field_name}: {message}" for message in field_errors)
            return "; ".join(parts)
        return "; ".join(error.messages)

    @admin.action(description="Send selected offers to customers")
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

    @admin.action(description="Re-send offer email to customers")
    def resend_offer_email_to_customer(self, request, queryset):
        resent_count = 0
        skipped_count = 0
        failed_count = 0

        for offer in queryset.select_related("inquiry", "inquiry__user"):
            if offer.status not in {
                InquiryOffer.Status.SENT,
                InquiryOffer.Status.ACCEPTED,
            }:
                skipped_count += 1
                self.message_user(
                    request,
                    (
                        f"Offer {offer.reference_code} was skipped because "
                        "manual re-send is only available for sent or accepted offers."
                    ),
                    level=messages.WARNING,
                )
                continue

            try:
                email_sent = send_customer_offer_sent_email(offer)
            except Exception:
                failed_count += 1
                logger.exception(
                    "Failed to manually re-send customer offer email (offer=%s inquiry=%s).",
                    offer.reference_code,
                    offer.inquiry.reference_code,
                )
                self.message_user(
                    request,
                    (
                        f"Offer {offer.reference_code} email could not be re-sent "
                        "due to an email delivery error."
                    ),
                    level=messages.ERROR,
                )
                continue

            if not email_sent:
                skipped_count += 1
                self.message_user(
                    request,
                    (
                        f"Offer {offer.reference_code} email could not be re-sent "
                        "because the customer email is missing."
                    ),
                    level=messages.WARNING,
                )
                continue

            resent_count += 1

        if resent_count:
            self.message_user(request, f"Re-sent {resent_count} offer email(s).")
        if failed_count and not resent_count:
            self.message_user(
                request,
                "No offer emails were re-sent due to delivery errors.",
                level=messages.ERROR,
            )
        elif skipped_count and not resent_count and not failed_count:
            self.message_user(
                request,
                "No offer emails were re-sent.",
                level=messages.WARNING,
            )

    @admin.action(description="Initiate payment for selected offers")
    def initiate_payment_for_selected_offers(self, request, queryset):
        initiated_count = 0
        skipped_count = 0

        for offer in queryset.select_related("inquiry"):
            try:
                InquiryOfferPayment.initiate_from_offer(offer, save=True)
            except ValidationError as error:
                skipped_count += 1
                details = self._render_validation_error(error)
                self.message_user(
                    request,
                    (
                        f"Payment for offer {offer.reference_code} could not be initiated "
                        f"({details})."
                    ),
                    level=messages.ERROR,
                )
            except ValueError as error:
                skipped_count += 1
                self.message_user(
                    request,
                    (
                        f"Payment for offer {offer.reference_code} could not be initiated "
                        f"({error})."
                    ),
                    level=messages.WARNING,
                )
            else:
                initiated_count += 1

        if initiated_count:
            self.message_user(request, f"Initiated {initiated_count} payment record(s).")
        if skipped_count and not initiated_count:
            self.message_user(
                request,
                "No payment records were initiated.",
                level=messages.WARNING,
            )


@admin.register(InquiryOfferPayment)
class InquiryOfferPaymentAdmin(InternalInquiryAccessMixin, admin.ModelAdmin):
    list_display = (
        "reference_code",
        "offer_reference",
        "inquiry_reference",
        "status",
        "payable_amount",
        "currency",
        "provider",
        "provider_reference",
        "initiated_at",
        "payment_deadline_at",
        "paid_at",
        "failed_at",
        "cancelled_at",
        "updated_at",
    )
    list_filter = (
        "status",
        "currency",
        "provider",
        "initiated_at",
        "payment_deadline_at",
        "paid_at",
        "failed_at",
        "cancelled_at",
        "created_at",
    )
    search_fields = (
        "reference_code",
        "offer__reference_code",
        "offer__inquiry__reference_code",
        "provider_reference",
    )
    ordering = ("-created_at",)
    list_select_related = ("offer", "offer__inquiry")
    autocomplete_fields = ("offer",)
    readonly_fields = (
        "reference_code",
        "offer",
        "status",
        "payable_amount",
        "currency",
        "initiated_at",
        "payment_deadline_at",
        "paid_at",
        "failed_at",
        "cancelled_at",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"
    actions = (
        "mark_selected_as_paid",
        "mark_selected_as_failed",
        "mark_selected_as_cancelled",
    )
    fieldsets = (
        (
            "Payment",
            {
                "fields": (
                    "reference_code",
                    "offer",
                    "status",
                    "payable_amount",
                    "currency",
                )
            },
        ),
        (
            "Provider",
            {
                "fields": (
                    "provider",
                    "provider_reference",
                    "internal_notes",
                )
            },
        ),
        (
            "Lifecycle",
            {
                "fields": (
                    "initiated_at",
                    "payment_deadline_at",
                    "paid_at",
                    "failed_at",
                    "cancelled_at",
                )
            },
        ),
        ("Audit", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def has_add_permission(self, request):
        return False

    @admin.display(ordering="offer__reference_code", description="Offer")
    def offer_reference(self, obj: InquiryOfferPayment) -> str:
        return obj.offer.reference_code

    @admin.display(ordering="offer__inquiry__reference_code", description="Inquiry")
    def inquiry_reference(self, obj: InquiryOfferPayment) -> str:
        return obj.offer.inquiry.reference_code

    def _transition_selected(
        self,
        request,
        queryset,
        *,
        transition_method: str,
        transition_label: str,
    ) -> None:
        transitioned_count = 0
        skipped_count = 0

        for payment in queryset.select_related("offer", "offer__inquiry"):
            transition = getattr(payment, transition_method)
            try:
                transition(save=True)
            except ValidationError as error:
                skipped_count += 1
                details = InquiryOfferAdmin._render_validation_error(error)
                self.message_user(
                    request,
                    (
                        f"Payment {payment.reference_code} could not transition to "
                        f"{transition_label} ({details})."
                    ),
                    level=messages.ERROR,
                )
            except ValueError as error:
                skipped_count += 1
                self.message_user(
                    request,
                    (
                        f"Payment {payment.reference_code} could not transition to "
                        f"{transition_label} ({error})."
                    ),
                    level=messages.WARNING,
                )
            else:
                transitioned_count += 1

        if transitioned_count:
            self.message_user(
                request,
                f"Transitioned {transitioned_count} payment record(s) to {transition_label}.",
            )
        if skipped_count and not transitioned_count:
            self.message_user(
                request,
                f"No payment records were transitioned to {transition_label}.",
                level=messages.WARNING,
            )

    @admin.action(description="Mark selected payments as Paid")
    def mark_selected_as_paid(self, request, queryset):
        self._transition_selected(
            request,
            queryset,
            transition_method="mark_paid",
            transition_label="paid",
        )

    @admin.action(description="Mark selected payments as Failed")
    def mark_selected_as_failed(self, request, queryset):
        self._transition_selected(
            request,
            queryset,
            transition_method="mark_failed",
            transition_label="failed",
        )

    @admin.action(description="Mark selected payments as Cancelled")
    def mark_selected_as_cancelled(self, request, queryset):
        self._transition_selected(
            request,
            queryset,
            transition_method="mark_cancelled",
            transition_label="cancelled",
        )


@admin.register(Inquiry)
class InquiryAdmin(InternalInquiryAccessMixin, admin.ModelAdmin):
    NEGATIVE_RESOLUTION_FIELDS = (
        "negative_resolution_reason",
        "negative_resolution_internal_notes",
        "negative_resolution_customer_message",
    )

    list_display = (
        "reference_code",
        "status",
        "negative_resolution_reason",
        "negative_resolved_at",
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
        "negative_resolution_reason",
        "created_at",
        "negative_resolved_at",
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
    actions = ("finalize_selected_as_not_offerable",)
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
        (
            "Negative Resolution",
            {
                "fields": (
                    "negative_resolution_reason",
                    "negative_resolution_internal_notes",
                    "negative_resolution_customer_message",
                    "negative_resolved_at",
                )
            },
        ),
        ("Audit", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        readonly_fields.append("negative_resolved_at")
        if obj is not None and obj.negative_resolved_at is not None:
            readonly_fields.extend(self.NEGATIVE_RESOLUTION_FIELDS)
        return tuple(dict.fromkeys(readonly_fields))

    @staticmethod
    def _render_validation_error(error: ValidationError) -> str:
        if hasattr(error, "message_dict"):
            parts = []
            for field_name, field_errors in error.message_dict.items():
                parts.extend(f"{field_name}: {message}" for message in field_errors)
            return "; ".join(parts)
        return "; ".join(error.messages)

    @admin.action(description="Finalize selected inquiries as Not Offerable")
    def finalize_selected_as_not_offerable(self, request, queryset):
        finalized_count = 0
        skipped_count = 0

        for inquiry in queryset:
            try:
                inquiry.finalize_negative_resolution(save=True)
            except ValidationError as error:
                skipped_count += 1
                details = self._render_validation_error(error)
                self.message_user(
                    request,
                    (
                        f"Inquiry {inquiry.reference_code} could not be finalized "
                        f"as not offerable ({details})."
                    ),
                    level=messages.ERROR,
                )
            except ValueError as error:
                skipped_count += 1
                self.message_user(
                    request,
                    (
                        f"Inquiry {inquiry.reference_code} could not be finalized "
                        f"as not offerable ({error})."
                    ),
                    level=messages.WARNING,
                )
            else:
                finalized_count += 1

        if finalized_count:
            self.message_user(
                request,
                f"Finalized {finalized_count} inquiry(ies) as not offerable.",
            )
        if skipped_count and not finalized_count:
            self.message_user(
                request,
                "No inquiries were finalized as not offerable.",
                level=messages.WARNING,
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
