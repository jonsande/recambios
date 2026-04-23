from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Brand, Category, Condition, Product
from apps.inquiries.models import Inquiry, InquiryOffer, InquiryOfferPayment
from apps.inquiries.payments import (
    STRIPE_PROVIDER,
    StripeCheckoutSessionResult,
    StripeConfigurationError,
    StripeWebhookPayloadError,
    StripeWebhookSignatureError,
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
    offer_response_deadline_hours: int = 24,
    accepted_payment_deadline_hours: int = 24,
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
        offer_response_deadline_hours=offer_response_deadline_hours,
        accepted_payment_deadline_hours=accepted_payment_deadline_hours,
        auto_send_payment_expired_notification=auto_send_payment_expired_notification,
        payment_expired_notification_email=payment_expired_notification_email,
    )


def make_product(sku: str, *, supplier: Supplier | None = None) -> Product:
    supplier = supplier or make_supplier(code=f"SUP-{sku}")
    brand = Brand.objects.create(name=f"Brand {sku}", slug=f"brand-{sku.lower()}")
    category = Category.objects.create(name=f"Category {sku}", slug=f"category-{sku.lower()}")
    condition = Condition.objects.create(
        code=f"cond-{sku.lower()}",
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
    inquiry = Inquiry.objects.create(user=user, status=Inquiry.Status.IN_REVIEW)
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
    return offer


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


@pytest.mark.django_db
def test_checkout_session_initiation_is_blocked_for_non_accepted_offer(django_user_model) -> None:
    user = django_user_model.objects.create_user(
        username="stripe_not_accepted",
        email="stripe_not_accepted@example.com",
        password="pass1234",
    )
    inquiry = Inquiry.objects.create(user=user, status=Inquiry.Status.IN_REVIEW)
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

    changed = process_stripe_checkout_event(
        {
            "type": "checkout.session.completed",
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

    event = {
        "type": "checkout.session.completed",
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
    event = {
        "type": "checkout.session.completed",
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
    event = {
        "type": "checkout.session.completed",
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
