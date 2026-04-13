from django.test import TestCase

from apps.imports.rg_pipeline import _ensure_supplier
from apps.suppliers.models import Supplier


class EnsureRGSupplierTests(TestCase):
    def test_reuses_existing_supplier_when_slug_matches(self):
        existing = Supplier.objects.create(
            name="RG GmbH",
            slug="rg-gmbh",
            code="RG",
            country="",
            website="",
            is_active=False,
        )

        supplier = _ensure_supplier()

        self.assertEqual(supplier.pk, existing.pk)
        supplier.refresh_from_db()
        self.assertEqual(supplier.code, "RG-GMBH")
        self.assertEqual(supplier.country, "Germany")
        self.assertEqual(supplier.website, "https://www.rg-gmbh.de/en/")
        self.assertTrue(supplier.is_active)
