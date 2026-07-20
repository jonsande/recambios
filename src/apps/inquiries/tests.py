from decimal import Decimal

from django.test import TestCase

from apps.catalog.models import Category, Condition, Product
from apps.suppliers.models import Supplier

from .models import Inquiry, InquiryItem, InquiryOffer


class OfferLastKnownPriceUpdateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        supplier = Supplier.objects.create(
            name="Offer Supplier", slug="offer-supplier", code="OFFER-SUP", is_active=True
        )
        category = Category.objects.create(
            name="Offer Category", slug="offer-category", is_active=True
        )
        condition = Condition.objects.create(
            code="offer-new", name="New", slug="offer-new", is_active=True
        )
        cls.product = Product.objects.create(
            supplier=supplier,
            sku="OFFER-001",
            title="Offered product",
            category=category,
            condition=condition,
            last_known_price=Decimal("10.00"),
            product_vat_rate=Decimal("21.00"),
        )

    def _create_offer(self, *, update_price=True, vat_applicable=True):
        inquiry = Inquiry.objects.create(
            guest_name="Test Customer",
            guest_email="customer@example.com",
            status=Inquiry.Status.IN_REVIEW,
            destination_country="ES",
            destination_city="Madrid",
            destination_region="Madrid",
            destination_postal_code="28001",
        )
        InquiryItem.objects.create(
            inquiry=inquiry,
            product=self.product,
            requested_quantity=3,
        )
        return InquiryOffer.objects.create(
            inquiry=inquiry,
            product_price=Decimal("100.00"),
            shipping_price=Decimal("0.00"),
            product_vat_applicable=vat_applicable,
            product_vat_rate=Decimal("10.00"),
            shipping_vat_applicable=False,
            lead_time_text="48 hours",
            currency="USD",
            update_product_last_known_price=update_price,
        )

    def test_mark_sent_updates_unit_net_price_vat_currency_and_date(self):
        offer = self._create_offer()

        offer.mark_sent()

        self.product.refresh_from_db()
        self.assertEqual(self.product.last_known_price, Decimal("33.33"))
        self.assertEqual(self.product.product_vat_rate, Decimal("10.00"))
        self.assertEqual(self.product.currency, "USD")
        self.assertEqual(
            self.product.price_visibility_mode,
            Product.PriceVisibilityMode.VISIBLE_INFO,
        )
        self.assertIsNotNone(self.product.last_known_price_updated_at)

    def test_mark_sent_does_not_update_product_when_option_is_disabled(self):
        original_updated_at = self.product.last_known_price_updated_at
        offer = self._create_offer(update_price=False)

        offer.mark_sent()

        self.product.refresh_from_db()
        self.assertEqual(self.product.last_known_price, Decimal("10.00"))
        self.assertEqual(self.product.product_vat_rate, Decimal("21.00"))
        self.assertEqual(self.product.currency, "EUR")
        self.assertEqual(
            self.product.price_visibility_mode,
            Product.PriceVisibilityMode.HIDDEN,
        )
        self.assertEqual(self.product.last_known_price_updated_at, original_updated_at)

    def test_mark_sent_saves_zero_vat_when_offer_does_not_apply_vat(self):
        offer = self._create_offer(vat_applicable=False)

        offer.mark_sent()

        self.product.refresh_from_db()
        self.assertEqual(self.product.product_vat_rate, Decimal("0.00"))
