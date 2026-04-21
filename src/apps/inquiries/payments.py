from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace
from typing import Any
from urllib.parse import urljoin

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import translation

from .models import InquiryOffer, InquiryOfferPayment

logger = logging.getLogger(__name__)

STRIPE_PROVIDER = "stripe_checkout"
ZERO_DECIMAL_CURRENCIES = {
    "bif",
    "clp",
    "djf",
    "gnf",
    "jpy",
    "kmf",
    "krw",
    "mga",
    "pyg",
    "rwf",
    "ugx",
    "vnd",
    "vuv",
    "xaf",
    "xof",
    "xpf",
}


class StripePaymentError(Exception):
    pass


class StripeConfigurationError(StripePaymentError):
    pass


class StripeCheckoutSessionError(StripePaymentError):
    pass


class StripeWebhookSignatureError(StripePaymentError):
    pass


class StripeWebhookPayloadError(StripePaymentError):
    pass


@dataclass(frozen=True)
class StripeCheckoutSessionResult:
    payment: InquiryOfferPayment
    session_id: str
    session_url: str
    reused_existing_session: bool


def create_or_reuse_checkout_session_for_offer(
    offer: InquiryOffer,
    *,
    language_code: str | None = None,
) -> StripeCheckoutSessionResult:
    _require_stripe_secret_key()

    payment = InquiryOfferPayment.ensure_pending_from_offer(
        offer,
        provider=STRIPE_PROVIDER,
        save=True,
    )

    with transaction.atomic():
        payment = (
            InquiryOfferPayment.objects.select_related("offer", "offer__inquiry")
            .select_for_update()
            .get(pk=payment.pk)
        )
        if payment.status != InquiryOfferPayment.Status.PENDING:
            raise ValueError("Only pending payments can be processed through Stripe Checkout.")

        if payment.provider != STRIPE_PROVIDER:
            payment.provider = STRIPE_PROVIDER
            payment.save(update_fields=["provider", "updated_at"])

        reusable_session = _resolve_reusable_checkout_session(payment)
        if reusable_session is not None:
            session_id = str(_get_attr(reusable_session, "id", ""))
            session_url = str(_get_attr(reusable_session, "url", ""))
            if not session_id or not session_url:
                raise StripeCheckoutSessionError(
                    "Stripe reusable session response is missing id or url."
                )
            return StripeCheckoutSessionResult(
                payment=payment,
                session_id=session_id,
                session_url=session_url,
                reused_existing_session=True,
            )

        created_session = _create_checkout_session(payment, language_code=language_code)
        session_id = str(_get_attr(created_session, "id", ""))
        session_url = str(_get_attr(created_session, "url", ""))
        if not session_id or not session_url:
            raise StripeCheckoutSessionError(
                "Stripe checkout session response is missing id or url."
            )

        payment.provider = STRIPE_PROVIDER
        payment.provider_reference = session_id
        payment.save(update_fields=["provider", "provider_reference", "updated_at"])

        return StripeCheckoutSessionResult(
            payment=payment,
            session_id=session_id,
            session_url=session_url,
            reused_existing_session=False,
        )


def construct_stripe_webhook_event(payload: bytes, signature: str) -> dict[str, Any]:
    webhook_secret = _require_stripe_webhook_secret()
    stripe = _load_stripe_module()

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature,
            secret=webhook_secret,
        )
    except ValueError as error:
        raise StripeWebhookPayloadError("Invalid Stripe webhook payload.") from error
    except stripe.error.SignatureVerificationError as error:
        raise StripeWebhookSignatureError("Invalid Stripe webhook signature.") from error
    except stripe.error.StripeError as error:
        raise StripeCheckoutSessionError("Stripe webhook processing failed.") from error

    if isinstance(event, dict):
        return event
    if hasattr(event, "to_dict"):
        return event.to_dict()
    return dict(event)


def process_stripe_checkout_event(event: dict[str, Any]) -> bool:
    event_type = str(event.get("type", ""))
    data = event.get("data", {})
    if not isinstance(data, dict):
        return False
    payload = data.get("object", {})
    if not isinstance(payload, dict):
        return False

    payment = _resolve_payment_from_checkout_payload(payload)
    if payment is None:
        logger.warning(
            "Stripe webhook event could not be matched to an internal payment (type=%s).",
            event_type,
        )
        return False

    session_id = str(payload.get("id", "")).strip()
    payment_status = str(payload.get("payment_status", "")).strip().lower()

    with transaction.atomic():
        payment = (
            InquiryOfferPayment.objects.select_related("offer", "offer__inquiry")
            .select_for_update()
            .get(pk=payment.pk)
        )

        if payment.status == InquiryOfferPayment.Status.PAID:
            return False

        changed_fields: list[str] = []
        if payment.provider != STRIPE_PROVIDER:
            payment.provider = STRIPE_PROVIDER
            changed_fields.append("provider")
        if session_id and payment.provider_reference != session_id:
            payment.provider_reference = session_id
            changed_fields.append("provider_reference")

        is_paid_transition = (
            event_type == "checkout.session.completed" and payment_status == "paid"
        )
        if is_paid_transition:
            payment.mark_paid(save=False)
            payment.save()
            return True

        if changed_fields:
            payment.save(update_fields=[*changed_fields, "updated_at"])

    return False


def _resolve_reusable_checkout_session(payment: InquiryOfferPayment) -> Any | None:
    provider_reference = (payment.provider_reference or "").strip()
    if not provider_reference:
        return None

    session = _retrieve_checkout_session(provider_reference)
    if session is None:
        return None

    session_status = str(_get_attr(session, "status", "")).lower()
    payment_status = str(_get_attr(session, "payment_status", "")).lower()
    has_url = bool(str(_get_attr(session, "url", "")).strip())

    if session_status == "open" and payment_status in {"unpaid", "no_payment_required"} and has_url:
        return session
    return None


def _retrieve_checkout_session(session_id: str) -> Any | None:
    stripe = _load_stripe_module()
    stripe.api_key = _require_stripe_secret_key()

    try:
        return stripe.checkout.Session.retrieve(session_id)
    except stripe.error.InvalidRequestError:
        logger.warning("Stored Stripe checkout session not found (session=%s).", session_id)
        return None
    except stripe.error.StripeError as error:
        raise StripeCheckoutSessionError(
            "Stripe checkout session retrieval failed."
        ) from error


def _create_checkout_session(
    payment: InquiryOfferPayment,
    *,
    language_code: str | None,
) -> Any:
    stripe = _load_stripe_module()
    stripe.api_key = _require_stripe_secret_key()

    currency = payment.currency.lower()
    success_url = _build_offer_url(
        "inquiries:public_inquiry_offer_payment_success",
        access_token=payment.offer.access_token,
        language_code=language_code,
        query_string="?session_id={CHECKOUT_SESSION_ID}",
    )
    cancel_url = _build_offer_url(
        "inquiries:public_inquiry_offer_payment_cancel",
        access_token=payment.offer.access_token,
        language_code=language_code,
    )

    try:
        return stripe.checkout.Session.create(
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=payment.reference_code,
            metadata={
                "payment_reference": payment.reference_code,
                "offer_reference": payment.offer.reference_code,
                "inquiry_reference": payment.offer.inquiry.reference_code,
            },
            line_items=[
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": currency,
                        "unit_amount": _to_minor_units(
                            payment.payable_amount,
                            currency=currency,
                        ),
                        "product_data": {
                            "name": f"Offer {payment.offer.reference_code}",
                            "description": (
                                f"Inquiry {payment.offer.inquiry.reference_code} "
                                f"/ Payment {payment.reference_code}"
                            ),
                        },
                    },
                }
            ],
        )
    except stripe.error.StripeError as error:
        raise StripeCheckoutSessionError("Stripe checkout session creation failed.") from error


def _resolve_payment_from_checkout_payload(payload: dict[str, Any]) -> InquiryOfferPayment | None:
    metadata = payload.get("metadata", {})
    payment_reference = ""
    if isinstance(metadata, dict):
        payment_reference = str(metadata.get("payment_reference", "")).strip()
    if payment_reference:
        payment = (
            InquiryOfferPayment.objects.select_related("offer", "offer__inquiry")
            .filter(reference_code=payment_reference)
            .first()
        )
        if payment is not None:
            return payment

    session_id = str(payload.get("id", "")).strip()
    if session_id:
        return (
            InquiryOfferPayment.objects.select_related("offer", "offer__inquiry")
            .filter(provider_reference=session_id)
            .first()
        )
    return None


def _to_minor_units(amount: Decimal, *, currency: str) -> int:
    normalized_currency = currency.lower()
    if normalized_currency in ZERO_DECIMAL_CURRENCIES:
        return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return int((amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _build_offer_url(
    view_name: str,
    *,
    access_token: Any,
    language_code: str | None,
    query_string: str = "",
) -> str:
    public_base_url = (settings.PUBLIC_BASE_URL or "").strip()
    if not public_base_url:
        raise StripeConfigurationError(
            "PUBLIC_BASE_URL must be configured to build Stripe Checkout return URLs."
        )

    normalized_language = (language_code or "").strip().lower()
    if not normalized_language:
        normalized_language = settings.LANGUAGE_CODE

    with translation.override(normalized_language):
        path = reverse(view_name, kwargs={"access_token": access_token})

    absolute_url = urljoin(public_base_url.rstrip("/") + "/", path.lstrip("/"))
    return f"{absolute_url}{query_string}"


def _require_stripe_secret_key() -> str:
    secret_key = (settings.STRIPE_SECRET_KEY or "").strip()
    if not secret_key:
        raise StripeConfigurationError(
            "STRIPE_SECRET_KEY is not configured for Stripe Checkout integration."
        )
    return secret_key


def _require_stripe_webhook_secret() -> str:
    webhook_secret = (settings.STRIPE_WEBHOOK_SECRET or "").strip()
    if not webhook_secret:
        raise StripeConfigurationError(
            "STRIPE_WEBHOOK_SECRET is not configured for Stripe webhook verification."
        )
    return webhook_secret


def _load_stripe_module() -> Any:
    try:
        import stripe  # type: ignore[import-not-found]
    except ModuleNotFoundError as error:
        raise StripeConfigurationError(
            "The Stripe SDK is not installed. Add 'stripe' to Python dependencies."
        ) from error

    if not hasattr(stripe, "error"):
        stripe.error = SimpleNamespace(  # type: ignore[attr-defined]
            StripeError=Exception,
            SignatureVerificationError=ValueError,
            InvalidRequestError=Exception,
        )
    return stripe


def _get_attr(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
