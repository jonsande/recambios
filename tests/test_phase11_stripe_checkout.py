from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Brand, Category, Condition, Product
from apps.inquiries.deadlines import expire_due_inquiry_deadlines
from apps.inquiries.forms import InquiryOfferPaymentDetailsForm
from apps.inquiries.models import (
    Inquiry,
    InquiryOffer,
    InquiryOfferPayment,
    InquiryOfferPaymentDetails,
)
from apps.inquiries.payments import (
    STRIPE_PROVIDER,
    StripeCheckoutSessionError,
    StripeCheckoutSessionResult,
    StripeConfigurationError,
    StripeWebhookPayloadError,
    StripeWebhookSignatureError,
    cancel_offer_with_remote_checkout_expiration,
    create_or_reuse_checkout_session_for_offer,
    process_stripe_checkout_event,
)
from apps.suppliers.models import Supplier


def make_supplier(
    code: str,
    *,
    auto_send_payment_paid_notification: bool = False,
    payment_paid_notification_email: str = "",
    send_payment_paid_notification_internal_copy: bool = False,
    offer_validity_hours: int = 24,
    auto_send_payment_expired_notification: bool = False,
    payment_expired_notification_email: str = "",
) -> Supplier:
    return Supplier.objects.create(
        name=f"Supplier {code}",
        slug=f"supplier-{code.lower()}",
        code=code,
        auto_send_payment_paid_notification=auto_send_payment_paid_notification,
        payment_paid_notification_email=payment_paid_notification_email,
        send_payment_paid_notification_internal_copy=send_payment_paid_notification_internal_copy,
        offer_validity_hours=offer_validity_hours,
        auto_send_payment_expired_notification=auto_send_payment_expired_notification,
        payment_expired_notification_email=payment_expired_notification_email,
    )


def make_product(sku: str, *, supplier: Supplier | None = None) -> Product:
    supplier = supplier or make_supplier(code=f"SUP-{sku}")
    brand = Brand.objects.create(name=f"Brand {sku}", slug=f"brand-{sku.lower()}")
    category = Category.objects.create(name=f"Category {sku}", slug=f"category-{sku.lower()}")
    condition = Condition.objects.create(
        code=f"cond-{sku.lower()}"[:32],
        name=f"Condition {sku}",
        slug=f"condition-{sku.lower()}",
    )
    return Product.objects.create(
        supplier=supplier,
        supplier_product_code=f"{supplier.code}-{sku}",
        sku=sku,
        slug=f"product-{sku.lower()}",
        title=f"Product {sku}",
        brand=brand,
        category=category,
        condition=condition,
        publication_status=Product.PublicationStatus.PUBLISHED,
        published_at=timezone.now(),
    )


def make_accepted_offer(
    django_user_model,
    *,
    username: str,
    confirmed_total: Decimal = Decimal("250.00"),
    supplier: Supplier | None = None,
) -> InquiryOffer:
    user = django_user_model.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="pass1234",
    )
    inquiry = Inquiry.objects.create(
        user=user,
        status=Inquiry.Status.IN_REVIEW,
        destination_country="ES",
        destination_city="Madrid",
        destination_region="Madrid",
        destination_postal_code="28001",
    )
    product = make_product(f"SKU-{username.upper()}", supplier=supplier)
    inquiry.items.create(product=product, requested_quantity=1)
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=confirmed_total,
        currency="EUR",
        lead_time_text="5 days",
    )
    offer.mark_sent(save=True)
    offer.mark_accepted(save=True)
    InquiryOfferPaymentDetails.objects.create(
        payment=offer.payment,
        shipping_recipient_name=user.get_username(),
        shipping_phone="+34 600 000 000",
        shipping_address_line_1="Calle Mayor 1",
        shipping_city="Madrid",
        shipping_region="Madrid",
        shipping_postal_code="28001",
        shipping_country="ES",
        billing_name=user.get_username(),
        billing_tax_id="12345678Z",
        billing_same_as_shipping=True,
        completed_at=timezone.now(),
    )
    return offer


@pytest.mark.django_db
def test_offer_cancellation_expires_active_remote_checkout_session(
    django_user_model,
    settings,
) -> None:
    settings.STRIPE_SECRET_KEY = "sk_test_cancel_remote"
    offer = make_accepted_offer(django_user_model, username="stripe_cancel_remote")
    payment = offer.payment
    payment.provider = STRIPE_PROVIDER
    payment.provider_reference = "cs_test_cancel_remote"
    payment.save(update_fields=["provider", "provider_reference", "updated_at"])
    offer.cancellation_internal_reason = "Supplier reports no stock"
    offer.cancellation_customer_message = "El producto ya no está disponible."
    offer.save()

    with (
        patch(
            "stripe.checkout.Session.retrieve",
            return_value={"id": "cs_test_cancel_remote", "status": "open"},
        ) as retrieve_session,
        patch(
            "stripe.checkout.Session.expire",
            return_value={"id": "cs_test_cancel_remote", "status": "expired"},
        ) as expire_session,
    ):
        cancelled_offer = cancel_offer_with_remote_checkout_expiration(offer)

    retrieve_session.assert_called_once_with("cs_test_cancel_remote")
    expire_session.assert_called_once_with("cs_test_cancel_remote")
    assert cancelled_offer.status == InquiryOffer.Status.CANCELLED
    payment.refresh_from_db()
    assert payment.status == InquiryOfferPayment.Status.CANCELLED


@pytest.mark.django_db
def test_offer_cancellation_is_blocked_when_remote_expiration_fails(
    django_user_model,
) -> None:
    offer = make_accepted_offer(django_user_model, username="stripe_cancel_failure")
    payment = offer.payment
    payment.provider = STRIPE_PROVIDER
    payment.provider_reference = "cs_test_cancel_failure"
    payment.save(update_fields=["provider", "provider_reference", "updated_at"])
    offer.cancellation_internal_reason = "Supplier reports no stock"
    offer.cancellation_customer_message = "El producto ya no está disponible."
    offer.save()

    with (
        patch(
            "apps.inquiries.payments._expire_stripe_checkout_session",
            side_effect=StripeCheckoutSessionError("Stripe unavailable"),
        ),
        pytest.raises(StripeCheckoutSessionError),
    ):
        cancel_offer_with_remote_checkout_expiration(offer)

    offer.refresh_from_db()
    payment.refresh_from_db()
    assert offer.status == InquiryOffer.Status.ACCEPTED
    assert payment.status == InquiryOfferPayment.Status.PENDING


@pytest.mark.django_db
def test_checkout_session_creation_persists_stripe_provider_reference(django_user_model) -> None:
    offer = make_accepted_offer(django_user_model, username="stripe_create_session")
    session = {
        "id": "cs_test_123",
        "url": "https://checkout.stripe.com/c/pay/cs_test_123",
        "status": "open",
        "payment_status": "unpaid",
    }

    with patch("apps.inquiries.payments._require_stripe_secret_key", return_value="sk_test"), patch(
        "apps.inquiries.payments._create_checkout_session",
        return_value=session,
    ):
        result = create_or_reuse_checkout_session_for_offer(offer, language_code="es")

    payment = InquiryOfferPayment.objects.get(offer=offer)
    assert result.session_id == "cs_test_123"
    assert result.session_url == "https://checkout.stripe.com/c/pay/cs_test_123"
    assert result.reused_existing_session is False
    assert payment.provider == STRIPE_PROVIDER
    assert payment.provider_reference == "cs_test_123"
    assert payment.checkout_expires_at == offer.valid_until


@pytest.mark.django_db
def test_checkout_started_in_last_30_minutes_gets_minimum_technical_window(
    django_user_model,
) -> None:
    offer = make_accepted_offer(django_user_model, username="stripe_min_window")
    offer.valid_until = timezone.now() + timedelta(minutes=10)
    offer.save(update_fields=["valid_until"])
    session = {
        "id": "cs_test_min_window",
        "url": "https://checkout.stripe.com/c/pay/cs_test_min_window",
    }

    with patch("apps.inquiries.payments._require_stripe_secret_key", return_value="sk_test"), patch(
        "apps.inquiries.payments._create_checkout_session",
        return_value=session,
    ) as create_mock:
        before = timezone.now()
        result = create_or_reuse_checkout_session_for_offer(offer, language_code="es")
        after = timezone.now()

    payment = result.payment
    assert before + timedelta(minutes=30) <= payment.checkout_expires_at
    assert payment.checkout_expires_at <= after + timedelta(minutes=30)
    assert create_mock.call_args.kwargs["expires_at"] == payment.checkout_expires_at


@pytest.mark.django_db
def test_checkout_cannot_start_after_offer_validity(django_user_model) -> None:
    offer = make_accepted_offer(django_user_model, username="stripe_expired_offer")
    offer.valid_until = timezone.now() - timedelta(seconds=1)
    offer.save(update_fields=["valid_until"])

    with patch("apps.inquiries.payments._require_stripe_secret_key", return_value="sk_test"), patch(
        "apps.inquiries.payments._create_checkout_session"
    ) as create_mock:
        with pytest.raises(ValueError, match="validity"):
            create_or_reuse_checkout_session_for_offer(offer, language_code="es")

    create_mock.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_active_checkout_window_defers_accepted_offer_expiry(django_user_model) -> None:
    offer = make_accepted_offer(django_user_model, username="stripe_expiry_deferred")
    payment = offer.payment
    now = timezone.now()
    offer.valid_until = now - timedelta(minutes=1)
    offer.save(update_fields=["valid_until"])
    payment.checkout_expires_at = now + timedelta(minutes=20)
    payment.save(update_fields=["checkout_expires_at"])

    active_summary = expire_due_inquiry_deadlines(now=now)
    offer.refresh_from_db()
    payment.refresh_from_db()
    assert active_summary == {"offers_expired": 0, "payments_expired": 0}
    assert offer.status == InquiryOffer.Status.ACCEPTED
    assert payment.status == InquiryOfferPayment.Status.PENDING

    expired_summary = expire_due_inquiry_deadlines(now=now + timedelta(minutes=21))
    offer.refresh_from_db()
    payment.refresh_from_db()
    assert expired_summary == {"offers_expired": 1, "payments_expired": 1}
    assert offer.status == InquiryOffer.Status.EXPIRED
    assert payment.status == InquiryOfferPayment.Status.CANCELLED


@pytest.mark.django_db
def test_checkout_details_form_prefills_locked_quoted_destination(django_user_model) -> None:
    offer = make_accepted_offer(django_user_model, username="quote_prefill")
    offer.payment.checkout_details.delete()

    form = InquiryOfferPaymentDetailsForm(payment=offer.payment)

    assert form["shipping_country"].value() == "ES"
    assert form["shipping_city"].value() == "Madrid"
    assert form["shipping_region"].value() == "Madrid"
    assert form["shipping_postal_code"].value() == "28001"
    assert form.fields["shipping_country"].disabled is True
    assert form.fields["shipping_city"].disabled is True
    assert form.fields["shipping_region"].disabled is True
    assert form.fields["shipping_postal_code"].disabled is True


@pytest.mark.django_db
def test_checkout_details_form_requires_billing_tax_id(django_user_model) -> None:
    offer = make_accepted_offer(django_user_model, username="billing_tax_id_required")
    offer.payment.checkout_details.delete()
    form = InquiryOfferPaymentDetailsForm(
        payment=offer.payment,
        data={
            "shipping_recipient_name": "María García",
            "shipping_phone": "+34 600 000 000",
            "shipping_address_line_1": "Calle Mayor 1",
            "shipping_city": "Madrid",
            "shipping_region": "Madrid",
            "shipping_postal_code": "28001",
            "shipping_country": "ES",
            "billing_customer_type": InquiryOfferPaymentDetails.BillingCustomerType.PRIVATE,
            "billing_same_as_shipping": "on",
            "billing_name": "María García",
            "billing_tax_id": "",
        },
    )

    assert form.is_valid() is False
    assert "billing_tax_id" in form.errors


@pytest.mark.django_db
def test_checkout_details_form_rejects_mismatched_billing_address_when_same(
    django_user_model,
) -> None:
    offer = make_accepted_offer(django_user_model, username="billing_address_mismatch")
    details = offer.payment.checkout_details
    form = InquiryOfferPaymentDetailsForm(
        payment=offer.payment,
        instance=details,
        data={
            "shipping_recipient_name": "María García",
            "shipping_phone": "+34 600 000 000",
            "shipping_address_line_1": "Calle Mayor 1",
            "billing_customer_type": InquiryOfferPaymentDetails.BillingCustomerType.PRIVATE,
            "billing_same_as_shipping": "on",
            "billing_name": "María García",
            "billing_tax_id": "12345678Z",
            "billing_address_line_1": "Calle Menor 2",
        },
    )

    assert form.is_valid() is False
    assert "billing_address_line_1" in form.errors
    assert "debe coincidir con la dirección de envío" in str(
        form.errors["billing_address_line_1"]
    )


@pytest.mark.django_db
def test_checkout_details_page_includes_billing_address_sync(client, django_user_model) -> None:
    offer = make_accepted_offer(django_user_model, username="billing_address_sync")

    response = client.get(
        reverse(
            "inquiries:public_inquiry_offer_payment_details",
            kwargs={"access_token": offer.access_token},
        )
    )

    assert response.status_code == 200
    assert b'data-billing-address-form' in response.content
    assert b'shippingLine1.addEventListener("input", copyShippingLine1)' in response.content
    assert b'role="alert"' in response.content


@pytest.mark.django_db
def test_checkout_details_model_requires_billing_tax_id(django_user_model) -> None:
    offer = make_accepted_offer(django_user_model, username="billing_tax_id_model")
    details = offer.payment.checkout_details
    details.billing_tax_id = ""

    with pytest.raises(ValidationError, match="Tax/VAT identifier is required for billing"):
        details.save()


@pytest.mark.django_db
def test_checkout_session_requires_completed_checkout_details(django_user_model) -> None:
    offer = make_accepted_offer(django_user_model, username="stripe_details_guard")
    offer.payment.checkout_details.delete()

    with patch("apps.inquiries.payments._require_stripe_secret_key", return_value="sk_test"), patch(
        "apps.inquiries.payments._create_checkout_session"
    ) as create_session:
        with pytest.raises(ValueError, match="shipping and billing details"):
            create_or_reuse_checkout_session_for_offer(offer, language_code="es")

    create_session.assert_not_called()


@pytest.mark.django_db
def test_paid_checkout_details_are_immutable(django_user_model) -> None:
    offer = make_accepted_offer(django_user_model, username="stripe_paid_details_lock")
    details = offer.payment.checkout_details
    offer.payment.mark_paid(save=True)
    details.shipping_city = "Barcelona"

    with pytest.raises(ValidationError, match="immutable snapshot"):
        details.save()


@pytest.mark.django_db
def test_checkout_session_initiation_is_blocked_for_non_accepted_offer(django_user_model) -> None:
    user = django_user_model.objects.create_user(
        username="stripe_not_accepted",
        email="stripe_not_accepted@example.com",
        password="pass1234",
    )
    inquiry = Inquiry.objects.create(
        user=user,
        status=Inquiry.Status.IN_REVIEW,
        destination_country="ES",
        destination_city="Madrid",
        destination_region="Madrid",
        destination_postal_code="28001",
    )
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("310.00"),
        currency="EUR",
        lead_time_text="4 days",
    )
    offer.mark_sent(save=True)

    with patch("apps.inquiries.payments._require_stripe_secret_key", return_value="sk_test"):
        with pytest.raises(ValueError):
            create_or_reuse_checkout_session_for_offer(offer, language_code="es")

    assert not InquiryOfferPayment.objects.filter(offer=offer).exists()


@pytest.mark.django_db
def test_checkout_session_is_idempotent_and_creates_new_session_each_attempt(
    django_user_model,
) -> None:
    offer = make_accepted_offer(django_user_model, username="stripe_idempotent")
    first_session = {
        "id": "cs_test_first",
        "url": "https://checkout.stripe.com/c/pay/cs_test_first",
        "status": "open",
        "payment_status": "unpaid",
    }
    second_session = {
        "id": "cs_test_second",
        "url": "https://checkout.stripe.com/c/pay/cs_test_second",
        "status": "open",
        "payment_status": "unpaid",
    }

    with patch("apps.inquiries.payments._require_stripe_secret_key", return_value="sk_test"), patch(
        "apps.inquiries.payments._create_checkout_session",
        side_effect=[first_session, second_session],
    ) as create_mock:
        first = create_or_reuse_checkout_session_for_offer(offer, language_code="es")
        second = create_or_reuse_checkout_session_for_offer(offer, language_code="es")

    payment = InquiryOfferPayment.objects.get(offer=offer)
    assert first.payment.pk == second.payment.pk
    assert first.session_id == "cs_test_first"
    assert second.session_id == "cs_test_second"
    assert first.reused_existing_session is False
    assert second.reused_existing_session is False
    assert payment.provider_reference == "cs_test_second"
    assert create_mock.call_count == 2
    assert InquiryOfferPayment.objects.filter(offer=offer).count() == 1


@pytest.mark.django_db
def test_checkout_retry_reuses_same_payment_record_without_duplicate_rows(
    django_user_model,
) -> None:
    offer = make_accepted_offer(django_user_model, username="stripe_retry")
    first_session = {
        "id": "cs_test_old",
        "url": "https://checkout.stripe.com/c/pay/cs_test_old",
        "status": "open",
        "payment_status": "unpaid",
    }
    retry_session = {
        "id": "cs_test_new",
        "url": "https://checkout.stripe.com/c/pay/cs_test_new",
        "status": "open",
        "payment_status": "unpaid",
    }

    with patch("apps.inquiries.payments._require_stripe_secret_key", return_value="sk_test"), patch(
        "apps.inquiries.payments._create_checkout_session",
        side_effect=[first_session, retry_session],
    ):
        first = create_or_reuse_checkout_session_for_offer(offer, language_code="es")
        second = create_or_reuse_checkout_session_for_offer(offer, language_code="es")

    payment = InquiryOfferPayment.objects.get(offer=offer)
    assert first.payment.pk == second.payment.pk
    assert first.session_id != second.session_id
    assert payment.provider_reference == "cs_test_new"
    assert InquiryOfferPayment.objects.filter(offer=offer).count() == 1


@pytest.mark.django_db
def test_checkout_session_creation_is_restricted_to_card_for_v1(django_user_model) -> None:
    offer = make_accepted_offer(django_user_model, username="stripe_card_only")
    captured_payload: dict = {}

    class _DummySession:
        @staticmethod
        def create(**kwargs):
            captured_payload.update(kwargs)
            return {
                "id": "cs_test_card_only",
                "url": "https://checkout.stripe.com/c/pay/cs_test_card_only",
            }

    class _DummyCheckout:
        Session = _DummySession

    class _DummyStripe:
        checkout = _DummyCheckout
        api_key = ""

    with patch("apps.inquiries.payments._load_stripe_module", return_value=_DummyStripe), patch(
        "apps.inquiries.payments._require_stripe_secret_key",
        return_value="sk_test",
    ), patch(
        "apps.inquiries.payments._build_offer_url",
        side_effect=[
            "https://recambios.example/payment/success",
            "https://recambios.example/payment/cancel",
        ],
    ):
        create_or_reuse_checkout_session_for_offer(offer, language_code="es")

    assert captured_payload.get("payment_method_types") == ["card"]


@pytest.mark.django_db
def test_checkout_configuration_guardrail_requires_secret_key(
    django_user_model,
    settings,
) -> None:
    offer = make_accepted_offer(django_user_model, username="stripe_missing_key")
    settings.STRIPE_SECRET_KEY = ""

    with pytest.raises(StripeConfigurationError):
        create_or_reuse_checkout_session_for_offer(offer, language_code="es")


@pytest.mark.django_db
def test_webhook_view_rejects_missing_or_invalid_signature(client) -> None:
    webhook_url = reverse("stripe_checkout_webhook")

    missing_signature_response = client.post(
        webhook_url,
        data=b"{}",
        content_type="application/json",
    )
    assert missing_signature_response.status_code == 400

    with patch(
        "apps.inquiries.views.construct_stripe_webhook_event",
        side_effect=StripeWebhookSignatureError("invalid"),
    ):
        invalid_signature_response = client.post(
            webhook_url,
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=invalid",
        )
    assert invalid_signature_response.status_code == 400

    with patch(
        "apps.inquiries.views.construct_stripe_webhook_event",
        side_effect=StripeWebhookPayloadError("invalid"),
    ):
        invalid_payload_response = client.post(
            webhook_url,
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=invalid",
        )
    assert invalid_payload_response.status_code == 400


@pytest.mark.django_db
def test_webhook_paid_event_marks_payment_as_paid(django_user_model) -> None:
    offer = make_accepted_offer(django_user_model, username="stripe_webhook_paid")
    payment = InquiryOfferPayment.ensure_pending_from_offer(
        offer,
        provider=STRIPE_PROVIDER,
        provider_reference="cs_test_pending",
        save=True,
    )
    payment.checkout_expires_at = offer.valid_until
    payment.save(update_fields=["checkout_expires_at"])

    changed = process_stripe_checkout_event(
        {
            "type": "checkout.session.completed",
            "created": int(timezone.now().timestamp()),
            "data": {
                "object": {
                    "id": "cs_test_paid",
                    "payment_status": "paid",
                    "metadata": {
                        "payment_reference": payment.reference_code,
                        "offer_reference": offer.reference_code,
                        "inquiry_reference": offer.inquiry.reference_code,
                    },
                }
            },
        }
    )

    payment.refresh_from_db()
    assert changed is True
    assert payment.status == InquiryOfferPayment.Status.PAID
    assert payment.paid_at is not None
    assert payment.provider_reference == "cs_test_paid"


@pytest.mark.django_db(transaction=True)
def test_late_webhook_restores_payment_completed_before_checkout_expiry(
    django_user_model,
) -> None:
    offer = make_accepted_offer(django_user_model, username="stripe_late_webhook")
    payment = offer.payment
    checkout_expiry = timezone.now() - timedelta(minutes=1)
    payment.checkout_expires_at = checkout_expiry
    payment.save(update_fields=["checkout_expires_at"])
    offer.valid_until = checkout_expiry - timedelta(minutes=10)
    offer.save(update_fields=["valid_until"])
    expire_due_inquiry_deadlines()

    changed = process_stripe_checkout_event(
        {
            "type": "checkout.session.completed",
            "created": int((checkout_expiry - timedelta(seconds=1)).timestamp()),
            "data": {
                "object": {
                    "id": "cs_test_late_webhook",
                    "payment_status": "paid",
                    "metadata": {"payment_reference": payment.reference_code},
                }
            },
        }
    )

    payment.refresh_from_db()
    offer.refresh_from_db()
    offer.inquiry.refresh_from_db()
    assert changed is True
    assert payment.status == InquiryOfferPayment.Status.PAID
    assert offer.status == InquiryOffer.Status.ACCEPTED
    assert offer.inquiry.status == Inquiry.Status.ACCEPTED


@pytest.mark.django_db
def test_webhook_rejects_payment_event_created_after_checkout_expiry(
    django_user_model,
) -> None:
    offer = make_accepted_offer(django_user_model, username="stripe_late_payment")
    payment = offer.payment
    payment.checkout_expires_at = timezone.now() - timedelta(seconds=2)
    payment.save(update_fields=["checkout_expires_at"])

    changed = process_stripe_checkout_event(
        {
            "type": "checkout.session.completed",
            "created": int(timezone.now().timestamp()),
            "data": {
                "object": {
                    "id": "cs_test_too_late",
                    "payment_status": "paid",
                    "metadata": {"payment_reference": payment.reference_code},
                }
            },
        }
    )

    payment.refresh_from_db()
    assert changed is False
    assert payment.status == InquiryOfferPayment.Status.PENDING


@pytest.mark.django_db(transaction=True)
def test_paid_internal_notification_is_sent_exactly_once(django_user_model, settings) -> None:
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.SERVER_EMAIL = "notifications@example.com"
    settings.INQUIRY_INTERNAL_NOTIFICATION_EMAILS = ["ops@example.com"]

    offer = make_accepted_offer(django_user_model, username="stripe_paid_once")
    payment = InquiryOfferPayment.ensure_pending_from_offer(
        offer,
        provider=STRIPE_PROVIDER,
        provider_reference="cs_test_pending_once",
        save=True,
    )
    payment.checkout_expires_at = offer.valid_until
    payment.save(update_fields=["checkout_expires_at"])

    event = {
        "type": "checkout.session.completed",
        "created": int(timezone.now().timestamp()),
        "data": {
            "object": {
                "id": "cs_test_paid_once",
                "payment_status": "paid",
                "metadata": {
                    "payment_reference": payment.reference_code,
                    "offer_reference": offer.reference_code,
                    "inquiry_reference": offer.inquiry.reference_code,
                },
            }
        },
    }

    mail.outbox.clear()
    first_changed = process_stripe_checkout_event(event)
    second_changed = process_stripe_checkout_event(event)

    assert first_changed is True
    assert second_changed is False
    assert len(mail.outbox) == 2

    internal_email = next(email for email in mail.outbox if email.to == ["ops@example.com"])
    customer_email = next(
        email for email in mail.outbox if email.to == ["stripe_paid_once@example.com"]
    )
    assert "Pago confirmado por Stripe" in internal_email.subject
    assert "Pago confirmado de su solicitud" in customer_email.subject
    assert offer.inquiry.reference_code in customer_email.body
    assert offer.reference_code in customer_email.body
    assert payment.reference_code in customer_email.body
    assert "Importe confirmado:" in customer_email.body
    assert payment.currency in customer_email.body
    assert "\n\n\n" not in internal_email.body
    assert "\n\n\n" not in customer_email.body


@pytest.mark.django_db(transaction=True)
def test_paid_supplier_notification_is_sent_once_when_enabled_via_webhook(
    django_user_model,
    settings,
) -> None:
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.SERVER_EMAIL = "notifications@example.com"
    settings.INQUIRY_INTERNAL_NOTIFICATION_EMAILS = ["ops@example.com"]

    supplier = make_supplier(
        code="SUP-STRIPE-PAID",
        auto_send_payment_paid_notification=True,
        payment_paid_notification_email="paid.notify@supplier.example",
        send_payment_paid_notification_internal_copy=True,
    )
    offer = make_accepted_offer(
        django_user_model,
        username="stripe_sup_paid_once",
        supplier=supplier,
    )
    payment = InquiryOfferPayment.ensure_pending_from_offer(
        offer,
        provider=STRIPE_PROVIDER,
        provider_reference="cs_test_supplier_pending",
        save=True,
    )
    payment.checkout_expires_at = offer.valid_until
    payment.save(update_fields=["checkout_expires_at"])
    event = {
        "type": "checkout.session.completed",
        "created": int(timezone.now().timestamp()),
        "data": {
            "object": {
                "id": "cs_test_supplier_paid_once",
                "payment_status": "paid",
                "metadata": {
                    "payment_reference": payment.reference_code,
                    "offer_reference": offer.reference_code,
                    "inquiry_reference": offer.inquiry.reference_code,
                },
            }
        },
    }

    mail.outbox.clear()
    first_changed = process_stripe_checkout_event(event)
    second_changed = process_stripe_checkout_event(event)

    assert first_changed is True
    assert second_changed is False
    assert len(mail.outbox) == 3

    internal_email = next(email for email in mail.outbox if email.to == ["ops@example.com"])
    supplier_email = next(
        email for email in mail.outbox if email.to == ["paid.notify@supplier.example"]
    )
    assert "Copia del mensaje enviado al proveedor:" in internal_email.body
    assert supplier_email.subject in internal_email.body
    assert supplier_email.body in internal_email.body
    assert "Customer payment confirmed - prepare fulfillment:" in supplier_email.subject
    assert supplier_email.bcc == ["ops@example.com"]


@pytest.mark.django_db
def test_irrelevant_stripe_events_are_ignored_without_warning_noise(caplog) -> None:
    with caplog.at_level("WARNING", logger="apps.inquiries.payments"):
        first_changed = process_stripe_checkout_event(
            {
                "type": "charge.succeeded",
                "data": {"object": {"id": "ch_123"}},
            }
        )
        second_changed = process_stripe_checkout_event(
            {
                "type": "payment_intent.created",
                "data": {"object": {"id": "pi_123"}},
            }
        )

    assert first_changed is False
    assert second_changed is False
    assert not any(record.levelname == "WARNING" for record in caplog.records)


@pytest.mark.django_db
def test_relevant_stripe_event_without_matching_payment_logs_warning(caplog) -> None:
    with caplog.at_level("WARNING", logger="apps.inquiries.payments"):
        changed = process_stripe_checkout_event(
            {
                "type": "checkout.session.completed",
                "created": int(timezone.now().timestamp()),
                "data": {
                    "object": {
                        "id": "cs_unknown",
                        "payment_status": "paid",
                        "metadata": {"payment_reference": "PAY-UNKNOWN"},
                    }
                },
            }
        )

    assert changed is False
    assert any(
        "could not be matched to an internal payment" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.django_db(transaction=True)
def test_customer_paid_email_failure_does_not_rollback_paid_state(
    django_user_model,
    settings,
    caplog,
) -> None:
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.SERVER_EMAIL = "notifications@example.com"
    settings.INQUIRY_INTERNAL_NOTIFICATION_EMAILS = ["ops@example.com"]
    offer = make_accepted_offer(django_user_model, username="stripe_paid_email_fail")
    payment = InquiryOfferPayment.ensure_pending_from_offer(
        offer,
        provider=STRIPE_PROVIDER,
        provider_reference="cs_test_customer_fail",
        save=True,
    )
    payment.checkout_expires_at = offer.valid_until
    payment.save(update_fields=["checkout_expires_at"])
    event = {
        "type": "checkout.session.completed",
        "created": int(timezone.now().timestamp()),
        "data": {
            "object": {
                "id": "cs_test_customer_fail_paid",
                "payment_status": "paid",
                "metadata": {
                    "payment_reference": payment.reference_code,
                    "offer_reference": offer.reference_code,
                    "inquiry_reference": offer.inquiry.reference_code,
                },
            }
        },
    }

    with patch(
        "apps.inquiries.signals.send_customer_payment_paid_confirmation_email",
        side_effect=RuntimeError("smtp down"),
    ):
        with caplog.at_level("ERROR", logger="apps.inquiries.signals"):
            changed = process_stripe_checkout_event(event)

    payment.refresh_from_db()
    assert changed is True
    assert payment.status == InquiryOfferPayment.Status.PAID
    assert any(
        "Failed to send customer paid-payment confirmation email" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.django_db
def test_public_payment_post_redirects_to_stripe_checkout_and_return_pages_do_not_mark_paid(
    client,
    django_user_model,
) -> None:
    offer = make_accepted_offer(django_user_model, username="stripe_public_flow")
    payment = InquiryOfferPayment.ensure_pending_from_offer(offer, save=True)
    payment_url = reverse(
        "inquiries:public_inquiry_offer_payment_placeholder",
        kwargs={"access_token": offer.access_token},
    )
    success_url = reverse(
        "inquiries:public_inquiry_offer_payment_success",
        kwargs={"access_token": offer.access_token},
    )
    cancel_url = reverse(
        "inquiries:public_inquiry_offer_payment_cancel",
        kwargs={"access_token": offer.access_token},
    )

    fake_result = StripeCheckoutSessionResult(
        payment=payment,
        session_id="cs_test_redirect",
        session_url="https://checkout.stripe.com/c/pay/cs_test_redirect",
        reused_existing_session=False,
    )
    with patch(
        "apps.inquiries.views.create_or_reuse_checkout_session_for_offer",
        return_value=fake_result,
    ):
        post_response = client.post(payment_url)
    assert post_response.status_code == 302
    assert post_response.url == "https://checkout.stripe.com/c/pay/cs_test_redirect"

    success_response = client.get(success_url)
    cancel_response = client.get(cancel_url)
    payment.refresh_from_db()

    assert success_response.status_code == 200
    assert cancel_response.status_code == 200
    assert payment.status == InquiryOfferPayment.Status.PENDING

    success_content = success_response.content.decode()
    cancel_content = cancel_response.content.decode()
    assert "Estamos completando la verificación final de su pago." in success_content
    assert "notificación técnica firmada de Stripe" not in success_content
    assert "Comprobar estado del pago" in success_content
    assert "El pago no se completó en esta operación." in cancel_content
    assert "Reintentar pago ahora" in cancel_content
