from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace
from typing import Any
from urllib.parse import urljoin

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _

from .models import (
    InquiryOffer,
    InquiryOfferPayment,
    InquiryOfferPaymentDetails,
    InvoiceIssuerConfiguration,
    PaymentInvoiceLineSnapshot,
    PaymentInvoiceSnapshot,
)

logger = logging.getLogger(__name__)

STRIPE_PROVIDER = "stripe_checkout"
# V1 scope: keep webhook processing intentionally narrow and focused on Checkout paid confirmation.
RELEVANT_STRIPE_EVENT_TYPES = {
    "checkout.session.completed",
}
# V1 scope: conservative payment-method set for predictable production behavior.
STRIPE_V1_CHECKOUT_PAYMENT_METHOD_TYPES = ("card",)
STRIPE_MINIMUM_CHECKOUT_LIFETIME = timedelta(minutes=30)
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


def cancel_offer_with_remote_checkout_expiration(offer: InquiryOffer) -> InquiryOffer:
    """Cancel an offer only after making any active Stripe Checkout URL unusable."""
    with transaction.atomic():
        locked_offer = (
            InquiryOffer.objects.select_related("inquiry")
            .select_for_update()
            .get(pk=offer.pk)
        )
        payment = (
            InquiryOfferPayment.objects.select_for_update()
            .filter(offer_id=locked_offer.pk)
            .first()
        )
        if (
            payment is not None
            and payment.status == InquiryOfferPayment.Status.PENDING
            and payment.provider == STRIPE_PROVIDER
            and payment.provider_reference
        ):
            _expire_stripe_checkout_session(payment.provider_reference)
        locked_offer.mark_cancelled(save=True)
    return locked_offer


def create_or_reuse_checkout_session_for_offer(
    offer: InquiryOffer,
    *,
    language_code: str | None = None,
) -> StripeCheckoutSessionResult:
    """
    Prepare a Stripe Checkout attempt for an accepted offer.

    Internal payment rows stay one-per-offer. Every new attempt creates a fresh
    Checkout Session and updates the same payment record with the latest session reference.
    """
    _require_stripe_secret_key()
    InvoiceIssuerConfiguration.get_configured()
    offer.ensure_fiscally_ready()

    now = timezone.now()
    if offer.valid_until is None or now >= offer.valid_until:
        raise ValueError("Offer validity has expired.")

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
        now = timezone.now()
        if payment.offer.valid_until is None or now >= payment.offer.valid_until:
            raise ValueError("Offer validity has expired.")
        try:
            details = payment.checkout_details
        except InquiryOfferPaymentDetails.DoesNotExist as error:
            raise ValueError("Completed shipping and billing details are required.") from error
        if not details.is_complete or not details.matches_quoted_destination:
            raise ValueError(
                "Completed shipping and billing details matching the quoted "
                "destination are required."
            )

        if payment.provider != STRIPE_PROVIDER:
            payment.provider = STRIPE_PROVIDER
            payment.save(update_fields=["provider", "updated_at"])

        checkout_expires_at = max(
            payment.offer.valid_until,
            now + STRIPE_MINIMUM_CHECKOUT_LIFETIME,
        )
        created_session = _create_checkout_session(
            payment,
            language_code=language_code,
            expires_at=checkout_expires_at,
        )
        session_id = str(_get_attr(created_session, "id", ""))
        session_url = str(_get_attr(created_session, "url", ""))
        if not session_id or not session_url:
            raise StripeCheckoutSessionError(
                "Stripe checkout session response is missing id or url."
            )

        payment.provider = STRIPE_PROVIDER
        payment.provider_reference = session_id
        payment.checkout_expires_at = checkout_expires_at
        payment.save(
            update_fields=[
                "provider",
                "provider_reference",
                "checkout_expires_at",
                "updated_at",
            ]
        )

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
    if event_type not in RELEVANT_STRIPE_EVENT_TYPES:
        logger.debug("Stripe webhook event ignored as out of scope (type=%s).", event_type)
        return False

    data = event.get("data", {})
    if not isinstance(data, dict):
        logger.warning(
            "Stripe webhook event has invalid data payload for relevant type (type=%s).",
            event_type,
        )
        return False
    payload = data.get("object", {})
    if not isinstance(payload, dict):
        logger.warning(
            "Stripe webhook event has invalid object payload for relevant type (type=%s).",
            event_type,
        )
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
    event_created = _stripe_timestamp(event.get("created"))

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
            if changed_fields:
                payment.save(update_fields=[*changed_fields, "updated_at"])
            if payment.offer.status == InquiryOffer.Status.CANCELLED:
                logger.error(
                    "Stripe paid event rejected for commercially cancelled offer (payment=%s).",
                    payment.reference_code,
                )
                return False
            if (
                payment.checkout_expires_at is None
                or event_created is None
                or event_created > payment.checkout_expires_at
            ):
                logger.warning(
                    "Stripe paid event rejected outside checkout validity (payment=%s).",
                    payment.reference_code,
                )
                return False
            if payment.status == InquiryOfferPayment.Status.CANCELLED:
                offer = payment.offer
                offer.status = InquiryOffer.Status.ACCEPTED
                offer.expired_at = None
                offer.save(update_fields=["status", "expired_at", "updated_at"])
                inquiry = offer.inquiry
                inquiry.status = inquiry.Status.ACCEPTED
                inquiry.save(update_fields=["status", "updated_at"])
                payment.status = InquiryOfferPayment.Status.PENDING
                payment.cancelled_at = None
                payment.save(update_fields=["status", "cancelled_at", "updated_at"])
            confirm_payment(
                payment,
                provider_transaction_reference=str(payload.get("payment_intent", "")).strip(),
            )
            return True

        if changed_fields:
            payment.save(update_fields=[*changed_fields, "updated_at"])

    return False


def confirm_payment(
    payment: InquiryOfferPayment,
    *,
    provider_transaction_reference: str = "",
) -> PaymentInvoiceSnapshot | None:
    """Confirm a payment and atomically freeze all invoice-ready fiscal data."""
    with transaction.atomic():
        locked_payment = (
            InquiryOfferPayment.objects.select_for_update(of=("self",))
            .select_related("offer", "offer__inquiry", "offer__inquiry__user")
            .get(pk=payment.pk)
        )
        if locked_payment.status == InquiryOfferPayment.Status.PAID:
            return PaymentInvoiceSnapshot.objects.filter(payment=locked_payment).first()
        if locked_payment.status != InquiryOfferPayment.Status.PENDING:
            raise ValueError("Only pending payments can transition to paid.")

        issuer = InvoiceIssuerConfiguration.get_configured()
        locked_payment.offer.ensure_fiscally_ready()
        try:
            details = locked_payment.checkout_details
        except InquiryOfferPaymentDetails.DoesNotExist as error:
            raise ValidationError("Completed billing details are required.") from error
        if not details.is_complete:
            raise ValidationError("Completed billing details are required.")

        items = list(
            locked_payment.offer.inquiry.items.select_related("product").order_by("pk")[:2]
        )
        if len(items) != 1:
            raise ValidationError("Exactly one invoiceable product is required per payment.")

        if provider_transaction_reference:
            locked_payment.provider_transaction_reference = provider_transaction_reference
        locked_payment.mark_paid(save=False)
        locked_payment.save()

        offer = locked_payment.offer
        inquiry = offer.inquiry
        product_item = items[0]
        product_net = (offer.product_price or Decimal("0.00")).quantize(Decimal("0.01"))
        shipping_net = offer.shipping_price.quantize(Decimal("0.01"))
        product_gross = offer.product_price_with_vat
        shipping_gross = offer.shipping_price_with_vat
        net_total = product_net + shipping_net
        tax_total = (product_gross - product_net) + (shipping_gross - shipping_net)
        grand_total = product_gross + shipping_gross
        if grand_total != locked_payment.payable_amount:
            raise ValidationError("Invoice snapshot total does not match the paid amount.")

        customer_email = (
            inquiry.user.email if inquiry.user_id and inquiry.user.email else inquiry.guest_email
        )
        customer_phone = inquiry.guest_phone or details.shipping_phone
        snapshot = PaymentInvoiceSnapshot.objects.create(
            payment=locked_payment,
            payment_reference=locked_payment.reference_code,
            offer_reference=offer.reference_code,
            inquiry_reference=inquiry.reference_code,
            paid_at=locked_payment.paid_at,
            provider=locked_payment.provider,
            checkout_reference=locked_payment.provider_reference,
            transaction_reference=locked_payment.provider_transaction_reference,
            currency=locked_payment.currency,
            net_total=net_total,
            tax_total=tax_total,
            grand_total=grand_total,
            customer_type=details.billing_customer_type,
            customer_name=details.billing_identity_name,
            customer_tax_id=details.billing_tax_id,
            customer_email=customer_email,
            customer_phone=customer_phone,
            customer_address_line_1=details.billing_address_line_1,
            customer_address_line_2=details.billing_address_line_2,
            customer_city=details.billing_city,
            customer_region=details.billing_region,
            customer_postal_code=details.billing_postal_code,
            customer_country=details.billing_country,
            issuer_legal_name=issuer.legal_name,
            issuer_tax_id=issuer.tax_id,
            issuer_address_line_1=issuer.address_line_1,
            issuer_address_line_2=issuer.address_line_2,
            issuer_city=issuer.city,
            issuer_region=issuer.region,
            issuer_postal_code=issuer.postal_code,
            issuer_country=issuer.country,
            issuer_email=issuer.email,
            issuer_phone=issuer.phone,
        )
        product_tax_rate = offer.product_vat_rate if offer.product_vat_applicable else Decimal("0")
        shipping_tax_rate = (
            offer.shipping_vat_rate if offer.shipping_vat_applicable else Decimal("0")
        )
        PaymentInvoiceLineSnapshot.objects.create(
            snapshot=snapshot,
            line_type=PaymentInvoiceLineSnapshot.LineType.PRODUCT,
            sku=product_item.product.sku,
            description=product_item.product.title,
            quantity=product_item.requested_quantity,
            unit_net_price=(product_net / product_item.requested_quantity).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            ),
            net_amount=product_net,
            tax_rate=product_tax_rate,
            tax_amount=product_gross - product_net,
            gross_amount=product_gross,
            tax_exemption_reason=(
                offer.product_tax_exemption_reason if product_tax_rate == 0 else ""
            ),
        )
        PaymentInvoiceLineSnapshot.objects.create(
            snapshot=snapshot,
            line_type=PaymentInvoiceLineSnapshot.LineType.SHIPPING,
            description=str(_("Shipping")),
            quantity=1,
            unit_net_price=shipping_net,
            net_amount=shipping_net,
            tax_rate=shipping_tax_rate,
            tax_amount=shipping_gross - shipping_net,
            gross_amount=shipping_gross,
            tax_exemption_reason=(
                offer.shipping_tax_exemption_reason if shipping_tax_rate == 0 else ""
            ),
        )
        return snapshot


def _create_checkout_session(
    payment: InquiryOfferPayment,
    *,
    language_code: str | None,
    expires_at,
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
            payment_method_types=list(STRIPE_V1_CHECKOUT_PAYMENT_METHOD_TYPES),
            success_url=success_url,
            cancel_url=cancel_url,
            expires_at=int(expires_at.timestamp()),
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


def _expire_stripe_checkout_session(session_id: str) -> None:
    stripe = _load_stripe_module()
    stripe.api_key = _require_stripe_secret_key()
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        status = str(_get_attr(session, "status", "")).strip().lower()
        if status == "expired":
            return
        if status == "complete":
            raise StripeCheckoutSessionError(
                "Stripe Checkout Session is already complete; reconcile the payment "
                "before cancelling the offer."
            )
        if status != "open":
            raise StripeCheckoutSessionError(
                "Stripe Checkout Session status could not be confirmed as open or expired."
            )
        expired_session = stripe.checkout.Session.expire(session_id)
        if str(_get_attr(expired_session, "status", "")).strip().lower() != "expired":
            raise StripeCheckoutSessionError(
                "Stripe did not confirm that the Checkout Session was expired."
            )
    except StripeCheckoutSessionError:
        raise
    except stripe.error.StripeError as error:
        raise StripeCheckoutSessionError(
            "Stripe Checkout Session expiration failed."
        ) from error


def _stripe_timestamp(value: Any):
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.get_current_timezone())
    except (TypeError, ValueError, OverflowError):
        return None


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
