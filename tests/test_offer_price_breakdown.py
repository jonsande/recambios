from decimal import Decimal

import pytest
from django.template.loader import render_to_string

from apps.inquiries.models import Inquiry, InquiryOffer


def make_inquiry(django_user_model, username: str) -> Inquiry:
    user = django_user_model.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass1234"
    )
    return Inquiry.objects.create(
        user=user,
        status=Inquiry.Status.IN_REVIEW,
        destination_country="ES",
        destination_city="Madrid",
        destination_region="Madrid",
        destination_postal_code="28001",
    )


@pytest.mark.django_db
def test_offer_calculates_product_shipping_and_total_with_independent_vat(
    django_user_model,
) -> None:
    offer = InquiryOffer.objects.create(
        inquiry=make_inquiry(django_user_model, "price_breakdown"),
        product_price=Decimal("100.00"),
        shipping_price=Decimal("10.00"),
        product_vat_applicable=True,
        product_vat_rate=Decimal("21.00"),
        shipping_vat_applicable=True,
        shipping_vat_rate=Decimal("10.00"),
        currency="EUR",
    )

    assert offer.product_price_with_vat == Decimal("121.00")
    assert offer.shipping_price_with_vat == Decimal("11.00")
    assert offer.confirmed_total == Decimal("132.00")


@pytest.mark.django_db
def test_customer_offer_email_shows_vat_inclusive_breakdown(django_user_model) -> None:
    offer = InquiryOffer.objects.create(
        inquiry=make_inquiry(django_user_model, "email_breakdown"),
        product_price=Decimal("200.00"),
        shipping_price=Decimal("20.00"),
        currency="EUR",
    )

    body = render_to_string(
        "inquiries/emails/customer_offer_sent_body.txt",
        {"offer": offer, "inquiry": offer.inquiry},
    )

    assert "Precio del producto (IVA incluido):" in body
    assert "242" in body
    assert "Gastos de envío (IVA incluido):" in body
    assert "24,20" in body or "24.20" in body
    assert "Importe total confirmado:" in body
    assert "266,20" in body or "266.20" in body
