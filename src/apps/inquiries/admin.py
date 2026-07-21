import logging

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.users.roles import is_restricted_supplier_user

from .emails import send_customer_offer_cancelled_email, send_customer_offer_sent_email
from .models import (
    Inquiry,
    InquiryItem,
    InquiryOffer,
    InquiryOfferPayment,
    InquiryOfferPaymentDetails,
    InquirySubmissionGroup,
    InvoiceIssuerConfiguration,
    PaymentInvoiceLineSnapshot,
    PaymentInvoiceSnapshot,
)
from .payments import (
    StripeCheckoutSessionError,
    cancel_offer_with_remote_checkout_expiration,
    confirm_payment,
)

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


class GroupInquiryInline(admin.TabularInline):
    model = Inquiry
    extra = 0
    fields = ("inquiry_link", "status", "single_item", "created_at")
    readonly_fields = fields
    can_delete = False
    show_change_link = False

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description=_("Solicitud"))
    def inquiry_link(self, obj: Inquiry):
        if not obj.pk:
            return "—"
        url = reverse("admin:inquiries_inquiry_change", args=(obj.pk,))
        return format_html('<a href="{}">{}</a>', url, obj.reference_code)

    @admin.display(description=_("Producto"))
    def single_item(self, obj: Inquiry) -> str:
        item = obj.items.select_related("product").order_by("id").first()
        return f"{item.product.sku} · {item.product.title}" if item else "—"


@admin.register(InquirySubmissionGroup)
class InquirySubmissionGroupAdmin(InternalInquiryAccessMixin, admin.ModelAdmin):
    list_display = (
        "reference_code",
        "requester",
        "guest_email",
        "company_name",
        "destination_summary",
        "language",
        "inquiry_count",
        "created_at",
    )
    list_filter = ("language", "created_at")
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
        "destination_country",
        "destination_city",
        "destination_region",
        "destination_postal_code",
        "inquiries__reference_code",
    )
    ordering = ("-created_at",)
    list_select_related = ("user",)
    readonly_fields = (
        "reference_code",
        "user",
        "guest_name",
        "guest_email",
        "guest_phone",
        "company_name",
        "tax_id",
        "language",
        "notes_from_customer",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (_("Envío"), {"fields": ("reference_code", "language")}),
        (
            _("Datos del cliente"),
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
        (_("Notas del cliente"), {"fields": ("notes_from_customer",)}),
        (
            _("Destino de la oferta"),
            {
                "fields": (
                    "destination_country",
                    "destination_city",
                    "destination_region",
                    "destination_postal_code",
                )
            },
        ),
        (
            _("Fechas y auditoría"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )
    inlines = (GroupInquiryInline,)
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(inquiries_count=Count("inquiries"))

    @admin.display(description=_("Cliente"))
    def requester(self, obj: InquirySubmissionGroup) -> str:
        return obj.requester_display

    @admin.display(ordering="inquiries_count", description=_("Solicitudes"))
    def inquiry_count(self, obj: InquirySubmissionGroup) -> int:
        return obj.inquiries_count

    @admin.display(description=_("Destino"))
    def destination_summary(self, obj: InquirySubmissionGroup) -> str:
        return ", ".join(
            value
            for value in (
                obj.destination_postal_code,
                obj.destination_city,
                obj.destination_region,
                obj.destination_country.name,
            )
            if value
        ) or "—"


@admin.register(InquiryOffer)
class InquiryOfferAdmin(InternalInquiryAccessMixin, admin.ModelAdmin):
    LOCKED_AFTER_SEND_FIELDS = (
        "confirmed_total",
        "product_price",
        "shipping_price",
        "product_vat_applicable",
        "product_vat_rate",
        "product_tax_exemption_reason",
        "update_product_last_known_price",
        "shipping_vat_applicable",
        "shipping_vat_rate",
        "shipping_tax_exemption_reason",
        "currency",
        "quoted_destination_summary",
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
        "valid_until",
        "accepted_at",
        "rejected_at",
        "expired_at",
        "cancelled_at",
        "updated_at",
    )
    list_filter = (
        "status",
        "currency",
        "sent_at",
        "valid_until",
        "accepted_at",
        "rejected_at",
        "expired_at",
        "cancelled_at",
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
        "confirmed_total_display",
        "confirmed_total",
        "access_token",
        "sent_at",
        "valid_until",
        "validity_hours_snapshot",
        "accepted_at",
        "rejected_at",
        "expired_at",
        "cancelled_at",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"
    actions = (
        "mark_selected_as_sent",
        "resend_offer_email_to_customer",
        "initiate_payment_for_selected_offers",
        "cancel_selected_offers",
    )
    fieldsets = (
        (
            _("Oferta comercial"),
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
            _("Datos comerciales"),
            {
                "fields": (
                    "product_price",
                    "product_vat_applicable",
                    "product_vat_rate",
                    "product_tax_exemption_reason",
                    "update_product_last_known_price",
                    "shipping_price",
                    "shipping_vat_applicable",
                    "shipping_vat_rate",
                    "shipping_tax_exemption_reason",
                    "confirmed_total_display",
                    "currency",
                    "lead_time_text",
                    "customer_message",
                    "internal_notes",
                    "cancellation_internal_reason",
                    "cancellation_customer_message",
                )
            },
        ),
        (
            _("Destino de la oferta"),
            {
                "fields": (
                    "quoted_destination_country",
                    "quoted_destination_city",
                    "quoted_destination_region",
                    "quoted_destination_postal_code",
                )
            },
        ),
        (
            _("Ciclo de vida"),
            {
                "fields": (
                    "sent_at",
                    "valid_until",
                    "validity_hours_snapshot",
                    "accepted_at",
                    "rejected_at",
                    "expired_at",
                    "cancelled_at",
                )
            },
        ),
        (
            _("Fechas y auditoría"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj is not None and obj.status == InquiryOffer.Status.DRAFT:
            readonly_fields = [field for field in readonly_fields if field != "confirmed_total"]
        elif obj is not None:
            readonly_fields.extend(self.LOCKED_AFTER_SEND_FIELDS)
        if obj is not None and obj.has_complete_quoted_destination:
            readonly_fields.extend(
                (
                    "quoted_destination_country",
                    "quoted_destination_city",
                    "quoted_destination_region",
                    "quoted_destination_postal_code",
                )
            )
        return tuple(dict.fromkeys(readonly_fields))

    @admin.display(description=_("Precio total con IVA"))
    def confirmed_total_display(self, obj: InquiryOffer) -> str:
        return f"{obj.confirmed_total} {obj.currency}" if obj else "—"

    @admin.display(ordering="inquiry__reference_code", description=_("Solicitud"))
    def inquiry_reference(self, obj: InquiryOffer) -> str:
        return obj.inquiry.reference_code

    @admin.display(description=_("Pago"))
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

    @admin.action(description=_("Enviar las ofertas seleccionadas a los clientes"))
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
                    _("La oferta %(reference)s no está lista para enviar (%(details)s).")
                    % {"reference": offer.reference_code, "details": details},
                    level=messages.ERROR,
                )
            except ValueError:
                skipped_count += 1
                self.message_user(
                    request,
                    _("La oferta %(reference)s no puede enviarse desde su estado actual.")
                    % {"reference": offer.reference_code},
                    level=messages.WARNING,
                )
            else:
                sent_count += 1

        if sent_count:
            self.message_user(
                request, _("Ofertas enviadas: %(count)s.") % {"count": sent_count}
            )
        if skipped_count and not sent_count:
            self.message_user(request, _("No se envió ninguna oferta."), level=messages.WARNING)

    @admin.action(description=_("Reenviar el correo de oferta a los clientes"))
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
                        _("Se omitió la oferta %(reference)s: solo pueden reenviarse "
                          "ofertas enviadas o aceptadas.")
                        % {"reference": offer.reference_code}
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
                        _("No se pudo reenviar el correo de la oferta %(reference)s "
                          "por un error de entrega.")
                        % {"reference": offer.reference_code}
                    ),
                    level=messages.ERROR,
                )
                continue

            if not email_sent:
                skipped_count += 1
                self.message_user(
                    request,
                    (
                        _("No se pudo reenviar la oferta %(reference)s porque falta "
                          "el correo electrónico del cliente.")
                        % {"reference": offer.reference_code}
                    ),
                    level=messages.WARNING,
                )
                continue

            resent_count += 1

        if resent_count:
            self.message_user(
                request, _("Correos de oferta reenviados: %(count)s.") % {"count": resent_count}
            )
        if failed_count and not resent_count:
            self.message_user(
                request,
                _("No se reenvió ningún correo de oferta debido a errores de entrega."),
                level=messages.ERROR,
            )
        elif skipped_count and not resent_count and not failed_count:
            self.message_user(
                request,
                _("No se reenvió ningún correo de oferta."),
                level=messages.WARNING,
            )

    @admin.action(description=_("Iniciar el pago de las ofertas seleccionadas"))
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
                        _("No se pudo iniciar el pago de la oferta %(reference)s "
                          "(%(details)s).")
                        % {"reference": offer.reference_code, "details": details}
                    ),
                    level=messages.ERROR,
                )
            except ValueError as error:
                skipped_count += 1
                self.message_user(
                    request,
                    (
                        _("No se pudo iniciar el pago de la oferta %(reference)s "
                          "(%(error)s).")
                        % {"reference": offer.reference_code, "error": error}
                    ),
                    level=messages.WARNING,
                )
            else:
                initiated_count += 1

        if initiated_count:
            self.message_user(
                request, _("Pagos iniciados: %(count)s.") % {"count": initiated_count}
            )
        if skipped_count and not initiated_count:
            self.message_user(
                request,
                _("No se inició ningún pago."),
                level=messages.WARNING,
            )

    @admin.action(description=_("Cancelar las ofertas y notificar a los clientes"))
    def cancel_selected_offers(self, request, queryset):
        cancelled_count = 0
        skipped_count = 0
        for offer in queryset.select_related("inquiry", "inquiry__user"):
            try:
                offer = cancel_offer_with_remote_checkout_expiration(offer)
            except (ValidationError, ValueError, StripeCheckoutSessionError) as error:
                skipped_count += 1
                details = (
                    self._render_validation_error(error)
                    if isinstance(error, ValidationError)
                    else str(error)
                )
                self.message_user(
                    request,
                    _("No se canceló la oferta %(reference)s (%(details)s).")
                    % {"reference": offer.reference_code, "details": details},
                    level=messages.WARNING,
                )
                continue
            try:
                send_customer_offer_cancelled_email(offer)
            except Exception:
                logger.exception(
                    "Failed to send offer cancellation email (offer=%s).",
                    offer.reference_code,
                )
                self.message_user(
                    request,
                    _("La oferta %(reference)s se canceló, pero falló el correo al cliente.")
                    % {"reference": offer.reference_code},
                    level=messages.ERROR,
                )
            cancelled_count += 1
        if cancelled_count:
            self.message_user(
                request,
                _("Ofertas canceladas: %(count)s.") % {"count": cancelled_count},
            )
        elif skipped_count:
            self.message_user(request, _("No se canceló ninguna oferta."), level=messages.WARNING)


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
        "provider_transaction_reference",
        "initiated_at",
        "checkout_expires_at",
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
        "checkout_expires_at",
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
        "provider_transaction_reference",
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
        "checkout_expires_at",
        "paid_at",
        "failed_at",
        "cancelled_at",
        "created_at",
        "updated_at",
        "invoice_snapshot_summary",
        "invoice_lines_summary",
    )
    date_hierarchy = "created_at"
    actions = (
        "mark_selected_as_paid",
        "mark_selected_as_failed",
        "mark_selected_as_cancelled",
    )
    fieldsets = (
        (
            _("Pago"),
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
            _("Proveedor de pago"),
            {
                "fields": (
                    "provider",
                    "provider_reference",
                    "provider_transaction_reference",
                    "internal_notes",
                )
            },
        ),
        (
            _("Datos preparados para facturar"),
            {"fields": ("invoice_snapshot_summary", "invoice_lines_summary")},
        ),
        (
            _("Ciclo de vida"),
            {
                "fields": (
                    "initiated_at",
                    "checkout_expires_at",
                    "paid_at",
                    "failed_at",
                    "cancelled_at",
                )
            },
        ),
        (
            _("Fechas y auditoría"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def has_add_permission(self, request):
        return False

    @admin.display(ordering="offer__reference_code", description=_("Oferta"))
    def offer_reference(self, obj: InquiryOfferPayment) -> str:
        return obj.offer.reference_code

    @admin.display(ordering="offer__inquiry__reference_code", description=_("Solicitud"))
    def inquiry_reference(self, obj: InquiryOfferPayment) -> str:
        return obj.offer.inquiry.reference_code

    @admin.display(description=_("Resumen fiscal"))
    def invoice_snapshot_summary(self, obj):
        snapshot = getattr(obj, "invoice_snapshot", None)
        if snapshot is None:
            return _("Todavía no existe snapshot fiscal.")
        return format_html(
            "{}<br>{}: {} · {}<br>{}: {}<br>{}: {} + {} = {} {}<br>{}: {} · {}",
            snapshot.customer_name,
            _("NIF/VAT"), snapshot.customer_tax_id, snapshot.customer_email,
            _("Domicilio"), snapshot.customer_address_line_1,
            _("Totales"), snapshot.net_total, snapshot.tax_total,
            snapshot.grand_total, snapshot.currency,
            _("Emisor"), snapshot.issuer_legal_name, snapshot.issuer_tax_id,
        )

    @admin.display(description=_("Líneas fiscales"))
    def invoice_lines_summary(self, obj):
        snapshot = getattr(obj, "invoice_snapshot", None)
        if snapshot is None:
            return "—"
        rows = [
            f"{line.description}: {line.quantity} × {line.unit_net_price} · "
            f"IVA {line.tax_rate}% ({line.tax_amount}) · {line.gross_amount} {snapshot.currency}"
            for line in snapshot.lines.all()
        ]
        return format_html("<br>".join("{}" for _row in rows), *rows)

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
            try:
                if transition_method == "mark_paid":
                    confirm_payment(payment)
                else:
                    getattr(payment, transition_method)(save=True)
            except ValidationError as error:
                skipped_count += 1
                details = InquiryOfferAdmin._render_validation_error(error)
                self.message_user(
                    request,
                    (
                        _("El pago %(reference)s no pudo cambiar a %(status)s "
                          "(%(details)s).")
                        % {
                            "reference": payment.reference_code,
                            "status": transition_label,
                            "details": details,
                        }
                    ),
                    level=messages.ERROR,
                )
            except ValueError as error:
                skipped_count += 1
                self.message_user(
                    request,
                    (
                        _("El pago %(reference)s no pudo cambiar a %(status)s "
                          "(%(error)s).")
                        % {
                            "reference": payment.reference_code,
                            "status": transition_label,
                            "error": error,
                        }
                    ),
                    level=messages.WARNING,
                )
            else:
                transitioned_count += 1

        if transitioned_count:
            self.message_user(
                request,
                _("Pagos actualizados a %(status)s: %(count)s.")
                % {"status": transition_label, "count": transitioned_count},
            )
        if skipped_count and not transitioned_count:
            self.message_user(
                request,
                _("No se actualizó ningún pago a %(status)s.")
                % {"status": transition_label},
                level=messages.WARNING,
            )

    @admin.action(description=_("Marcar los pagos seleccionados como pagados"))
    def mark_selected_as_paid(self, request, queryset):
        self._transition_selected(
            request,
            queryset,
            transition_method="mark_paid",
            transition_label=_("pagado"),
        )

    @admin.action(description=_("Marcar los pagos seleccionados como fallidos"))
    def mark_selected_as_failed(self, request, queryset):
        self._transition_selected(
            request,
            queryset,
            transition_method="mark_failed",
            transition_label=_("fallido"),
        )

    @admin.action(description=_("Marcar los pagos seleccionados como cancelados"))
    def mark_selected_as_cancelled(self, request, queryset):
        self._transition_selected(
            request,
            queryset,
            transition_method="mark_cancelled",
            transition_label=_("cancelado"),
        )


@admin.register(InquiryOfferPaymentDetails)
class InquiryOfferPaymentDetailsAdmin(InternalInquiryAccessMixin, admin.ModelAdmin):
    list_display = (
        "payment_reference",
        "offer_reference",
        "inquiry_reference",
        "shipping_recipient_name",
        "delivery_destination_summary",
        "billing_name",
        "completed_at",
        "updated_at",
    )
    search_fields = (
        "payment__reference_code",
        "payment__offer__reference_code",
        "payment__offer__inquiry__reference_code",
        "shipping_recipient_name",
        "billing_name",
        "billing_tax_id",
    )
    list_select_related = ("payment", "payment__offer", "payment__offer__inquiry")
    readonly_fields = tuple(
        field.name for field in InquiryOfferPaymentDetails._meta.fields
    ) + ("offer_reference", "inquiry_reference")
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    @admin.display(ordering="payment__reference_code", description=_("Pago"))
    def payment_reference(self, obj):
        return obj.payment.reference_code

    @admin.display(ordering="payment__offer__reference_code", description=_("Oferta"))
    def offer_reference(self, obj):
        return obj.payment.offer.reference_code

    @admin.display(ordering="payment__offer__inquiry__reference_code", description=_("Solicitud"))
    def inquiry_reference(self, obj):
        return obj.payment.offer.inquiry.reference_code


@admin.register(InvoiceIssuerConfiguration)
class InvoiceIssuerConfigurationAdmin(InternalInquiryAccessMixin, admin.ModelAdmin):
    fieldsets = (
        (_("Identidad fiscal"), {"fields": ("legal_name", "tax_id")}),
        (_("Domicilio fiscal"), {"fields": (
            "address_line_1", "address_line_2", "city", "region", "postal_code", "country",
        )}),
        (_("Contacto"), {"fields": ("email", "phone")}),
    )

    def has_add_permission(self, request):
        return (
            not InvoiceIssuerConfiguration.objects.exists()
            and super().has_add_permission(request)
        )

    def has_delete_permission(self, request, obj=None):
        return False


class PaymentInvoiceLineSnapshotInline(admin.TabularInline):
    model = PaymentInvoiceLineSnapshot
    extra = 0
    can_delete = False
    fields = tuple(field.name for field in PaymentInvoiceLineSnapshot._meta.fields)
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PaymentInvoiceSnapshot)
class PaymentInvoiceSnapshotAdmin(InternalInquiryAccessMixin, admin.ModelAdmin):
    list_display = ("payment_reference", "customer_name", "grand_total", "currency", "paid_at")
    search_fields = (
        "payment_reference",
        "offer_reference",
        "inquiry_reference",
        "customer_name",
        "customer_tax_id",
    )
    fields = tuple(field.name for field in PaymentInvoiceSnapshot._meta.fields)
    readonly_fields = fields
    inlines = (PaymentInvoiceLineSnapshotInline,)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentInvoiceLineSnapshot)
class PaymentInvoiceLineSnapshotAdmin(InternalInquiryAccessMixin, admin.ModelAdmin):
    list_display = ("snapshot", "line_type", "description", "quantity", "gross_amount")
    fields = tuple(field.name for field in PaymentInvoiceLineSnapshot._meta.fields)
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Inquiry)
class InquiryAdmin(InternalInquiryAccessMixin, admin.ModelAdmin):
    NEGATIVE_RESOLUTION_FIELDS = (
        "negative_resolution_reason",
        "negative_resolution_internal_notes",
        "negative_resolution_customer_message",
    )

    list_display = (
        "reference_code",
        "submission_group_reference",
        "status",
        "destination_summary",
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
        "submission_group__reference_code",
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
    list_select_related = ("user", "submission_group")
    autocomplete_fields = ("user",)
    readonly_fields = ("reference_code", "submission_group_link", "created_at", "updated_at")
    date_hierarchy = "created_at"
    inlines = (InquiryItemInline,)
    actions = ("finalize_selected_as_not_offerable",)
    fieldsets = (
        (
            _("Solicitud"),
            {
                "fields": (
                    "reference_code",
                    "submission_group_link",
                    "status",
                    "language",
                )
            },
        ),
        (
            _("Destino de la oferta"),
            {
                "fields": (
                    "destination_country",
                    "destination_city",
                    "destination_region",
                    "destination_postal_code",
                )
            },
        ),
        (
            _("Datos del cliente"),
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
            _("Seguimiento"),
            {
                "fields": (
                    "response_due_at",
                    "supplier_feedback_at",
                )
            },
        ),
        (
            _("Notas"),
            {
                "fields": (
                    "notes_from_customer",
                    "internal_notes",
                )
            },
        ),
        (
            _("Resolución no ofertable"),
            {
                "fields": (
                    "negative_resolution_reason",
                    "negative_resolution_internal_notes",
                    "negative_resolution_customer_message",
                    "negative_resolved_at",
                )
            },
        ),
        (
            _("Fechas y auditoría"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        readonly_fields.append("negative_resolved_at")
        if obj is not None and obj.negative_resolved_at is not None:
            readonly_fields.extend(self.NEGATIVE_RESOLUTION_FIELDS)
        return tuple(dict.fromkeys(readonly_fields))

    @admin.display(description=_("Destino"))
    def destination_summary(self, obj: Inquiry) -> str:
        return ", ".join(
            value
            for value in (
                obj.destination_postal_code,
                obj.destination_city,
                obj.destination_region,
                obj.destination_country.name,
            )
            if value
        ) or "—"

    @staticmethod
    def _render_validation_error(error: ValidationError) -> str:
        if hasattr(error, "message_dict"):
            parts = []
            for field_name, field_errors in error.message_dict.items():
                parts.extend(f"{field_name}: {message}" for message in field_errors)
            return "; ".join(parts)
        return "; ".join(error.messages)

    @admin.action(description=_("Finalizar las solicitudes seleccionadas como no ofertables"))
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
                        _("La solicitud %(reference)s no pudo finalizarse como no "
                          "ofertable (%(details)s).")
                        % {"reference": inquiry.reference_code, "details": details}
                    ),
                    level=messages.ERROR,
                )
            except ValueError as error:
                skipped_count += 1
                self.message_user(
                    request,
                    (
                        _("La solicitud %(reference)s no pudo finalizarse como no "
                          "ofertable (%(error)s).")
                        % {"reference": inquiry.reference_code, "error": error}
                    ),
                    level=messages.WARNING,
                )
            else:
                finalized_count += 1

        if finalized_count:
            self.message_user(
                request,
                _("Solicitudes finalizadas como no ofertables: %(count)s.")
                % {"count": finalized_count},
            )
        if skipped_count and not finalized_count:
            self.message_user(
                request,
                _("No se finalizó ninguna solicitud como no ofertable."),
                level=messages.WARNING,
            )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(items_count=Count("items"))

    @admin.display(description=_("Cliente"))
    def requester(self, obj: Inquiry) -> str:
        return obj.requester_display

    @admin.display(
        ordering="submission_group__reference_code",
        description=_("Grupo de solicitudes"),
    )
    def submission_group_reference(self, obj: Inquiry) -> str:
        return obj.submission_group.reference_code if obj.submission_group_id else "—"

    @admin.display(description=_("Grupo de solicitudes"))
    def submission_group_link(self, obj: Inquiry):
        if not obj.submission_group_id:
            return "—"
        url = reverse(
            "admin:inquiries_inquirysubmissiongroup_change",
            args=(obj.submission_group_id,),
        )
        return format_html('<a href="{}">{}</a>', url, obj.submission_group.reference_code)

    @admin.display(ordering="items_count", description=_("Artículos"))
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
