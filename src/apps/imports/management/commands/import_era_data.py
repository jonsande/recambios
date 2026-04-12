"""
Import ERA product data from JSON into the database.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import (
    Brand,
    Category,
    Condition,
    PartNumber,
    PartNumberType,
    Product,
)
from apps.suppliers.models import Supplier
from apps.vehicles.models import ProductVehicleFitment, Vehicle


class Command(BaseCommand):
    help = "Import ERA product data from JSON"

    def add_arguments(self, parser):
        parser.add_argument(
            "json_file",
            type=str,
            nargs="?",
            default="era_data/era_products.json",
            help="Path to JSON file (default: era_data/era_products.json)",
        )

    def handle(self, *args, **options):
        json_path = Path(options["json_file"])

        if not json_path.exists():
            self.stderr.write(self.style.ERROR(f"File not found: {json_path}"))
            return

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        products_data = data.get("products", [])
        self.stdout.write(f"Found {len(products_data)} products in JSON")

        with transaction.atomic():
            created = self._import_data(products_data)

        self.stdout.write(self.style.SUCCESS(f"Import complete: {created}"))

    def _import_data(self, products_data: list) -> dict:
        created = {
            "supplier": 0,
            "brands": 0,
            "categories": 0,
            "part_number_types": 0,
            "products": 0,
            "part_numbers": 0,
            "vehicle_brands": 0,
            "vehicles": 0,
            "fitments": 0,
        }

        supplier = self._get_or_create_supplier()
        created["supplier"] = 1

        part_number_type_oe, pn_oe_created = PartNumberType.objects.get_or_create(
            code="OEM",
            defaults={"name": "OEM Reference", "sort_order": 10},
        )
        if pn_oe_created:
            created["part_number_types"] += 1

        part_number_type_era, pn_era_created = PartNumberType.objects.get_or_create(
            code="ERA",
            defaults={"name": "ERA Part Number", "sort_order": 20},
        )
        if pn_era_created:
            created["part_number_types"] += 1

        default_condition, _ = Condition.objects.get_or_create(
            code="NEW",
            defaults={"name": "New", "slug": "new"},
        )

        era_brand = self._get_or_create_brand("ERA", brand_type=Brand.BrandType.PARTS)
        created["brands"] += 1

        category_cache = {}
        processed_refs = set()

        for prod_data in products_data:
            reference = prod_data["reference"]

            if reference in processed_refs:
                continue
            processed_refs.add(reference)

            category_names = prod_data.get("category_names", ["Sensores"])
            category_name = category_names[0] if category_names else "Sensores"

            category = self._get_or_create_category(category_name, category_cache, created)

            title = prod_data.get("description", f"ERA Product {reference}")
            if title.startswith("ERA Sensor"):
                title = f"Coolant Temperature Sensor {reference}"

            sku = f"ERA-{reference}"

            product, product_created = Product.objects.get_or_create(
                sku=sku,
                defaults={
                    "supplier": supplier,
                    "supplier_product_code": reference,
                    "title": title,
                    "short_description": f"ERA {category_name} sensor",
                    "brand": era_brand,
                    "category": category,
                    "condition": default_condition,
                    "publication_status": Product.PublicationStatus.DRAFT,
                    "is_active": True,
                },
            )

            if product_created:
                created["products"] += 1

                PartNumber.objects.get_or_create(
                    product=product,
                    number_raw=reference,
                    part_number_type=part_number_type_era,
                    defaults={"is_primary": True},
                )
                created["part_numbers"] += 1

                for oe_data in prod_data.get("oe_numbers", []):
                    brand_name = oe_data.get("brand", "")
                    if brand_name:
                        brand = self._get_or_create_brand(brand_name, Brand.BrandType.PARTS)
                        created["brands"] += 1

                        for number in oe_data.get("numbers", [])[:10]:
                            PartNumber.objects.get_or_create(
                                product=product,
                                brand=brand,
                                number_raw=number,
                                part_number_type=part_number_type_oe,
                                defaults={"is_primary": False},
                            )
                            created["part_numbers"] += 1

                for app_data in prod_data.get("applications", []):
                    brand_name = app_data.get("brand", "")
                    if brand_name:
                        vehicle_brand = self._get_or_create_brand(
                            brand_name, Brand.BrandType.VEHICLE
                        )

                        if brand_name not in category_cache:
                            created["vehicle_brands"] += 1

                        for model_name in app_data.get("models", [])[:20]:
                            model_name = model_name.strip()
                            if len(model_name) < 2:
                                continue

                            vehicle, vehicle_created = Vehicle.objects.get_or_create(
                                brand=vehicle_brand,
                                model=model_name,
                                defaults={
                                    "vehicle_type": Vehicle.VehicleType.CAR,
                                },
                            )

                            if vehicle_created:
                                created["vehicles"] += 1

                            fitment, fitment_created = ProductVehicleFitment.objects.get_or_create(
                                product=product,
                                vehicle=vehicle,
                                defaults={
                                    "source": ProductVehicleFitment.FitmentSource.IMPORT,
                                },
                            )

                            if fitment_created:
                                created["fitments"] += 1

        self.stdout.write(f"  Supplier: {created['supplier']}")
        self.stdout.write(f"  Brands: {created['brands']}")
        self.stdout.write(f"  Categories: {created['categories']}")
        self.stdout.write(f"  Part Number Types: {created['part_number_types']}")
        self.stdout.write(f"  Products: {created['products']}")
        self.stdout.write(f"  Part Numbers: {created['part_numbers']}")
        self.stdout.write(f"  Vehicle Brands: {created['vehicle_brands']}")
        self.stdout.write(f"  Vehicles: {created['vehicles']}")
        self.stdout.write(f"  Fitments: {created['fitments']}")

        return created

    def _get_or_create_supplier(self) -> Supplier:
        supplier, created = Supplier.objects.get_or_create(
            code="ERA",
            defaults={
                "name": "ERA",
                "slug": "era",
                "country": "Italy",
                "website": "https://www.eraspares.es",
            },
        )
        if created:
            self.stdout.write(f"Created supplier: {supplier.name}")
        return supplier

    def _get_or_create_brand(
        self, name: str, brand_type: str = Brand.BrandType.PARTS
    ) -> Brand:
        slug = slugify(name)
        brand, created = Brand.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "brand_type": brand_type,
            },
        )
        if created:
            self.stdout.write(f"  Created brand: {name}")
        return brand

    def _get_or_create_category(
        self, name: str, cache: dict, created: dict = None
    ) -> Category:
        if name in cache:
            return cache[name]

        slug = slugify(name)
        category, is_new = Category.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
            },
        )

        if is_new:
            if created is not None:
                created["categories"] += 1
            self.stdout.write(f"  Created category: {name}")

        cache[name] = category
        return category
