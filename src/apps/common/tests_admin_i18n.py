from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.catalog.admin import ProductAdmin
from apps.catalog.models import Category, Product
from apps.inquiries.models import Inquiry, InquiryItem, InquiryOffer, InquiryOfferPayment


class AdminSpanishLanguageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="admin-i18n",
            email="admin-i18n@example.com",
            password="test-password",
        )

    def test_admin_is_spanish_even_with_public_english_cookie(self):
        self.client.force_login(self.user)
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"

        response = self.client.get(reverse("admin:index"), HTTP_ACCEPT_LANGUAGE="en")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Language"], "es")
        self.assertContains(response, "Administración de")
        self.assertContains(response, settings.SITE_BRAND_NAME_ES)
        self.assertContains(response, "Gestión interna")
        self.assertContains(response, "Añadir")

    def test_public_english_request_remains_english(self):
        response = self.client.get("/en/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Language"], "en")
        self.assertContains(response, 'lang="en"')

    def test_project_admin_metadata_is_natural_spanish(self):
        self.assertEqual(str(Category._meta.verbose_name_plural), "categorías")
        self.assertEqual(str(Inquiry._meta.verbose_name), "solicitud")
        self.assertEqual(str(InquiryOffer._meta.verbose_name_plural), "ofertas")
        self.assertEqual(str(InquiryOfferPayment.Status.PAID.label), "Pagado")

    def test_representative_admin_labels_are_spanish(self):
        model_admin = ProductAdmin(Product, admin.site)

        self.assertEqual(
            str(model_admin.mark_selected_as_published.short_description),
            "Cambiar el estado de publicación a Publicado",
        )
        self.assertEqual(str(model_admin.fieldsets[0][0]), "Identificación del producto")

    def test_admin_exposed_model_fields_have_explicit_spanish_labels(self):
        expected_labels = {
            Inquiry: {
                "user": "usuario",
                "negative_resolution_reason": "motivo de resolución no ofertable",
                "response_due_at": "fecha límite de respuesta",
                "destination_country": "país de destino",
            },
            InquiryItem: {
                "product": "producto",
                "requested_quantity": "cantidad solicitada",
                "last_known_price_snapshot": "último precio conocido al solicitar",
                "customer_note": "nota del cliente",
            },
            Product: {
                "supplier": "proveedor",
                "supplier_product_code": "código de producto del proveedor",
                "category": "categoría",
                "condition": "estado del producto",
                "unit_of_sale": "unidad de venta",
                "weight": "peso",
            },
        }

        for model, fields in expected_labels.items():
            for field_name, expected_label in fields.items():
                with self.subTest(model=model._meta.label, field=field_name):
                    self.assertEqual(
                        str(model._meta.get_field(field_name).verbose_name),
                        expected_label,
                    )
