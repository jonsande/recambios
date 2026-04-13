from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.suppliers.models import Supplier
from apps.vehicles.models import ProductVehicleFitment, Vehicle

from .models import Brand, Category, Condition, Product


class ProductListVehicleModelFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        supplier = Supplier.objects.create(
            name="Supplier A",
            slug="supplier-a",
            code="SUP-A",
            is_active=True,
        )
        category = Category.objects.create(
            name="Alternators",
            slug="alternators",
            is_active=True,
        )
        condition = Condition.objects.create(
            code="new",
            name="New",
            slug="new",
            is_active=True,
        )

        product = Product.objects.create(
            supplier=supplier,
            sku="SKU-001",
            title="Alternator test",
            category=category,
            condition=condition,
            publication_status=Product.PublicationStatus.PUBLISHED,
            published_at=timezone.now(),
            is_active=True,
        )

        audi_brand = Brand.objects.create(
            name="Audi",
            slug="audi",
            brand_type=Brand.BrandType.VEHICLE,
            is_active=True,
        )
        bmw_brand = Brand.objects.create(
            name="BMW",
            slug="bmw",
            brand_type=Brand.BrandType.VEHICLE,
            is_active=True,
        )

        audi_a3 = Vehicle.objects.create(
            brand=audi_brand,
            model="A3",
            vehicle_type=Vehicle.VehicleType.CAR,
            is_active=True,
        )
        audi_a4 = Vehicle.objects.create(
            brand=audi_brand,
            model="A4",
            vehicle_type=Vehicle.VehicleType.CAR,
            is_active=True,
        )
        bmw_x5 = Vehicle.objects.create(
            brand=bmw_brand,
            model="X5",
            vehicle_type=Vehicle.VehicleType.CAR,
            is_active=True,
        )

        ProductVehicleFitment.objects.create(product=product, vehicle=audi_a3)
        ProductVehicleFitment.objects.create(product=product, vehicle=audi_a4)
        ProductVehicleFitment.objects.create(product=product, vehicle=bmw_x5)

    def test_model_options_are_filtered_by_selected_brand(self):
        response = self.client.get(reverse("catalog:product_list"), {"brand": "audi"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_vehicle_brand_slug"], "audi")
        self.assertEqual(response.context["model_options"], ["A3", "A4"])

    def test_model_options_include_all_models_when_brand_not_selected(self):
        response = self.client.get(reverse("catalog:product_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["model_options"], ["A3", "A4", "X5"])
