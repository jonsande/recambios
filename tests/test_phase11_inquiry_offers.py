from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone, translation

from apps.catalog.models import Brand, Category, Condition, Product
from apps.inquiries.admin import InquiryAdmin, InquiryOfferAdmin, InquiryOfferPaymentAdmin
from apps.inquiries.models import Inquiry, InquiryItem, InquiryOffer, InquiryOfferPayment
from apps.suppliers.models import Supplier
from apps.users.roles import ROLE_INTERNAL_STAFF


def make_supplier(code: str) -> Supplier:
    return Supplier.objects.create(
        name=f"Supplier {code}",
        slug=f"supplier-{code.lower()}",
        code=code,
    )


def make_brand(name: str, slug: str) -> Brand:
    return Brand.objects.create(name=name, slug=slug, brand_type=Brand.BrandType.PARTS)


def make_category(name: str, slug: str) -> Category:
    return Category.objects.create(name=name, slug=slug)


def make_condition(code: str, name: str, slug: str) -> Condition:
    return Condition.objects.create(code=code, name=name, slug=slug)


def make_product(
    sku: str,
    *,
    price: Decimal | None = Decimal("100.00"),
) -> Product:
    supplier = make_supplier(code=f"SUP-{sku}")
    brand = make_brand(name=f"Brand {sku}", slug=f"brand-{sku.lower()}")
    category = make_category(name=f"Category {sku}", slug=f"category-{sku.lower()}")
    condition = make_condition(
        code=f"cond-{sku.lower()}",
        name=f"Cond {sku}",
        slug=f"cond-{sku.lower()}",
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
        last_known_price=price,
        currency="EUR",
    )


def make_inquiry(
    django_user_model,
    *,
    username: str,
    status: str = Inquiry.Status.SUBMITTED,
) -> Inquiry:
    user = django_user_model.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="pass1234",
    )
    return Inquiry.objects.create(user=user, status=status)


def make_accepted_offer(
    django_user_model,
    *,
    username: str,
    confirmed_total: Decimal = Decimal("250.00"),
    currency: str = "EUR",
) -> InquiryOffer:
    inquiry = make_inquiry(
        django_user_model,
        username=username,
        status=Inquiry.Status.IN_REVIEW,
    )
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=confirmed_total,
        currency=currency,
        lead_time_text="5 days",
    )
    offer.mark_sent(save=True)
    offer.mark_accepted(save=True)
    offer.refresh_from_db()
    return offer


@pytest.mark.django_db
def test_offer_enforces_one_offer_per_inquiry(django_user_model) -> None:
    inquiry = make_inquiry(django_user_model, username="offer_uq")
    InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("350.00"),
        currency="EUR",
    )

    with pytest.raises(ValidationError):
        InquiryOffer.objects.create(
            inquiry=inquiry,
            confirmed_total=Decimal("360.00"),
            currency="EUR",
        )


@pytest.mark.django_db
def test_offer_rejects_negative_confirmed_total(django_user_model) -> None:
    inquiry = make_inquiry(django_user_model, username="offer_negative_total")

    with pytest.raises(ValidationError):
        InquiryOffer.objects.create(
            inquiry=inquiry,
            confirmed_total=Decimal("-1.00"),
            currency="EUR",
        )


@pytest.mark.django_db
def test_confirmed_total_is_traceable_independent_from_last_known_price(
    django_user_model,
) -> None:
    inquiry = make_inquiry(django_user_model, username="offer_traceability")
    product = make_product("SKU-OFFER-TRACE", price=Decimal("120.00"))
    InquiryItem.objects.create(inquiry=inquiry, product=product, requested_quantity=2)
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("479.99"),
        currency="EUR",
    )

    product.last_known_price = Decimal("999.99")
    product.save(update_fields=["last_known_price"])
    offer.refresh_from_db()

    assert offer.confirmed_total == Decimal("479.99")
    assert offer.confirmed_total != product.last_known_price


@pytest.mark.django_db
def test_offer_transition_rules_and_timestamps_with_valid_inquiry_sync(django_user_model) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="offer_transition_sync",
        status=Inquiry.Status.IN_REVIEW,
    )
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("220.00"),
        currency="EUR",
        lead_time_text="3-5 business days",
    )
    assert offer.is_ready_for_payment is False

    offer.mark_sent(save=True)
    offer.refresh_from_db()
    inquiry.refresh_from_db()

    assert offer.status == InquiryOffer.Status.SENT
    assert offer.sent_at is not None
    assert inquiry.status == Inquiry.Status.RESPONDED
    assert offer.is_ready_for_payment is False

    offer.mark_accepted(save=True)
    offer.refresh_from_db()
    inquiry.refresh_from_db()

    assert offer.status == InquiryOffer.Status.ACCEPTED
    assert offer.accepted_at is not None
    assert offer.rejected_at is None
    assert inquiry.status == Inquiry.Status.ACCEPTED
    assert offer.is_ready_for_payment is True

    with pytest.raises(ValueError):
        offer.mark_rejected(save=True)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "offer_status",
    (
        InquiryOffer.Status.DRAFT,
        InquiryOffer.Status.SENT,
        InquiryOffer.Status.REJECTED,
    ),
)
def test_payment_initiation_is_blocked_for_non_accepted_offers(
    django_user_model,
    offer_status: str,
) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username=f"payment_blocked_{offer_status}",
        status=Inquiry.Status.IN_REVIEW,
    )
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("450.00"),
        currency="EUR",
        lead_time_text="4 days",
    )
    if offer_status == InquiryOffer.Status.SENT:
        offer.mark_sent(save=True)
    elif offer_status == InquiryOffer.Status.REJECTED:
        offer.mark_sent(save=True)
        offer.mark_rejected(save=True)

    with pytest.raises(ValueError):
        InquiryOfferPayment.initiate_from_offer(offer, save=True)

    assert not InquiryOfferPayment.objects.filter(offer=offer).exists()


@pytest.mark.django_db
def test_payment_initiation_from_accepted_offer_snapshots_amount_and_currency(
    django_user_model,
) -> None:
    offer = make_accepted_offer(
        django_user_model,
        username="payment_snapshot_offer",
        confirmed_total=Decimal("680.55"),
        currency="eur",
    )
    payment = InquiryOfferPayment.initiate_from_offer(offer, save=True)

    assert payment.status == InquiryOfferPayment.Status.PENDING
    assert payment.initiated_at is not None
    assert payment.payable_amount == Decimal("680.55")
    assert payment.currency == "EUR"

    offer.confirmed_total = Decimal("999.00")
    offer.currency = "USD"
    offer.save(update_fields=["confirmed_total", "currency"])

    payment.refresh_from_db()
    assert payment.payable_amount == Decimal("680.55")
    assert payment.currency == "EUR"


@pytest.mark.django_db
def test_payment_ensure_from_accepted_offer_is_idempotent(django_user_model) -> None:
    offer = make_accepted_offer(
        django_user_model,
        username="payment_ensure_idempotent",
        confirmed_total=Decimal("499.90"),
    )

    first_payment = InquiryOfferPayment.ensure_pending_from_offer(offer, save=True)
    second_payment = InquiryOfferPayment.ensure_pending_from_offer(offer, save=True)

    assert first_payment.pk == second_payment.pk
    assert InquiryOfferPayment.objects.filter(offer=offer).count() == 1
    assert second_payment.status == InquiryOfferPayment.Status.PENDING
    assert second_payment.payable_amount == Decimal("499.90")
    assert second_payment.currency == "EUR"


@pytest.mark.django_db
def test_offer_with_payment_record_must_stay_accepted(django_user_model) -> None:
    offer = make_accepted_offer(
        django_user_model,
        username="payment_offer_stays_accepted",
    )
    InquiryOfferPayment.initiate_from_offer(offer, save=True)

    offer.status = InquiryOffer.Status.REJECTED
    offer.rejected_at = timezone.now()
    offer.accepted_at = None

    with pytest.raises(ValidationError):
        offer.full_clean()


@pytest.mark.django_db
def test_one_payment_record_per_offer_is_enforced(django_user_model) -> None:
    offer = make_accepted_offer(
        django_user_model,
        username="payment_one_per_offer",
    )
    InquiryOfferPayment.initiate_from_offer(offer, save=True)

    with pytest.raises(ValidationError):
        InquiryOfferPayment.initiate_from_offer(offer, save=True)


@pytest.mark.django_db
def test_payment_transition_rules_and_timestamps(django_user_model) -> None:
    offer = make_accepted_offer(
        django_user_model,
        username="payment_transition_rules",
    )
    payment = InquiryOfferPayment.initiate_from_offer(offer, save=True)

    payment.mark_paid(save=True)
    payment.refresh_from_db()
    assert payment.status == InquiryOfferPayment.Status.PAID
    assert payment.paid_at is not None
    assert payment.failed_at is None
    assert payment.cancelled_at is None

    with pytest.raises(ValueError):
        payment.mark_failed(save=True)


@pytest.mark.django_db
def test_payment_status_requires_consistent_timestamps(django_user_model) -> None:
    offer = make_accepted_offer(
        django_user_model,
        username="payment_timestamp_integrity",
    )
    payment = InquiryOfferPayment.initiate_from_offer(offer, save=True)
    payment.paid_at = timezone.now()

    with pytest.raises(ValidationError):
        payment.full_clean()


@pytest.mark.django_db
def test_mark_sent_requires_minimum_commercial_data(django_user_model) -> None:
    inquiry = make_inquiry(django_user_model, username="offer_send_ready")
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("120.00"),
        currency="EUR",
        lead_time_text="",
    )

    with pytest.raises(ValidationError):
        offer.mark_sent(save=True)

    offer.refresh_from_db()
    assert offer.status == InquiryOffer.Status.DRAFT
    assert offer.sent_at is None


@pytest.mark.django_db
def test_mark_sent_succeeds_with_minimum_commercial_data(django_user_model) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="offer_send_ready_ok",
        status=Inquiry.Status.IN_REVIEW,
    )
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("120.00"),
        currency="EUR",
        lead_time_text="48-72h",
    )

    offer.mark_sent(save=True)
    offer.refresh_from_db()

    assert offer.status == InquiryOffer.Status.SENT
    assert offer.sent_at is not None


@pytest.mark.django_db
def test_offer_status_requires_consistent_timestamps(django_user_model) -> None:
    inquiry = make_inquiry(django_user_model, username="offer_timestamp_integrity")
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("99.00"),
        currency="EUR",
    )
    offer.status = InquiryOffer.Status.SENT
    offer.sent_at = None

    with pytest.raises(ValidationError):
        offer.full_clean()


@pytest.mark.django_db
def test_mark_sent_is_blocked_when_inquiry_cannot_transition_to_responded(
    django_user_model,
) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="offer_send_requires_inquiry_transition",
        status=Inquiry.Status.SUBMITTED,
    )
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("180.00"),
        currency="EUR",
        lead_time_text="1 week",
    )

    with pytest.raises(ValidationError):
        offer.mark_sent(save=True)

    offer.refresh_from_db()
    inquiry.refresh_from_db()
    assert offer.status == InquiryOffer.Status.DRAFT
    assert offer.sent_at is None
    assert inquiry.status == Inquiry.Status.SUBMITTED


@pytest.mark.django_db
def test_negative_resolution_persists_reason_notes_and_timestamp(django_user_model) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="negative_resolution_persistence",
        status=Inquiry.Status.IN_REVIEW,
    )
    inquiry.negative_resolution_reason = Inquiry.NegativeResolutionReason.UNAVAILABLE
    inquiry.negative_resolution_internal_notes = "  Proveedor sin stock confirmado  "
    inquiry.negative_resolution_customer_message = "  No podemos confirmar suministro.  "
    inquiry.finalize_negative_resolution(save=True)
    inquiry.refresh_from_db()

    assert inquiry.status == Inquiry.Status.CLOSED
    assert inquiry.negative_resolution_reason == Inquiry.NegativeResolutionReason.UNAVAILABLE
    assert inquiry.negative_resolution_internal_notes == "Proveedor sin stock confirmado"
    assert inquiry.negative_resolution_customer_message == "No podemos confirmar suministro."
    assert inquiry.negative_resolved_at is not None


@pytest.mark.django_db
@pytest.mark.parametrize(
    "starting_status",
    (Inquiry.Status.IN_REVIEW, Inquiry.Status.SUPPLIER_PENDING),
)
def test_finalize_negative_resolution_moves_inquiry_to_closed(
    django_user_model,
    starting_status: str,
) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username=f"negative_to_closed_{starting_status}",
        status=starting_status,
    )
    inquiry.negative_resolution_reason = (
        Inquiry.NegativeResolutionReason.SUPPLIER_CANNOT_CONFIRM
    )
    inquiry.finalize_negative_resolution(save=True)
    inquiry.refresh_from_db()

    assert inquiry.status == Inquiry.Status.CLOSED
    assert inquiry.negative_resolved_at is not None


@pytest.mark.django_db
def test_finalize_negative_resolution_requires_reason(django_user_model) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="negative_requires_reason",
        status=Inquiry.Status.IN_REVIEW,
    )

    with pytest.raises(ValidationError):
        inquiry.finalize_negative_resolution(save=True)

    inquiry.refresh_from_db()
    assert inquiry.status == Inquiry.Status.IN_REVIEW
    assert inquiry.negative_resolved_at is None


@pytest.mark.django_db
def test_finalize_negative_resolution_is_blocked_when_any_offer_exists(django_user_model) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="negative_offer_conflict",
        status=Inquiry.Status.IN_REVIEW,
    )
    inquiry.negative_resolution_reason = Inquiry.NegativeResolutionReason.OTHER
    InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("250.00"),
        currency="EUR",
        lead_time_text="5 days",
    )

    with pytest.raises(ValidationError):
        inquiry.finalize_negative_resolution(save=True)

    inquiry.refresh_from_db()
    assert inquiry.status == Inquiry.Status.IN_REVIEW
    assert inquiry.negative_resolved_at is None


@pytest.mark.django_db
def test_offer_creation_is_blocked_for_negatively_resolved_inquiry(django_user_model) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="offer_blocked_after_negative",
        status=Inquiry.Status.IN_REVIEW,
    )
    inquiry.negative_resolution_reason = Inquiry.NegativeResolutionReason.LOGISTICS_NOT_POSSIBLE
    inquiry.finalize_negative_resolution(save=True)

    with pytest.raises(ValidationError):
        InquiryOffer.objects.create(
            inquiry=inquiry,
            confirmed_total=Decimal("300.00"),
            currency="EUR",
            lead_time_text="2 weeks",
        )


@pytest.mark.django_db(transaction=True)
def test_negative_resolution_email_is_sent_once_on_true_finalization(
    django_user_model,
    offer_email_settings,
) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="negative_email_once",
        status=Inquiry.Status.IN_REVIEW,
    )
    inquiry.negative_resolution_reason = Inquiry.NegativeResolutionReason.UNAVAILABLE
    inquiry.negative_resolution_customer_message = "No podemos confirmar disponibilidad."

    mail.outbox.clear()
    inquiry.finalize_negative_resolution(save=True)
    assert len(mail.outbox) == 1

    inquiry.internal_notes = "Seguimiento interno"
    inquiry.save(update_fields=["internal_notes"])
    assert len(mail.outbox) == 1


@pytest.mark.django_db(transaction=True)
def test_negative_resolution_email_supports_english_content(
    django_user_model,
    offer_email_settings,
) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="negative_email_en",
        status=Inquiry.Status.IN_REVIEW,
    )
    inquiry.language = Inquiry.Language.ENGLISH
    inquiry.negative_resolution_reason = Inquiry.NegativeResolutionReason.SUPPLIER_CANNOT_CONFIRM
    inquiry.negative_resolution_customer_message = (
        "We cannot secure a firm supplier confirmation right now."
    )
    inquiry.save(update_fields=["language"])

    mail.outbox.clear()
    inquiry.finalize_negative_resolution(save=True)

    assert len(mail.outbox) == 1
    email = mail.outbox[0]
    assert "Inquiry update:" in email.subject
    assert "We have completed the review of your inquiry" in email.body
    assert "We could not obtain a firm confirmation from the supplier." in email.body
    assert "We cannot secure a firm supplier confirmation right now." in email.body


@pytest.mark.django_db(transaction=True)
def test_negative_resolution_email_failure_is_logged_and_state_is_kept(
    django_user_model,
    offer_email_settings,
    caplog,
) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="negative_email_send_failure",
        status=Inquiry.Status.IN_REVIEW,
    )
    inquiry.negative_resolution_reason = Inquiry.NegativeResolutionReason.OTHER
    inquiry.negative_resolution_customer_message = "No es posible ofrecer en este momento."

    with patch("apps.inquiries.emails.EmailMessage.send", side_effect=RuntimeError("smtp down")):
        with caplog.at_level("ERROR", logger="apps.inquiries.signals"):
            inquiry.finalize_negative_resolution(save=True)

    inquiry.refresh_from_db()
    assert inquiry.status == Inquiry.Status.CLOSED
    assert inquiry.negative_resolved_at is not None
    assert any(
        "Failed to send customer negative-resolution email" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.django_db
def test_internal_staff_group_has_inquiry_offer_permissions() -> None:
    internal_staff = Group.objects.get(name=ROLE_INTERNAL_STAFF)
    for codename in (
        "add_inquiryoffer",
        "change_inquiryoffer",
        "delete_inquiryoffer",
        "view_inquiryoffer",
    ):
        assert internal_staff.permissions.filter(
            content_type__app_label="inquiries",
            codename=codename,
        ).exists()


@pytest.mark.django_db
def test_internal_staff_group_has_inquiry_offer_payment_permissions() -> None:
    internal_staff = Group.objects.get(name=ROLE_INTERNAL_STAFF)
    for codename in (
        "add_inquiryofferpayment",
        "change_inquiryofferpayment",
        "delete_inquiryofferpayment",
        "view_inquiryofferpayment",
    ):
        assert internal_staff.permissions.filter(
            content_type__app_label="inquiries",
            codename=codename,
        ).exists()


@pytest.mark.django_db
def test_admin_send_action_moves_draft_offer_to_sent(django_user_model) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="offer_admin_send",
        status=Inquiry.Status.IN_REVIEW,
    )
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("700.00"),
        currency="EUR",
        lead_time_text="5 days",
    )
    admin_user = django_user_model.objects.create_superuser(
        username="offer_admin",
        email="offer_admin@example.com",
        password="pass1234",
    )
    request = RequestFactory().post("/admin/inquiries/inquiryoffer/")
    request.user = admin_user

    offer_admin = InquiryOfferAdmin(InquiryOffer, AdminSite())
    offer_admin.message_user = lambda *args, **kwargs: None
    offer_admin.mark_selected_as_sent(request, InquiryOffer.objects.filter(pk=offer.pk))

    offer.refresh_from_db()
    assert offer.status == InquiryOffer.Status.SENT
    assert offer.sent_at is not None


@pytest.mark.django_db
def test_admin_send_action_uses_business_friendly_label() -> None:
    assert InquiryOfferAdmin.mark_selected_as_sent.short_description == (
        "Send selected offers to customers"
    )


@pytest.mark.django_db(transaction=True)
def test_admin_manual_resend_action_sends_only_for_sent_or_accepted_without_state_change(
    django_user_model,
    offer_email_settings,
) -> None:
    sent_inquiry = make_inquiry(
        django_user_model,
        username="offer_resend_sent",
        status=Inquiry.Status.IN_REVIEW,
    )
    accepted_inquiry = make_inquiry(
        django_user_model,
        username="offer_resend_accepted",
        status=Inquiry.Status.IN_REVIEW,
    )
    draft_inquiry = make_inquiry(
        django_user_model,
        username="offer_resend_draft",
        status=Inquiry.Status.IN_REVIEW,
    )
    rejected_inquiry = make_inquiry(
        django_user_model,
        username="offer_resend_rejected",
        status=Inquiry.Status.IN_REVIEW,
    )
    sent_offer = InquiryOffer.objects.create(
        inquiry=sent_inquiry,
        confirmed_total=Decimal("500.00"),
        currency="EUR",
        lead_time_text="5 days",
    )
    accepted_offer = InquiryOffer.objects.create(
        inquiry=accepted_inquiry,
        confirmed_total=Decimal("610.00"),
        currency="EUR",
        lead_time_text="3 days",
    )
    draft_offer = InquiryOffer.objects.create(
        inquiry=draft_inquiry,
        confirmed_total=Decimal("450.00"),
        currency="EUR",
        lead_time_text="4 days",
    )
    rejected_offer = InquiryOffer.objects.create(
        inquiry=rejected_inquiry,
        confirmed_total=Decimal("390.00"),
        currency="EUR",
        lead_time_text="8 days",
    )
    sent_offer.mark_sent(save=True)
    accepted_offer.mark_sent(save=True)
    accepted_offer.mark_accepted(save=True)
    rejected_offer.mark_sent(save=True)
    rejected_offer.mark_rejected(save=True)

    admin_user = django_user_model.objects.create_superuser(
        username="offer_resend_admin",
        email="offer_resend_admin@example.com",
        password="pass1234",
    )
    request = RequestFactory().post("/admin/inquiries/inquiryoffer/")
    request.user = admin_user
    offer_admin = InquiryOfferAdmin(InquiryOffer, AdminSite())

    captured_messages: list[str] = []
    offer_admin.message_user = (
        lambda _request, message, level=None: captured_messages.append(str(message))
    )

    mail.outbox.clear()
    offer_admin.resend_offer_email_to_customer(
        request,
        InquiryOffer.objects.filter(
            pk__in=[sent_offer.pk, accepted_offer.pk, draft_offer.pk, rejected_offer.pk]
        ),
    )

    sent_offer.refresh_from_db()
    accepted_offer.refresh_from_db()
    draft_offer.refresh_from_db()
    rejected_offer.refresh_from_db()

    assert sent_offer.status == InquiryOffer.Status.SENT
    assert accepted_offer.status == InquiryOffer.Status.ACCEPTED
    assert draft_offer.status == InquiryOffer.Status.DRAFT
    assert rejected_offer.status == InquiryOffer.Status.REJECTED
    assert len(mail.outbox) == 2
    assert any("Re-sent 2 offer email(s)." in message for message in captured_messages)
    assert any(
        "manual re-send is only available for sent or accepted offers" in message
        for message in captured_messages
    )


@pytest.mark.django_db
def test_admin_action_initiates_payment_for_accepted_offer(django_user_model) -> None:
    offer = make_accepted_offer(
        django_user_model,
        username="admin_payment_init_ok",
        confirmed_total=Decimal("730.00"),
    )
    admin_user = django_user_model.objects.create_superuser(
        username="admin_payment_init_user",
        email="admin_payment_init_user@example.com",
        password="pass1234",
    )
    request = RequestFactory().post("/admin/inquiries/inquiryoffer/")
    request.user = admin_user

    offer_admin = InquiryOfferAdmin(InquiryOffer, AdminSite())
    offer_admin.message_user = lambda *args, **kwargs: None
    offer_admin.initiate_payment_for_selected_offers(
        request,
        InquiryOffer.objects.filter(pk=offer.pk),
    )

    payment = InquiryOfferPayment.objects.get(offer=offer)
    assert payment.status == InquiryOfferPayment.Status.PENDING
    assert payment.initiated_at is not None
    assert payment.payable_amount == Decimal("730.00")
    assert payment.currency == "EUR"


@pytest.mark.django_db
def test_admin_action_reports_invalid_payment_initiation_cases(django_user_model) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="admin_payment_init_invalid",
        status=Inquiry.Status.IN_REVIEW,
    )
    sent_offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("540.00"),
        currency="EUR",
        lead_time_text="4 days",
    )
    sent_offer.mark_sent(save=True)
    admin_user = django_user_model.objects.create_superuser(
        username="admin_payment_init_invalid_user",
        email="admin_payment_init_invalid_user@example.com",
        password="pass1234",
    )
    request = RequestFactory().post("/admin/inquiries/inquiryoffer/")
    request.user = admin_user

    offer_admin = InquiryOfferAdmin(InquiryOffer, AdminSite())
    captured_messages: list[str] = []
    offer_admin.message_user = (
        lambda _request, message, level=None: captured_messages.append(str(message))
    )
    offer_admin.initiate_payment_for_selected_offers(
        request,
        InquiryOffer.objects.filter(pk=sent_offer.pk),
    )

    assert not InquiryOfferPayment.objects.filter(offer=sent_offer).exists()
    assert any(
        "could not be initiated" in message
        for message in captured_messages
    )


@pytest.mark.django_db
def test_payment_admin_actions_apply_and_block_invalid_transitions(
    django_user_model,
) -> None:
    offer = make_accepted_offer(
        django_user_model,
        username="admin_payment_transition",
    )
    payment = InquiryOfferPayment.initiate_from_offer(offer, save=True)
    admin_user = django_user_model.objects.create_superuser(
        username="admin_payment_transition_user",
        email="admin_payment_transition_user@example.com",
        password="pass1234",
    )
    request = RequestFactory().post("/admin/inquiries/inquiryofferpayment/")
    request.user = admin_user
    payment_admin = InquiryOfferPaymentAdmin(InquiryOfferPayment, AdminSite())
    captured_messages: list[str] = []
    payment_admin.message_user = (
        lambda _request, message, level=None: captured_messages.append(str(message))
    )

    payment_admin.mark_selected_as_paid(
        request,
        InquiryOfferPayment.objects.filter(pk=payment.pk),
    )
    payment.refresh_from_db()
    assert payment.status == InquiryOfferPayment.Status.PAID
    assert payment.paid_at is not None

    payment_admin.mark_selected_as_failed(
        request,
        InquiryOfferPayment.objects.filter(pk=payment.pk),
    )
    payment.refresh_from_db()
    assert payment.status == InquiryOfferPayment.Status.PAID
    assert any("could not transition to failed" in message for message in captured_messages)


@pytest.mark.django_db
def test_admin_action_finalizes_negative_resolution(django_user_model) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="admin_negative_finalize",
        status=Inquiry.Status.SUPPLIER_PENDING,
    )
    inquiry.negative_resolution_reason = Inquiry.NegativeResolutionReason.UNAVAILABLE
    inquiry.negative_resolution_customer_message = "No hay disponibilidad."
    inquiry.save()

    admin_user = django_user_model.objects.create_superuser(
        username="admin_negative_finalize_user",
        email="admin_negative_finalize@example.com",
        password="pass1234",
    )
    request = RequestFactory().post("/admin/inquiries/inquiry/")
    request.user = admin_user

    admin_instance = InquiryAdmin(Inquiry, AdminSite())
    admin_instance.message_user = lambda *args, **kwargs: None
    admin_instance.finalize_selected_as_not_offerable(
        request,
        Inquiry.objects.filter(pk=inquiry.pk),
    )

    inquiry.refresh_from_db()
    assert inquiry.status == Inquiry.Status.CLOSED
    assert inquiry.negative_resolved_at is not None


@pytest.mark.django_db
def test_admin_action_reports_invalid_negative_resolution(django_user_model) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="admin_negative_invalid",
        status=Inquiry.Status.IN_REVIEW,
    )
    admin_user = django_user_model.objects.create_superuser(
        username="admin_negative_invalid_user",
        email="admin_negative_invalid@example.com",
        password="pass1234",
    )
    request = RequestFactory().post("/admin/inquiries/inquiry/")
    request.user = admin_user

    admin_instance = InquiryAdmin(Inquiry, AdminSite())
    captured_messages: list[str] = []
    admin_instance.message_user = (
        lambda _request, message, level=None: captured_messages.append(str(message))
    )
    admin_instance.finalize_selected_as_not_offerable(
        request,
        Inquiry.objects.filter(pk=inquiry.pk),
    )

    inquiry.refresh_from_db()
    assert inquiry.status == Inquiry.Status.IN_REVIEW
    assert inquiry.negative_resolved_at is None
    assert any(
        "could not be finalized as not offerable" in message
        for message in captured_messages
    )
    assert any("negative_resolution_reason" in message for message in captured_messages)


@pytest.mark.django_db
def test_admin_locks_negative_resolution_fields_after_finalization(django_user_model) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="admin_negative_locking",
        status=Inquiry.Status.IN_REVIEW,
    )
    inquiry.negative_resolution_reason = Inquiry.NegativeResolutionReason.OTHER
    inquiry.finalize_negative_resolution(save=True)

    admin_user = django_user_model.objects.create_superuser(
        username="admin_negative_locking_user",
        email="admin_negative_locking@example.com",
        password="pass1234",
    )
    request = RequestFactory().get("/admin/inquiries/inquiry/")
    request.user = admin_user

    admin_instance = InquiryAdmin(Inquiry, AdminSite())
    readonly_fields = set(admin_instance.get_readonly_fields(request, inquiry))

    assert "negative_resolution_reason" in readonly_fields
    assert "negative_resolution_internal_notes" in readonly_fields
    assert "negative_resolution_customer_message" in readonly_fields
    assert "negative_resolved_at" in readonly_fields


@pytest.mark.django_db
def test_admin_locks_customer_facing_commercial_fields_after_send(django_user_model) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="offer_admin_locking",
        status=Inquiry.Status.IN_REVIEW,
    )
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("325.00"),
        currency="EUR",
        lead_time_text="1 week",
    )
    admin_user = django_user_model.objects.create_superuser(
        username="offer_admin_lock",
        email="offer_admin_lock@example.com",
        password="pass1234",
    )
    request = RequestFactory().get("/admin/inquiries/inquiryoffer/")
    request.user = admin_user
    offer_admin = InquiryOfferAdmin(InquiryOffer, AdminSite())

    readonly_in_draft = set(offer_admin.get_readonly_fields(request, offer))
    assert "confirmed_total" not in readonly_in_draft
    assert "currency" not in readonly_in_draft
    assert "lead_time_text" not in readonly_in_draft
    assert "customer_message" not in readonly_in_draft

    offer.mark_sent(save=True)
    offer.refresh_from_db()

    readonly_after_send = set(offer_admin.get_readonly_fields(request, offer))
    assert {
        "confirmed_total",
        "currency",
        "lead_time_text",
        "customer_message",
    } <= readonly_after_send
    assert "internal_notes" not in readonly_after_send


@pytest.mark.django_db
def test_admin_send_action_reports_not_ready_offers(django_user_model) -> None:
    inquiry = make_inquiry(django_user_model, username="offer_admin_not_ready")
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("400.00"),
        currency="EUR",
        lead_time_text="",
    )
    admin_user = django_user_model.objects.create_superuser(
        username="offer_admin_not_ready_user",
        email="offer_admin_not_ready@example.com",
        password="pass1234",
    )
    request = RequestFactory().post("/admin/inquiries/inquiryoffer/")
    request.user = admin_user
    offer_admin = InquiryOfferAdmin(InquiryOffer, AdminSite())
    captured_messages: list[str] = []
    offer_admin.message_user = (
        lambda _request, message, level=None: captured_messages.append(str(message))
    )

    offer_admin.mark_selected_as_sent(request, InquiryOffer.objects.filter(pk=offer.pk))
    offer.refresh_from_db()

    assert offer.status == InquiryOffer.Status.DRAFT
    assert any("not ready to send" in message for message in captured_messages)
    assert any("lead_time_text" in message for message in captured_messages)


@pytest.mark.django_db
def test_confirmed_total_help_text_marks_payment_source_of_truth() -> None:
    help_text = InquiryOffer._meta.get_field("confirmed_total").help_text.lower()
    assert "source of truth" in help_text
    assert "payment preparation" in help_text


@pytest.mark.django_db
def test_public_offer_token_invalid_returns_404(client) -> None:
    url = reverse(
        "inquiries:public_inquiry_offer_detail",
        kwargs={"access_token": uuid.uuid4()},
    )
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_public_offer_draft_token_shows_unavailable_without_offer_data(
    client,
    django_user_model,
) -> None:
    inquiry = make_inquiry(django_user_model, username="offer_public_draft")
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("310.00"),
        currency="EUR",
        customer_message="Mensaje borrador interno",
    )
    url = reverse(
        "inquiries:public_inquiry_offer_detail",
        kwargs={"access_token": offer.access_token},
    )

    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()

    assert "Oferta no disponible" in content
    assert str(offer.confirmed_total) not in content
    assert offer.reference_code not in content
    assert inquiry.reference_code not in content


@pytest.mark.django_db
def test_public_offer_sent_token_shows_offer_data_and_actions(client, django_user_model) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="offer_public_sent",
        status=Inquiry.Status.IN_REVIEW,
    )
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("410.00"),
        currency="EUR",
        lead_time_text="5-7 días laborables",
        customer_message="Disponibilidad confirmada según consulta.",
    )
    offer.mark_sent(save=True)
    offer.refresh_from_db()
    url = reverse(
        "inquiries:public_inquiry_offer_detail",
        kwargs={"access_token": offer.access_token},
    )

    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()

    assert offer.reference_code in content
    assert inquiry.reference_code in content
    assert "410" in content
    assert "EUR" in content
    assert "Responder a la oferta" in content
    assert "Aceptar oferta y proceder al pago" in content
    assert "Rechazar oferta" in content
    assert "bg-slate-900" in content
    assert "border-slate-400" in content
    assert (
        "La oferta está sujeta a disponibilidad efectiva en el momento de tramitación del pago."
        in content
    )


@pytest.mark.django_db
def test_customer_accept_flow_redirects_to_payment_placeholder_and_prevents_duplicates(
    client,
    django_user_model,
) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="offer_public_accept",
        status=Inquiry.Status.IN_REVIEW,
    )
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("990.00"),
        currency="EUR",
        lead_time_text="3 days",
    )
    offer.mark_sent(save=True)
    url = reverse(
        "inquiries:public_inquiry_offer_detail",
        kwargs={"access_token": offer.access_token},
    )
    payment_url = reverse(
        "inquiries:public_inquiry_offer_payment_placeholder",
        kwargs={"access_token": offer.access_token},
    )

    first_response = client.post(url, data={"decision": "accept"})
    assert first_response.status_code == 302
    assert first_response.url == payment_url
    offer.refresh_from_db()
    inquiry.refresh_from_db()
    assert offer.status == InquiryOffer.Status.ACCEPTED
    assert offer.accepted_at is not None
    assert inquiry.status == Inquiry.Status.ACCEPTED
    assert InquiryOfferPayment.objects.filter(offer=offer).count() == 1

    second_response = client.post(url, data={"decision": "reject"})
    assert second_response.status_code == 302
    offer.refresh_from_db()
    inquiry.refresh_from_db()
    assert offer.status == InquiryOffer.Status.ACCEPTED
    assert offer.rejected_at is None
    assert inquiry.status == Inquiry.Status.ACCEPTED
    assert InquiryOfferPayment.objects.filter(offer=offer).count() == 1


@pytest.mark.django_db
def test_customer_reject_flow_updates_offer(client, django_user_model) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="offer_public_reject",
        status=Inquiry.Status.IN_REVIEW,
    )
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("430.00"),
        currency="EUR",
        lead_time_text="7 days",
    )
    offer.mark_sent(save=True)
    url = reverse(
        "inquiries:public_inquiry_offer_detail",
        kwargs={"access_token": offer.access_token},
    )

    response = client.post(url, data={"decision": "reject"})
    assert response.status_code == 302

    offer.refresh_from_db()
    inquiry.refresh_from_db()
    assert offer.status == InquiryOffer.Status.REJECTED
    assert offer.rejected_at is not None
    assert offer.accepted_at is None
    assert inquiry.status == Inquiry.Status.REJECTED


@pytest.mark.django_db
def test_public_offer_state_specific_copy_for_accepted_and_rejected(
    client,
    django_user_model,
) -> None:
    accepted_offer = make_accepted_offer(
        django_user_model,
        username="offer_public_copy_accepted",
        confirmed_total=Decimal("880.00"),
    )
    rejected_inquiry = make_inquiry(
        django_user_model,
        username="offer_public_copy_rejected",
        status=Inquiry.Status.IN_REVIEW,
    )
    rejected_offer = InquiryOffer.objects.create(
        inquiry=rejected_inquiry,
        confirmed_total=Decimal("640.00"),
        currency="EUR",
        lead_time_text="7 days",
    )
    rejected_offer.mark_sent(save=True)
    rejected_offer.mark_rejected(save=True)

    accepted_url = reverse(
        "inquiries:public_inquiry_offer_detail",
        kwargs={"access_token": accepted_offer.access_token},
    )
    rejected_url = reverse(
        "inquiries:public_inquiry_offer_detail",
        kwargs={"access_token": rejected_offer.access_token},
    )

    accepted_response = client.get(accepted_url)
    rejected_response = client.get(rejected_url)
    accepted_content = accepted_response.content.decode()
    rejected_content = rejected_response.content.decode()

    assert accepted_response.status_code == 200
    assert rejected_response.status_code == 200
    assert "Oferta aceptada" in accepted_content
    assert "Continuar al paso de pago" in accepted_content
    assert "Oferta rechazada" in rejected_content
    assert "Si necesitas revisar alternativas" in rejected_content
    assert "Responder a la oferta" not in accepted_content
    assert "Responder a la oferta" not in rejected_content


@pytest.mark.django_db
def test_public_offer_state_specific_copy_supports_english(client, django_user_model) -> None:
    sent_inquiry = make_inquiry(
        django_user_model,
        username="offer_public_copy_en",
        status=Inquiry.Status.IN_REVIEW,
    )
    sent_offer = InquiryOffer.objects.create(
        inquiry=sent_inquiry,
        confirmed_total=Decimal("715.00"),
        currency="EUR",
        lead_time_text="3 business days",
    )
    sent_offer.mark_sent(save=True)

    try:
        with translation.override("en"):
            sent_url = reverse(
                "inquiries:public_inquiry_offer_detail",
                kwargs={"access_token": sent_offer.access_token},
            )
            sent_response = client.get(sent_url)
        sent_content = sent_response.content.decode()

        assert sent_response.status_code == 200
        assert "Confirmed offer" in sent_content
        assert "Respond to this offer" in sent_content
        assert "Accept offer and proceed to payment" in sent_content
        assert "Reject offer" in sent_content
        assert (
            "The offer remains subject to effective availability at the time of payment processing."
            in sent_content
        )
    finally:
        translation.activate("es")


@pytest.mark.django_db
def test_public_payment_placeholder_renders_for_accepted_offer(client, django_user_model) -> None:
    offer = make_accepted_offer(
        django_user_model,
        username="offer_public_payment_placeholder",
        confirmed_total=Decimal("555.20"),
    )
    InquiryOfferPayment.ensure_pending_from_offer(offer, save=True)
    with translation.override("es"):
        payment_url = reverse(
            "inquiries:public_inquiry_offer_payment_placeholder",
            kwargs={"access_token": offer.access_token},
        )

    response = client.get(payment_url)
    content = response.content.decode()
    payment = InquiryOfferPayment.objects.get(offer=offer)

    assert response.status_code == 200
    assert "Paso de pago" in content
    assert payment.reference_code in content
    assert "555" in content
    assert payment.currency in content
    assert InquiryOfferPayment.objects.filter(offer=offer).count() == 1

    second_response = client.get(payment_url)
    assert second_response.status_code == 200
    assert InquiryOfferPayment.objects.filter(offer=offer).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "starting_status",
    (
        InquiryOffer.Status.SENT,
        InquiryOffer.Status.REJECTED,
    ),
)
def test_public_payment_placeholder_redirects_non_accepted_offers_to_detail(
    client,
    django_user_model,
    starting_status: str,
) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username=f"offer_public_payment_redirect_{starting_status}",
        status=Inquiry.Status.IN_REVIEW,
    )
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("601.00"),
        currency="EUR",
        lead_time_text="6 days",
    )
    if starting_status == InquiryOffer.Status.SENT:
        offer.mark_sent(save=True)
    elif starting_status == InquiryOffer.Status.REJECTED:
        offer.mark_sent(save=True)
        offer.mark_rejected(save=True)

    payment_url = reverse(
        "inquiries:public_inquiry_offer_payment_placeholder",
        kwargs={"access_token": offer.access_token},
    )
    offer_url = reverse(
        "inquiries:public_inquiry_offer_detail",
        kwargs={"access_token": offer.access_token},
    )
    response = client.get(payment_url)

    assert response.status_code == 302
    assert response.url == offer_url
    assert not InquiryOfferPayment.objects.filter(offer=offer).exists()


@pytest.fixture
def offer_email_settings(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "Recambios <noreply@example.com>"
    settings.INQUIRY_CUSTOMER_REPLY_TO_EMAIL = "atencion@example.com"
    settings.PUBLIC_BASE_URL = "https://recambios.example"


@pytest.fixture
def internal_offer_response_email_settings(offer_email_settings, settings):
    settings.SERVER_EMAIL = "notifications@example.com"
    settings.INQUIRY_INTERNAL_NOTIFICATION_EMAILS = ["ops@example.com"]


@pytest.mark.django_db(transaction=True)
def test_offer_sent_email_is_sent_once_on_true_status_entry(
    django_user_model,
    offer_email_settings,
) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="offer_email_once",
        status=Inquiry.Status.IN_REVIEW,
    )
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("555.00"),
        currency="EUR",
        lead_time_text="72h",
    )

    mail.outbox.clear()
    offer.mark_sent(save=True)
    assert len(mail.outbox) == 1

    offer.internal_notes = "Actualizacion interna"
    offer.save(update_fields=["internal_notes"])
    assert len(mail.outbox) == 1


@pytest.mark.django_db(transaction=True)
def test_offer_sent_email_contains_tokenized_public_url_and_summary(
    django_user_model,
    offer_email_settings,
) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="offer_email_content",
        status=Inquiry.Status.IN_REVIEW,
    )
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("410.00"),
        currency="EUR",
        lead_time_text="5-7 dias laborables",
        customer_message="Disponibilidad confirmada para el lote solicitado.",
    )

    mail.outbox.clear()
    offer.mark_sent(save=True)

    assert len(mail.outbox) == 1
    email = mail.outbox[0]
    expected_url = (
        "https://recambios.example"
        + reverse(
            "inquiries:public_inquiry_offer_detail",
            kwargs={"access_token": offer.access_token},
        )
    )

    assert offer.reference_code in email.subject
    assert inquiry.reference_code in email.body
    assert offer.reference_code in email.body
    assert "Importe total confirmado:" in email.body
    assert "410" in email.body
    assert "EUR" in email.body
    assert "5-7 dias laborables" in email.body
    assert "Disponibilidad confirmada para el lote solicitado." in email.body
    assert (
        "La disponibilidad final se confirma en el momento de tramitación del pago."
        in email.body
    )
    assert expected_url in email.body


@pytest.mark.django_db(transaction=True)
def test_offer_sent_email_recipient_prefers_registered_user_email(
    django_user_model,
    offer_email_settings,
) -> None:
    user = django_user_model.objects.create_user(
        username="offer_email_user_priority",
        email="priority@example.com",
        password="pass1234",
    )
    inquiry = Inquiry.objects.create(
        user=user,
        guest_name="Guest Name",
        guest_email="guest-fallback@example.com",
        status=Inquiry.Status.IN_REVIEW,
    )
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("720.00"),
        currency="EUR",
        lead_time_text="10 dias",
    )

    mail.outbox.clear()
    offer.mark_sent(save=True)

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["priority@example.com"]


@pytest.mark.django_db(transaction=True)
def test_offer_sent_email_recipient_falls_back_to_guest_email(
    offer_email_settings,
) -> None:
    inquiry = Inquiry.objects.create(
        guest_name="Guest Buyer",
        guest_email="guest-offer@example.com",
        status=Inquiry.Status.IN_REVIEW,
    )
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("615.00"),
        currency="EUR",
        lead_time_text="4 dias",
    )

    mail.outbox.clear()
    offer.mark_sent(save=True)

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["guest-offer@example.com"]


@pytest.mark.django_db(transaction=True)
def test_offer_sent_email_missing_recipient_does_not_break_status_transition(
    django_user_model,
    offer_email_settings,
    caplog,
) -> None:
    user = django_user_model.objects.create_user(
        username="offer_email_missing_recipient",
        email="",
        password="pass1234",
    )
    inquiry = Inquiry.objects.create(
        user=user,
        status=Inquiry.Status.IN_REVIEW,
    )
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("800.00"),
        currency="EUR",
        lead_time_text="6 dias",
    )

    mail.outbox.clear()
    with caplog.at_level("WARNING", logger="apps.inquiries.emails"):
        offer.mark_sent(save=True)

    offer.refresh_from_db()
    assert offer.status == InquiryOffer.Status.SENT
    assert len(mail.outbox) == 0
    assert any(
        "Customer offer email skipped due to missing recipient email" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.django_db(transaction=True)
def test_offer_sent_email_renders_english_content_when_inquiry_language_is_en(
    django_user_model,
    offer_email_settings,
) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="offer_email_english",
        status=Inquiry.Status.IN_REVIEW,
    )
    inquiry.language = Inquiry.Language.ENGLISH
    inquiry.save(update_fields=["language"])
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("299.99"),
        currency="EUR",
        lead_time_text="3 business days",
    )

    mail.outbox.clear()
    offer.mark_sent(save=True)

    assert len(mail.outbox) == 1
    email = mail.outbox[0]
    assert "Confirmed offer available:" in email.subject
    assert "Offer summary:" in email.body
    assert "Review the offer and respond (accept or reject) using this secure link:" in email.body


@pytest.mark.django_db(transaction=True)
def test_admin_send_action_triggers_offer_sent_email_for_valid_offers_only(
    django_user_model,
    offer_email_settings,
) -> None:
    valid_inquiry = make_inquiry(
        django_user_model,
        username="offer_email_admin_valid",
        status=Inquiry.Status.IN_REVIEW,
    )
    invalid_inquiry = make_inquiry(
        django_user_model,
        username="offer_email_admin_invalid",
        status=Inquiry.Status.IN_REVIEW,
    )
    valid_offer = InquiryOffer.objects.create(
        inquiry=valid_inquiry,
        confirmed_total=Decimal("650.00"),
        currency="EUR",
        lead_time_text="5 dias",
    )
    invalid_offer = InquiryOffer.objects.create(
        inquiry=invalid_inquiry,
        confirmed_total=Decimal("510.00"),
        currency="EUR",
        lead_time_text="",
    )
    admin_user = django_user_model.objects.create_superuser(
        username="offer_email_admin_user",
        email="offer_email_admin_user@example.com",
        password="pass1234",
    )
    request = RequestFactory().post("/admin/inquiries/inquiryoffer/")
    request.user = admin_user
    offer_admin = InquiryOfferAdmin(InquiryOffer, AdminSite())
    offer_admin.message_user = lambda *args, **kwargs: None

    mail.outbox.clear()
    offer_admin.mark_selected_as_sent(
        request,
        InquiryOffer.objects.filter(pk__in=[valid_offer.pk, invalid_offer.pk]),
    )

    valid_offer.refresh_from_db()
    invalid_offer.refresh_from_db()
    assert valid_offer.status == InquiryOffer.Status.SENT
    assert invalid_offer.status == InquiryOffer.Status.DRAFT
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["offer_email_admin_valid@example.com"]


@pytest.mark.django_db(transaction=True)
def test_offer_sent_email_failure_is_logged_and_offer_state_is_kept_as_sent(
    django_user_model,
    offer_email_settings,
    caplog,
) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="offer_email_send_failure",
        status=Inquiry.Status.IN_REVIEW,
    )
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("710.00"),
        currency="EUR",
        lead_time_text="8 dias",
    )

    with patch("apps.inquiries.emails.EmailMessage.send", side_effect=RuntimeError("smtp down")):
        with caplog.at_level("ERROR", logger="apps.inquiries.signals"):
            offer.mark_sent(save=True)

    offer.refresh_from_db()
    assert offer.status == InquiryOffer.Status.SENT
    assert any(
        "Failed to send customer offer email" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.django_db(transaction=True)
def test_internal_offer_response_email_is_sent_once_on_true_accept_entry(
    django_user_model,
    internal_offer_response_email_settings,
) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="offer_internal_accept_once",
        status=Inquiry.Status.IN_REVIEW,
    )
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("470.00"),
        currency="EUR",
        lead_time_text="5 days",
    )
    offer.mark_sent(save=True)

    mail.outbox.clear()
    offer.mark_accepted(save=True)
    assert len(mail.outbox) == 1
    internal_email = mail.outbox[0]
    assert internal_email.to == ["ops@example.com"]
    assert "Oferta aceptada por cliente:" in internal_email.subject

    offer.internal_notes = "Seguimiento interno"
    offer.save(update_fields=["internal_notes"])
    assert len(mail.outbox) == 1


@pytest.mark.django_db(transaction=True)
def test_internal_offer_response_email_is_sent_once_on_true_reject_entry(
    django_user_model,
    internal_offer_response_email_settings,
) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="offer_internal_reject_once",
        status=Inquiry.Status.IN_REVIEW,
    )
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("520.00"),
        currency="EUR",
        lead_time_text="5 days",
    )
    offer.mark_sent(save=True)

    mail.outbox.clear()
    offer.mark_rejected(save=True)
    assert len(mail.outbox) == 1
    internal_email = mail.outbox[0]
    assert internal_email.to == ["ops@example.com"]
    assert "Oferta rechazada por cliente:" in internal_email.subject

    offer.internal_notes = "Sin cambios comerciales"
    offer.save(update_fields=["internal_notes"])
    assert len(mail.outbox) == 1


@pytest.mark.django_db(transaction=True)
def test_internal_offer_response_email_renders_english_content(
    django_user_model,
    internal_offer_response_email_settings,
) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="offer_internal_email_en",
        status=Inquiry.Status.IN_REVIEW,
    )
    inquiry.language = Inquiry.Language.ENGLISH
    inquiry.save(update_fields=["language"])
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("399.99"),
        currency="EUR",
        lead_time_text="3 business days",
    )
    offer.mark_sent(save=True)

    mail.outbox.clear()
    offer.mark_accepted(save=True)

    assert len(mail.outbox) == 1
    internal_email = mail.outbox[0]
    assert "Offer accepted by customer:" in internal_email.subject
    assert "The customer has accepted an offer." in internal_email.body
    assert "Expected next step: payment management with the customer." in internal_email.body


@pytest.mark.django_db(transaction=True)
def test_internal_offer_response_email_failure_is_logged_and_state_is_kept(
    django_user_model,
    internal_offer_response_email_settings,
    caplog,
) -> None:
    inquiry = make_inquiry(
        django_user_model,
        username="offer_internal_email_failure",
        status=Inquiry.Status.IN_REVIEW,
    )
    offer = InquiryOffer.objects.create(
        inquiry=inquiry,
        confirmed_total=Decimal("580.00"),
        currency="EUR",
        lead_time_text="4 days",
    )
    offer.mark_sent(save=True)

    with patch("apps.inquiries.emails.EmailMessage.send", side_effect=RuntimeError("smtp down")):
        with caplog.at_level("ERROR", logger="apps.inquiries.signals"):
            offer.mark_accepted(save=True)

    offer.refresh_from_db()
    assert offer.status == InquiryOffer.Status.ACCEPTED
    assert any(
        "Failed to send internal offer-response notification email" in record.getMessage()
        for record in caplog.records
    )
