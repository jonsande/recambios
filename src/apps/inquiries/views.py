from __future__ import annotations

import logging

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import FormView, TemplateView, View

from apps.cart.services import clear_request_cart, get_request_cart_items

from .deadlines import expire_offer_if_due, expire_payment_if_due
from .forms import PublicInquirySubmissionForm
from .models import Inquiry, InquiryItem, InquiryOffer, InquiryOfferPayment
from .payments import (
    StripeCheckoutSessionError,
    StripeConfigurationError,
    StripeWebhookPayloadError,
    StripeWebhookSignatureError,
    construct_stripe_webhook_event,
    create_or_reuse_checkout_session_for_offer,
    process_stripe_checkout_event,
)

logger = logging.getLogger(__name__)


class PublicInquirySubmitView(FormView):
    template_name = "inquiries/public_submit.html"
    form_class = PublicInquirySubmissionForm

    def dispatch(self, request, *args, **kwargs):
        if not get_request_cart_items(request.session):
            messages.error(
                request,
                _("Su carrito de solicitud está vacío. Añada al menos un producto para continuar."),
            )
            return redirect("cart:request_cart_detail")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cart_items = get_request_cart_items(self.request.session)
        (
            offer_response_deadline_hours,
            payment_deadline_hours,
        ) = _resolve_deadline_hours_for_cart_items(cart_items)
        context.update(
            {
                "page_title": _("Enviar solicitud"),
                "cart_items": cart_items,
                "total_quantity": sum(item.quantity for item in cart_items),
                "offer_response_deadline_hours": offer_response_deadline_hours,
                "payment_deadline_hours": payment_deadline_hours,
            }
        )
        return context

    def form_valid(self, form):
        cart_items = get_request_cart_items(self.request.session)
        if not cart_items:
            form.add_error(
                None,
                _("Su carrito de solicitud está vacío. Añada productos antes de enviar."),
            )
            return self.form_invalid(form)

        try:
            inquiry = self._create_submitted_inquiry(form.cleaned_data, cart_items)
        except (ValidationError, IntegrityError, ValueError):
            logger.exception("Public inquiry submission failed due to invalid payload.")
            form.add_error(
                None,
                _(
                    "No se ha podido registrar su solicitud. "
                    "Revise los datos del carrito e inténtelo de nuevo."
                ),
            )
            return self.form_invalid(form)

        clear_request_cart(self.request.session)

        messages.success(
            self.request,
            _("Solicitud enviada correctamente. Referencia: %(reference)s")
            % {"reference": inquiry.reference_code},
        )
        return redirect(
            "inquiries:public_inquiry_success",
            reference_code=inquiry.reference_code,
        )

    def _create_submitted_inquiry(self, cleaned_data: dict, cart_items) -> Inquiry:
        user = self.request.user if self.request.user.is_authenticated else None

        with transaction.atomic():
            inquiry = Inquiry.objects.create(
                user=user,
                guest_name=cleaned_data["contact_name"],
                guest_email=cleaned_data["contact_email"],
                guest_phone=cleaned_data["phone"],
                company_name=cleaned_data["company_name"],
                tax_id=cleaned_data["tax_id"],
                language=_resolve_inquiry_language(),
                status=Inquiry.Status.DRAFT,
                notes_from_customer=cleaned_data["notes_from_customer"],
            )

            for cart_item in cart_items:
                InquiryItem.objects.create(
                    inquiry=inquiry,
                    product=cart_item.product,
                    requested_quantity=cart_item.quantity,
                    customer_note=cart_item.note,
                )

            inquiry.transition_to(Inquiry.Status.SUBMITTED)
            inquiry.save()

        return inquiry


class PublicInquirySuccessView(TemplateView):
    template_name = "inquiries/public_success.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        reference_code = (self.kwargs.get("reference_code") or "").strip()
        inquiry_exists = Inquiry.objects.filter(
            reference_code=reference_code,
            status__in=(
                Inquiry.Status.SUBMITTED,
                Inquiry.Status.SUPPLIER_PENDING,
            ),
        ).exists()
        if not inquiry_exists:
            raise Http404

        context.update(
            {
                "page_title": _("Solicitud enviada"),
                "inquiry_reference": reference_code,
            }
        )
        return context


class PublicInquiryOfferDetailView(TemplateView):
    template_name = "inquiries/public_offer_detail.html"

    def dispatch(self, request, *args, **kwargs):
        self.access_token = kwargs.get("access_token")
        if self.access_token is None:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def _get_offer(self, *, for_update: bool = False) -> InquiryOffer:
        queryset = InquiryOffer.objects.select_related("inquiry")
        if for_update:
            queryset = queryset.select_for_update()

        offer = queryset.filter(access_token=self.access_token).first()
        if offer is None:
            raise Http404
        return offer

    def get(self, request, *args, **kwargs):
        self.offer = self._get_offer()
        if expire_offer_if_due(self.offer):
            self.offer = self._get_offer()
        return super().get(request, *args, **kwargs)

    def get_template_names(self):
        if self.offer.status == InquiryOffer.Status.DRAFT:
            return ["inquiries/public_offer_unavailable.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.offer.status == InquiryOffer.Status.DRAFT:
            context.update(
                {
                    "page_title": _("Oferta no disponible"),
                }
            )
            return context

        page_title = _("Oferta confirmada")
        page_intro = _("Revise el importe confirmado y el plazo estimado antes de responder.")
        payment_deadline_at = None
        if self.offer.status == InquiryOffer.Status.ACCEPTED:
            page_title = _("Oferta aceptada")
            page_intro = _("Ha aceptado esta oferta. El siguiente paso es la gestión del pago.")
            payment = InquiryOfferPayment.objects.filter(offer_id=self.offer.pk).first()
            if payment is not None:
                payment_deadline_at = payment.payment_deadline_at
        elif self.offer.status == InquiryOffer.Status.REJECTED:
            page_title = _("Oferta rechazada")
            page_intro = _(
                "Ha rechazado esta oferta. Si necesita revisar alternativas, "
                "puede contactar con nuestro equipo."
            )
        elif self.offer.status == InquiryOffer.Status.EXPIRED:
            page_title = _("Oferta caducada")
            page_intro = _(
                "El plazo para responder a esta oferta ha vencido. Si sigue habiendo "
                "disponibilidad, puede solicitar una nueva oferta."
            )

        context.update(
            {
                "page_title": page_title,
                "page_intro": page_intro,
                "offer": self.offer,
                "can_respond": self.offer.status == InquiryOffer.Status.SENT,
                "is_accepted": self.offer.status == InquiryOffer.Status.ACCEPTED,
                "is_rejected": self.offer.status == InquiryOffer.Status.REJECTED,
                "is_expired": self.offer.status == InquiryOffer.Status.EXPIRED,
                "payment_deadline_at": payment_deadline_at,
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        decision = (request.POST.get("decision") or "").strip().lower()
        if decision not in {"accept", "reject"}:
            messages.error(request, _("La respuesta seleccionada no es válida."))
            return redirect(request.path)

        offer_snapshot = self._get_offer()
        if expire_offer_if_due(offer_snapshot):
            messages.info(
                request,
                _(
                    "El plazo para responder a esta oferta ha vencido. "
                    "Si sigue habiendo disponibilidad, puede solicitar una nueva oferta."
                ),
            )
            return redirect(request.path)

        with transaction.atomic():
            offer = self._get_offer(for_update=True)
            if offer.status != InquiryOffer.Status.SENT:
                messages.info(
                    request,
                    _(
                        "Esta oferta ya tiene una respuesta registrada. "
                        "Puede revisar su estado actual."
                    ),
                )
                return redirect(request.path)

            if decision == "accept":
                offer.mark_accepted(save=True)
                messages.success(
                    request,
                    _("Oferta aceptada. A continuación verá el siguiente paso para el pago."),
                )
                return redirect(
                    "inquiries:public_inquiry_offer_payment_placeholder",
                    access_token=offer.access_token,
                )
            else:
                offer.mark_rejected(save=True)
                messages.success(request, _("Ha rechazado la oferta."))

        return redirect(request.path)


class PublicInquiryOfferPaymentView(TemplateView):
    template_name = "inquiries/public_offer_payment_placeholder.html"

    def dispatch(self, request, *args, **kwargs):
        self.access_token = kwargs.get("access_token")
        if self.access_token is None:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def _get_offer(self) -> InquiryOffer:
        offer = (
            InquiryOffer.objects.select_related("inquiry")
            .filter(access_token=self.access_token)
            .first()
        )
        if offer is None:
            raise Http404
        return offer

    def get(self, request, *args, **kwargs):
        self.offer = self._get_offer()
        if expire_offer_if_due(self.offer):
            self.offer = self._get_offer()
        redirect_response = self._redirect_if_offer_not_accepted(request, offer=self.offer)
        if redirect_response is not None:
            return redirect_response
        self.payment = InquiryOfferPayment.ensure_pending_from_offer(self.offer, save=True)
        if expire_payment_if_due(self.payment):
            self.payment.refresh_from_db()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.offer = self._get_offer()
        if expire_offer_if_due(self.offer):
            self.offer = self._get_offer()
        redirect_response = self._redirect_if_offer_not_accepted(request, offer=self.offer)
        if redirect_response is not None:
            return redirect_response
        self.payment = InquiryOfferPayment.ensure_pending_from_offer(self.offer, save=True)
        if expire_payment_if_due(self.payment):
            messages.info(
                request,
                _(
                    "El plazo para pagar esta oferta ha vencido. "
                    "Si sigue habiendo disponibilidad, solicite una nueva oferta."
                ),
            )
            return redirect(request.path)
        if self.payment.status != InquiryOfferPayment.Status.PENDING:
            messages.info(
                request,
                _(
                    "Este pago ya no está pendiente. "
                    "Si necesita ayuda, contacte con nuestro equipo."
                ),
            )
            return redirect(request.path)

        try:
            checkout_result = create_or_reuse_checkout_session_for_offer(
                self.offer,
                language_code=request.LANGUAGE_CODE,
            )
        except StripeConfigurationError:
            logger.exception(
                "Stripe checkout initiation blocked due to configuration error (offer=%s).",
                self.offer.reference_code,
            )
            messages.error(
                request,
                _(
                    "El pago online no está disponible temporalmente. "
                    "Nuestro equipo ha sido notificado."
                ),
            )
            return redirect(request.path)
        except (StripeCheckoutSessionError, ValidationError, ValueError):
            logger.exception(
                "Stripe checkout initiation failed (offer=%s).",
                self.offer.reference_code,
            )
            messages.error(
                request,
                _(
                    "No se ha podido iniciar la pasarela de pago. "
                    "Inténtelo de nuevo en unos minutos."
                ),
            )
            return redirect(request.path)

        return redirect(checkout_result.session_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": _("Paso de pago"),
                "offer": self.offer,
                "payment": self.payment,
                "is_paid": self.payment.status == InquiryOfferPayment.Status.PAID,
                "can_start_checkout": self.payment.status == InquiryOfferPayment.Status.PENDING,
                "payment_deadline_at": self.payment.payment_deadline_at,
            }
        )
        return context

    @staticmethod
    def _redirect_if_offer_not_accepted(request, *, offer: InquiryOffer):
        if offer.status == InquiryOffer.Status.ACCEPTED:
            return None

        if offer.status == InquiryOffer.Status.SENT:
            messages.info(
                request,
                _(
                    "Esta oferta aún está pendiente de su respuesta. "
                    "Acepte la oferta para avanzar al pago."
                ),
            )
        elif offer.status == InquiryOffer.Status.REJECTED:
            messages.info(
                request,
                _(
                    "Esta oferta fue rechazada. Si necesita revisar "
                    "alternativas, contacte con nuestro equipo."
                ),
            )
        elif offer.status == InquiryOffer.Status.EXPIRED:
            messages.info(
                request,
                _(
                    "El plazo para responder a esta oferta ha vencido. "
                    "Si sigue habiendo disponibilidad, puede solicitar una nueva oferta."
                ),
            )
        else:
            messages.info(
                request,
                _("Esta oferta todavía no está disponible para continuar al paso de pago."),
            )
        return redirect(
            "inquiries:public_inquiry_offer_detail",
            access_token=offer.access_token,
        )


class PublicInquiryOfferPaymentSuccessView(TemplateView):
    template_name = "inquiries/public_offer_payment_success.html"

    def dispatch(self, request, *args, **kwargs):
        self.access_token = kwargs.get("access_token")
        if self.access_token is None:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def _get_offer(self) -> InquiryOffer:
        offer = (
            InquiryOffer.objects.select_related("inquiry")
            .filter(access_token=self.access_token)
            .first()
        )
        if offer is None:
            raise Http404
        return offer

    def get(self, request, *args, **kwargs):
        self.offer = self._get_offer()
        if expire_offer_if_due(self.offer):
            self.offer = self._get_offer()
        self.payment = InquiryOfferPayment.objects.filter(offer=self.offer).first()
        if self.payment is None:
            messages.info(
                request,
                _("No se ha encontrado un pago activo para esta oferta."),
            )
            return redirect(
                "inquiries:public_inquiry_offer_detail",
                access_token=self.offer.access_token,
            )
        if expire_payment_if_due(self.payment):
            self.payment.refresh_from_db()
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": _("Confirmación de pago"),
                "offer": self.offer,
                "payment": self.payment,
                "is_paid": self.payment.status == InquiryOfferPayment.Status.PAID,
            }
        )
        return context


class PublicInquiryOfferPaymentCancelView(TemplateView):
    template_name = "inquiries/public_offer_payment_cancel.html"

    def dispatch(self, request, *args, **kwargs):
        self.access_token = kwargs.get("access_token")
        if self.access_token is None:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def _get_offer(self) -> InquiryOffer:
        offer = (
            InquiryOffer.objects.select_related("inquiry")
            .filter(access_token=self.access_token)
            .first()
        )
        if offer is None:
            raise Http404
        return offer

    def get(self, request, *args, **kwargs):
        self.offer = self._get_offer()
        if expire_offer_if_due(self.offer):
            self.offer = self._get_offer()
        self.payment = InquiryOfferPayment.objects.filter(offer=self.offer).first()
        if self.payment is None:
            messages.info(
                request,
                _("No se ha encontrado un pago activo para esta oferta."),
            )
            return redirect(
                "inquiries:public_inquiry_offer_detail",
                access_token=self.offer.access_token,
            )
        if expire_payment_if_due(self.payment):
            self.payment.refresh_from_db()
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": _("Pago no completado"),
                "offer": self.offer,
                "payment": self.payment,
                "is_paid": self.payment.status == InquiryOfferPayment.Status.PAID,
            }
        )
        return context


@method_decorator(csrf_exempt, name="dispatch")
class StripeCheckoutWebhookView(View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        signature = (request.META.get("HTTP_STRIPE_SIGNATURE") or "").strip()
        if not signature:
            return HttpResponseBadRequest("Missing Stripe signature.")

        try:
            event = construct_stripe_webhook_event(request.body, signature)
        except StripeWebhookSignatureError:
            logger.warning("Stripe webhook rejected due to invalid signature.")
            return HttpResponseBadRequest("Invalid Stripe signature.")
        except StripeWebhookPayloadError:
            logger.warning("Stripe webhook rejected due to invalid payload.")
            return HttpResponseBadRequest("Invalid Stripe payload.")
        except StripeConfigurationError:
            logger.exception("Stripe webhook processing blocked by missing configuration.")
            return HttpResponse(status=500)
        except StripeCheckoutSessionError:
            logger.exception("Stripe webhook verification failed due to provider error.")
            return HttpResponse(status=502)

        try:
            process_stripe_checkout_event(event)
        except Exception:
            logger.exception("Stripe webhook event processing failed.")
            return HttpResponse(status=500)

        return HttpResponse(status=200)


def _resolve_inquiry_language() -> str:
    current_language = (get_language() or settings.LANGUAGE_CODE).lower()
    if current_language.startswith("en"):
        return Inquiry.Language.ENGLISH
    return Inquiry.Language.SPANISH


def _resolve_deadline_hours_for_cart_items(cart_items) -> tuple[int, int]:
    response_candidates: list[int] = []
    payment_candidates: list[int] = []
    seen_supplier_ids: set[int] = set()
    for item in cart_items:
        supplier = item.product.supplier
        if supplier.pk is None or supplier.pk in seen_supplier_ids:
            continue
        seen_supplier_ids.add(supplier.pk)
        if supplier.offer_response_deadline_hours > 0:
            response_candidates.append(supplier.offer_response_deadline_hours)
        if supplier.accepted_payment_deadline_hours > 0:
            payment_candidates.append(supplier.accepted_payment_deadline_hours)

    response_deadline_hours = min(response_candidates) if response_candidates else 24
    payment_deadline_hours = min(payment_candidates) if payment_candidates else 24
    return response_deadline_hours, payment_deadline_hours
