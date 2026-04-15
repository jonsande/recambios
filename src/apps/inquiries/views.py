from __future__ import annotations

import logging

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import redirect
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.views.generic import FormView, TemplateView

from apps.cart.services import clear_request_cart, get_request_cart_items

from .forms import PublicInquirySubmissionForm
from .models import Inquiry, InquiryItem, InquiryOffer, InquiryOfferPayment

logger = logging.getLogger(__name__)


class PublicInquirySubmitView(FormView):
    template_name = "inquiries/public_submit.html"
    form_class = PublicInquirySubmissionForm

    def dispatch(self, request, *args, **kwargs):
        if not get_request_cart_items(request.session):
            messages.error(
                request,
                _("Tu carrito de solicitud está vacío. Añade al menos un producto para continuar."),
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
        context.update(
            {
                "page_title": _("Enviar solicitud"),
                "cart_items": cart_items,
                "total_quantity": sum(item.quantity for item in cart_items),
            }
        )
        return context

    def form_valid(self, form):
        cart_items = get_request_cart_items(self.request.session)
        if not cart_items:
            form.add_error(
                None,
                _("Tu carrito de solicitud está vacío. Añade productos antes de enviar."),
            )
            return self.form_invalid(form)

        try:
            inquiry = self._create_submitted_inquiry(form.cleaned_data, cart_items)
        except (ValidationError, IntegrityError, ValueError):
            logger.exception("Public inquiry submission failed due to invalid payload.")
            form.add_error(
                None,
                _(
                    "No se ha podido registrar tu solicitud. "
                    "Revisa los datos del carrito e inténtalo de nuevo."
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
            status=Inquiry.Status.SUBMITTED,
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
        page_intro = _("Revisa el importe confirmado y el plazo estimado antes de responder.")
        if self.offer.status == InquiryOffer.Status.ACCEPTED:
            page_title = _("Oferta aceptada")
            page_intro = _("Has aceptado esta oferta. El siguiente paso es la gestión del pago.")
        elif self.offer.status == InquiryOffer.Status.REJECTED:
            page_title = _("Oferta rechazada")
            page_intro = _(
                "Has rechazado esta oferta. Si necesitas revisar alternativas, "
                "puedes contactar con nuestro equipo."
            )

        context.update(
            {
                "page_title": page_title,
                "page_intro": page_intro,
                "offer": self.offer,
                "can_respond": self.offer.status == InquiryOffer.Status.SENT,
                "is_accepted": self.offer.status == InquiryOffer.Status.ACCEPTED,
                "is_rejected": self.offer.status == InquiryOffer.Status.REJECTED,
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        decision = (request.POST.get("decision") or "").strip().lower()
        if decision not in {"accept", "reject"}:
            messages.error(request, _("La respuesta seleccionada no es válida."))
            return redirect(request.path)

        with transaction.atomic():
            offer = self._get_offer(for_update=True)
            if offer.status != InquiryOffer.Status.SENT:
                messages.info(
                    request,
                    _(
                        "Esta oferta ya tiene una respuesta registrada. "
                        "Puedes revisar su estado actual."
                    ),
                )
                return redirect(request.path)

            if decision == "accept":
                offer.mark_accepted(save=True)
                InquiryOfferPayment.ensure_pending_from_offer(offer, save=True)
                messages.success(
                    request,
                    _("Oferta aceptada. A continuación verás el siguiente paso para el pago."),
                )
                return redirect(
                    "inquiries:public_inquiry_offer_payment_placeholder",
                    access_token=offer.access_token,
                )
            else:
                offer.mark_rejected(save=True)
                messages.success(request, _("Has rechazado la oferta."))

        return redirect(request.path)


class PublicInquiryOfferPaymentPlaceholderView(TemplateView):
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
        if self.offer.status != InquiryOffer.Status.ACCEPTED:
            if self.offer.status == InquiryOffer.Status.SENT:
                messages.info(
                    request,
                    _(
                        "Esta oferta aún está pendiente de tu respuesta. "
                        "Acepta la oferta para avanzar al pago."
                    ),
                )
            elif self.offer.status == InquiryOffer.Status.REJECTED:
                messages.info(
                    request,
                    _(
                        "Esta oferta fue rechazada. Si necesitas revisar "
                        "alternativas, contacta con nuestro equipo."
                    ),
                )
            else:
                messages.info(
                    request,
                    _("Esta oferta todavía no está disponible para continuar al paso de pago."),
                )
            return redirect(
                "inquiries:public_inquiry_offer_detail",
                access_token=self.offer.access_token,
            )

        self.payment = InquiryOfferPayment.ensure_pending_from_offer(self.offer, save=True)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": _("Paso de pago"),
                "offer": self.offer,
                "payment": self.payment,
            }
        )
        return context


def _resolve_inquiry_language() -> str:
    current_language = (get_language() or settings.LANGUAGE_CODE).lower()
    if current_language.startswith("en"):
        return Inquiry.Language.ENGLISH
    return Inquiry.Language.SPANISH
