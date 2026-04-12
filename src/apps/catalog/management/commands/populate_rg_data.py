from datetime import datetime, timezone
from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.catalog.models import Brand, Category, Condition, PartNumber, PartNumberType, Product
from apps.suppliers.models import Supplier
from apps.vehicles.models import ProductVehicleFitment, Vehicle


class Command(BaseCommand):
    help = "Populate database with sample data from RG GmbH supplier"

    def handle(self, *args, **options):
        self.stdout.write("Populating database with RG GmbH sample data...")

        supplier = self._create_supplier()
        conditions = self._create_conditions()
        categories = self._create_categories()
        brands = self._create_brands()
        vehicles = self._create_vehicles(brands)
        self._create_products(supplier, conditions, categories, brands, vehicles)

        self.stdout.write(self.style.SUCCESS("Database populated successfully!"))

    def _create_supplier(self) -> Supplier:
        supplier, created = Supplier.objects.get_or_create(
            code="RG-GMBH",
            defaults={
                "name": "RG GmbH",
                "slug": "rg-gmbh",
                "country": "Germany",
                "website": "https://www.rg-gmbh.de",
                "contact_name": "RG GmbH Team",
                "contact_email": "info@rg-gmbh.de",
                "contact_phone": "+49 (0)9351 6020-0",
                "is_active": True,
            },
        )
        if created:
            self.stdout.write(f"  Created supplier: {supplier.name}")
        else:
            self.stdout.write(f"  Supplier already exists: {supplier.name}")
        return supplier

    def _get_part_number_types(self) -> dict[str, PartNumberType]:
        part_number_types: dict[str, PartNumberType] = {}
        for index, code in enumerate(PartNumberType.REQUIRED_BASE_CODES, start=1):
            part_number_type, _ = PartNumberType.objects.get_or_create(
                code=code,
                defaults={
                    "name": code,
                    "sort_order": index,
                    "is_active": True,
                },
            )
            part_number_types[code] = part_number_type
        return part_number_types

    def _map_sample_part_number_type(self, raw_type: str) -> str:
        normalized = (raw_type or "").strip().lower()
        if normalized == "oem":
            return "OEM"
        if normalized == "oe":
            return "OES"
        return "AIM"

    def _create_conditions(self) -> dict:
        conditions_data = [
            {
                "code": "new",
                "name": "New",
                "slug": "new",
                "description": "Brand new part",
            },
            {
                "code": "take_off",
                "name": "New - Take off",
                "slug": "new-take-off",
                "description": "New part removed from vehicle",
            },
            {
                "code": "refurbished",
                "name": "Rebuilt",
                "slug": "rebuilt",
                "description": "Refurbished/rebuilt part",
            },
            {
                "code": "used",
                "name": "Used",
                "slug": "used",
                "description": "Used part in good condition",
            },
            {
                "code": "exchange",
                "name": "Exchange",
                "slug": "exchange",
                "description": "Exchange part/core",
            },
            {
                "code": "second_quality",
                "name": "II. Choice",
                "slug": "ii-choice",
                "description": "Second quality part",
            },
        ]

        conditions = {}
        for data in conditions_data:
            obj, created = Condition.objects.get_or_create(
                code=data["code"],
                defaults={
                    "name": data["name"],
                    "slug": data["slug"],
                    "description": data["description"],
                },
            )
            conditions[data["code"]] = obj
            if created:
                self.stdout.write(f"  Created condition: {obj.name}")

        return conditions

    def _create_categories(self) -> dict:
        categories_data = [
            {
                "name": "Starters & Alternators",
                "slug": "starters-alternators",
                "parent": None,
            },
            {
                "name": "Starter",
                "slug": "starter",
                "parent": "starters-alternators",
            },
            {
                "name": "Alternators",
                "slug": "alternators",
                "parent": "starters-alternators",
            },
            {"name": "Brakes", "slug": "brakes", "parent": None},
            {
                "name": "Brake Parts",
                "slug": "brake-parts",
                "parent": "brakes",
            },
            {"name": "Injection", "slug": "injection", "parent": None},
            {
                "name": "Injectors",
                "slug": "injectors",
                "parent": "injection",
            },
            {
                "name": "High Pressure Pumps",
                "slug": "high-pressure-pumps",
                "parent": "injection",
            },
            {
                "name": "Turbochargers",
                "slug": "turbochargers",
                "parent": None,
            },
            {
                "name": "Turbocharger",
                "slug": "turbocharger",
                "parent": "turbochargers",
            },
            {
                "name": "Climate Control",
                "slug": "climate-control",
                "parent": None,
            },
            {
                "name": "Air Conditioning Compressors",
                "slug": "air-conditioning-compressors",
                "parent": "climate-control",
            },
            {"name": "Sensors", "slug": "sensors", "parent": None},
            {
                "name": "Sensors + Lambda Sensors",
                "slug": "sensors-lambda-sensors",
                "parent": "sensors",
            },
            {"name": "Ignition", "slug": "ignition", "parent": None},
            {
                "name": "Ignition Coils",
                "slug": "ignition-coils",
                "parent": "ignition",
            },
            {
                "name": "Spark Plugs",
                "slug": "spark-plugs",
                "parent": "ignition",
            },
            {"name": "Steering", "slug": "steering", "parent": None},
            {
                "name": "Steering + Servo Pumps",
                "slug": "steering-servo-pumps",
                "parent": "steering",
            },
            {"name": "Drivetrain", "slug": "drivetrain", "parent": None},
            {
                "name": "Transmission",
                "slug": "transmission",
                "parent": "drivetrain",
            },
            {
                "name": "Flywheels / Clutches",
                "slug": "flywheels-clutches",
                "parent": "drivetrain",
            },
            {
                "name": "Suspension",
                "slug": "suspension",
                "parent": None,
            },
            {
                "name": "Shock Absorbers / Springs / Axles",
                "slug": "shock-absorbers-springs-axles",
                "parent": "suspension",
            },
            {
                "name": "Wheel Bearings",
                "slug": "wheel-bearings",
                "parent": "suspension",
            },
            {
                "name": "Air Flow Meters",
                "slug": "air-flow-meters",
                "parent": None,
            },
            {
                "name": "Air Flow Meter",
                "slug": "air-flow-meter",
                "parent": "air-flow-meters",
            },
            {
                "name": "Thermostats",
                "slug": "thermostats",
                "parent": None,
            },
            {
                "name": "Thermostat",
                "slug": "thermostat",
                "parent": "thermostats",
            },
            {"name": "Engines", "slug": "engines", "parent": None},
            {
                "name": "Engine",
                "slug": "engine",
                "parent": "engines",
            },
            {"name": "Wheels", "slug": "wheels", "parent": None},
            {
                "name": "Rim",
                "slug": "rim",
                "parent": "wheels",
            },
            {"name": "Tires", "slug": "tires", "parent": "wheels"},
            {"name": "Specials", "slug": "specials", "parent": None},
            {
                "name": "Special Items",
                "slug": "special-items",
                "parent": "specials",
            },
        ]

        categories = {}
        category_map = {}

        for data in categories_data:
            parent_slug = data.pop("parent")
            parent = category_map.get(parent_slug) if parent_slug else None

            obj, created = Category.objects.get_or_create(
                slug=data["slug"],
                defaults={
                    "name": data["name"],
                    "parent": parent,
                    "is_active": True,
                },
            )
            category_map[data["slug"]] = obj
            categories[data["slug"]] = obj
            if created:
                self.stdout.write(f"  Created category: {obj.name}")

        return categories

    def _create_brands(self) -> dict:
        brands_data = [
            {"name": "Denso", "slug": "denso", "country": "Japan"},
            {"name": "Bosch", "slug": "bosch", "country": "Germany"},
            {"name": "Valeo", "slug": "valeo", "country": "France"},
            {"name": "SEG", "slug": "seg", "country": "Germany"},
            {"name": "Nippondenso", "slug": "nippondenso", "country": "Japan"},
            {"name": "Garrett", "slug": "garrett", "country": "USA"},
            {"name": "BorgWarner", "slug": "borgwarner", "country": "USA"},
            {"name": "MAHLE", "slug": "mahle", "country": "Germany"},
            {"name": "KKK", "slug": "kkk", "country": "Germany"},
            {"name": "Continental", "slug": "continental", "country": "Germany"},
            {"name": "Holset", "slug": "holset", "country": "USA"},
            {"name": "MHI", "slug": "mhi", "country": "Japan"},
            {"name": "Sanden", "slug": "sanden", "country": "Japan"},
            {"name": "AC Edge", "slug": "ac-edge", "country": "USA"},
            {"name": "BMW", "slug": "bmw", "country": "Germany"},
            {"name": "Mercedes-Benz", "slug": "mercedes-benz", "country": "Germany"},
            {"name": "Audi", "slug": "audi", "country": "Germany"},
            {"name": "Volkswagen", "slug": "volkswagen", "country": "Germany"},
            {"name": "Ford", "slug": "ford", "country": "USA"},
            {"name": "Opel", "slug": "opel", "country": "Germany"},
            {"name": "Renault", "slug": "renault", "country": "France"},
            {"name": "Peugeot", "slug": "peugeot", "country": "France"},
            {"name": "Citroen", "slug": "citroen", "country": "France"},
            {"name": "Fiat", "slug": "fiat", "country": "Italy"},
            {"name": "Alfa Romeo", "slug": "alfa-romeo", "country": "Italy"},
            {"name": "Toyota", "slug": "toyota", "country": "Japan"},
            {"name": "Honda", "slug": "honda", "country": "Japan"},
            {"name": "Nissan", "slug": "nissan", "country": "Japan"},
            {"name": "Hyundai", "slug": "hyundai", "country": "South Korea"},
            {"name": "Kia", "slug": "kia", "country": "South Korea"},
        ]

        brands = {}
        for data in brands_data:
            obj, created = Brand.objects.get_or_create(
                slug=data["slug"],
                defaults={
                    "name": data["name"],
                    "country": data["country"],
                    "brand_type": Brand.BrandType.PARTS,
                    "is_active": True,
                },
            )
            brands[data["slug"]] = obj
            if created:
                self.stdout.write(f"  Created brand: {obj.name}")

        return brands

    def _create_vehicles(self, brands: dict) -> dict:
        vehicles_data = [
            {
                "brand": "bmw",
                "model": "3 Series",
                "generation": "G20",
                "variant": "320d",
                "year_start": 2019,
                "year_end": 2023,
                "engine_code": "B47D20",
                "fuel_type": Vehicle.FuelType.DIESEL,
                "displacement_cc": 1995,
                "power_hp": 190,
                "power_kw": 140,
            },
            {
                "brand": "bmw",
                "model": "3 Series",
                "generation": "G20",
                "variant": "330i",
                "year_start": 2019,
                "year_end": 2023,
                "engine_code": "B48B20",
                "fuel_type": Vehicle.FuelType.GASOLINE,
                "displacement_cc": 1998,
                "power_hp": 258,
                "power_kw": 190,
            },
            {
                "brand": "bmw",
                "model": "5 Series",
                "generation": "G30",
                "variant": "520d",
                "year_start": 2017,
                "year_end": 2023,
                "engine_code": "B47D20",
                "fuel_type": Vehicle.FuelType.DIESEL,
                "displacement_cc": 1995,
                "power_hp": 190,
                "power_kw": 140,
            },
            {
                "brand": "bmw",
                "model": "7 Series",
                "generation": "G11",
                "variant": "730d",
                "year_start": 2015,
                "year_end": 2022,
                "engine_code": "N57D30",
                "fuel_type": Vehicle.FuelType.DIESEL,
                "displacement_cc": 2993,
                "power_hp": 265,
                "power_kw": 195,
            },
            {
                "brand": "bmw",
                "model": "X3",
                "generation": "G01",
                "variant": "xDrive30d",
                "year_start": 2017,
                "year_end": 2023,
                "engine_code": "B57D30",
                "fuel_type": Vehicle.FuelType.DIESEL,
                "displacement_cc": 2993,
                "power_hp": 286,
                "power_kw": 210,
            },
            {
                "brand": "mercedes-benz",
                "model": "C-Class",
                "generation": "W205",
                "variant": "C220d",
                "year_start": 2014,
                "year_end": 2021,
                "engine_code": "OM654",
                "fuel_type": Vehicle.FuelType.DIESEL,
                "displacement_cc": 1950,
                "power_hp": 194,
                "power_kw": 143,
            },
            {
                "brand": "mercedes-benz",
                "model": "E-Class",
                "generation": "W213",
                "variant": "E220d",
                "year_start": 2016,
                "year_end": 2023,
                "engine_code": "OM654",
                "fuel_type": Vehicle.FuelType.DIESEL,
                "displacement_cc": 1950,
                "power_hp": 194,
                "power_kw": 143,
            },
            {
                "brand": "mercedes-benz",
                "model": "S-Class",
                "generation": "W222",
                "variant": "S350d",
                "year_start": 2013,
                "year_end": 2020,
                "engine_code": "OM656",
                "fuel_type": Vehicle.FuelType.DIESEL,
                "displacement_cc": 2925,
                "power_hp": 286,
                "power_kw": 210,
            },
            {
                "brand": "audi",
                "model": "A4",
                "generation": "B9",
                "variant": "40 TDI",
                "year_start": 2015,
                "year_end": 2019,
                "engine_code": "CKMC",
                "fuel_type": Vehicle.FuelType.DIESEL,
                "displacement_cc": 1968,
                "power_hp": 190,
                "power_kw": 140,
            },
            {
                "brand": "audi",
                "model": "A6",
                "generation": "C7",
                "variant": "50 TDI",
                "year_start": 2014,
                "year_end": 2018,
                "engine_code": "CRTC",
                "fuel_type": Vehicle.FuelType.DIESEL,
                "displacement_cc": 2967,
                "power_hp": 272,
                "power_kw": 200,
            },
            {
                "brand": "audi",
                "model": "Q5",
                "generation": "FY",
                "variant": "40 TDI",
                "year_start": 2016,
                "year_end": 2020,
                "engine_code": "DETC",
                "fuel_type": Vehicle.FuelType.DIESEL,
                "displacement_cc": 1968,
                "power_hp": 190,
                "power_kw": 140,
            },
            {
                "brand": "volkswagen",
                "model": "Golf",
                "generation": "VII",
                "variant": "GTD",
                "year_start": 2013,
                "year_end": 2020,
                "engine_code": "CKFC",
                "fuel_type": Vehicle.FuelType.DIESEL,
                "displacement_cc": 1968,
                "power_hp": 184,
                "power_kw": 135,
            },
            {
                "brand": "volkswagen",
                "model": "Passat",
                "generation": "B8",
                "variant": "2.0 TDI",
                "year_start": 2014,
                "year_end": 2019,
                "engine_code": "DFCC",
                "fuel_type": Vehicle.FuelType.DIESEL,
                "displacement_cc": 1968,
                "power_hp": 190,
                "power_kw": 140,
            },
            {
                "brand": "ford",
                "model": "Focus",
                "generation": "IV",
                "variant": "EcoBlue",
                "year_start": 2018,
                "year_end": 2023,
                "engine_code": "YG",
                "fuel_type": Vehicle.FuelType.DIESEL,
                "displacement_cc": 1995,
                "power_hp": 120,
                "power_kw": 88,
            },
            {
                "brand": "ford",
                "model": "Transit",
                "generation": "Custom",
                "variant": "2.0 TDCi",
                "year_start": 2012,
                "year_end": 2023,
                "engine_code": "T9",
                "fuel_type": Vehicle.FuelType.DIESEL,
                "displacement_cc": 1995,
                "power_hp": 130,
                "power_kw": 96,
            },
            {
                "brand": "toyota",
                "model": "Corolla",
                "generation": "E210",
                "variant": "1.8 Hybrid",
                "year_start": 2018,
                "year_end": 2023,
                "engine_code": "2ZR-FXE",
                "fuel_type": Vehicle.FuelType.HYBRID,
                "displacement_cc": 1798,
                "power_hp": 122,
                "power_kw": 90,
            },
            {
                "brand": "toyota",
                "model": "RAV4",
                "generation": "XA50",
                "variant": "2.5 Hybrid",
                "year_start": 2018,
                "year_end": 2023,
                "engine_code": "A25A-FXS",
                "fuel_type": Vehicle.FuelType.HYBRID,
                "displacement_cc": 2487,
                "power_hp": 222,
                "power_kw": 163,
            },
            {
                "brand": "renault",
                "model": "Clio",
                "generation": "V",
                "variant": "dCi 90",
                "year_start": 2019,
                "year_end": 2023,
                "engine_code": "H5Dt",
                "fuel_type": Vehicle.FuelType.DIESEL,
                "displacement_cc": 1461,
                "power_hp": 90,
                "power_kw": 66,
            },
            {
                "brand": "renault",
                "model": "Megane",
                "generation": "IV",
                "variant": "dCi 110",
                "year_start": 2015,
                "year_end": 2023,
                "engine_code": "R9N",
                "fuel_type": Vehicle.FuelType.DIESEL,
                "displacement_cc": 1461,
                "power_hp": 110,
                "power_kw": 81,
            },
            {
                "brand": "fiat",
                "model": "500",
                "generation": "312",
                "variant": "1.3 Multijet",
                "year_start": 2007,
                "year_end": 2023,
                "engine_code": "169A1",
                "fuel_type": Vehicle.FuelType.DIESEL,
                "displacement_cc": 1248,
                "power_hp": 75,
                "power_kw": 55,
            },
        ]

        vehicles = {}
        for data in vehicles_data:
            brand = brands[data.pop("brand")]
            key = f"{brand.slug}-{data['model']}-{data['generation']}-{data['variant']}"

            obj, created = Vehicle.objects.get_or_create(
                brand=brand,
                model=data["model"],
                generation=data["generation"],
                variant=data["variant"],
                defaults={
                    "vehicle_type": Vehicle.VehicleType.CAR,
                    "year_start": data.get("year_start"),
                    "year_end": data.get("year_end"),
                    "engine_code": data.get("engine_code", ""),
                    "fuel_type": data.get("fuel_type", ""),
                    "displacement_cc": data.get("displacement_cc"),
                    "power_hp": data.get("power_hp"),
                    "power_kw": data.get("power_kw"),
                    "is_active": True,
                },
            )
            vehicles[key] = obj
            if created:
                self.stdout.write(f"  Created vehicle: {obj}")

        return vehicles

    def _create_products(
        self,
        supplier: Supplier,
        conditions: dict,
        categories: dict,
        brands: dict,
        vehicles: dict,
    ) -> None:
        part_number_types = self._get_part_number_types()
        products_data = [
            {
                "sku": "RG-ANL-DEN-001",
                "supplier_code": "TE438000-4913",
                "title": "Starter Denso (New - Take off) TE438000-4913",
                "short_description": "Starter motor for BMW vehicles, 12V",
                "brand": "denso",
                "category": "starter",
                "condition": "take_off",
                "price": Decimal("166.60"),
                "weight": Decimal("3.500"),
                "part_numbers": [
                    {"number": "TE438000-4913", "type": "oe"},
                    {"number": "8687064", "type": "oem"},
                    {"number": "12418687064", "type": "oem"},
                    {"number": "438000-4913", "type": "equivalent"},
                ],
                "fitments": [
                    ("bmw-3 Series-G20-320d", "BMW 7 (G11, G12), Year 2021-"),
                ],
            },
            {
                "sku": "RG-ANL-BOS-001",
                "supplier_code": "0001107528",
                "title": "Starter Bosch (Rebuilt) 0001107528",
                "short_description": "Refurbished starter motor",
                "brand": "bosch",
                "category": "starter",
                "condition": "refurbished",
                "price": Decimal("98.00"),
                "weight": Decimal("4.200"),
                "part_numbers": [
                    {"number": "0001107528", "type": "oe"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-ANL-SEG-001",
                "supplier_code": "0001148515",
                "title": "Starter SEG (New - Take off) 0001148515",
                "short_description": "Starter motor SEG brand",
                "brand": "seg",
                "category": "starter",
                "condition": "take_off",
                "price": Decimal("112.00"),
                "weight": Decimal("3.800"),
                "part_numbers": [
                    {"number": "0001148515", "type": "oe"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-ANL-SEG-002",
                "supplier_code": "0001200004",
                "title": "Starter SEG (New - Take off) 0001200004",
                "short_description": "Heavy duty starter motor",
                "brand": "seg",
                "category": "starter",
                "condition": "take_off",
                "price": Decimal("220.15"),
                "weight": Decimal("5.500"),
                "part_numbers": [
                    {"number": "0001200004", "type": "oe"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-ANL-VAL-001",
                "supplier_code": "RSM18",
                "title": "Starter Valeo (New) 12V RSM18",
                "short_description": "New Valeo starter motor 12V",
                "brand": "valeo",
                "category": "starter",
                "condition": "new",
                "price": Decimal("285.60"),
                "weight": Decimal("4.000"),
                "part_numbers": [
                    {"number": "RSM18", "type": "internal"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-LIC-JAK-001",
                "supplier_code": "J5113053",
                "title": "Alternator Jakoparts (New) 100A/14V J5113053",
                "short_description": "Alternator 100A 14V",
                "brand": "ac-edge",
                "category": "alternators",
                "condition": "new",
                "price": Decimal("95.20"),
                "weight": Decimal("5.200"),
                "part_numbers": [
                    {"number": "J5113053", "type": "internal"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-LIC-DEN-001",
                "supplier_code": "104211-8183",
                "title": "Alternator Denso (New) 14V 150A, 104211-8183",
                "short_description": "High power alternator 150A made in Japan",
                "brand": "denso",
                "category": "alternators",
                "condition": "new",
                "price": Decimal("273.70"),
                "weight": Decimal("6.500"),
                "part_numbers": [
                    {"number": "104211-8183", "type": "oe"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-LIC-VAL-001",
                "supplier_code": "TG12C065",
                "title": "Alternator Valeo (Short running) 140A, TG12C065",
                "short_description": "Alternator 140A short-run",
                "brand": "valeo",
                "category": "alternators",
                "condition": "take_off",
                "price": Decimal("130.90"),
                "weight": Decimal("6.000"),
                "part_numbers": [
                    {"number": "TG12C065", "type": "oe"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-LIC-BOS-001",
                "supplier_code": "0124325064",
                "title": "Alternator Bosch (New) 14V/ 90A, 0124325064",
                "short_description": "Bosch alternator 90A",
                "brand": "bosch",
                "category": "alternators",
                "condition": "new",
                "price": Decimal("261.80"),
                "weight": Decimal("5.800"),
                "part_numbers": [
                    {"number": "0124325064", "type": "oe"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-TUR-MAH-001",
                "supplier_code": "001TC14455000",
                "title": "Turbocharger MAHLE (New) 001TC14455000",
                "short_description": "Turbocharger MAHLE new",
                "brand": "mahle",
                "category": "turbocharger",
                "condition": "new",
                "price": Decimal("329.90"),
                "weight": Decimal("4.500"),
                "part_numbers": [
                    {"number": "001TC14455000", "type": "internal"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-TUR-GAR-001",
                "supplier_code": "836847-5",
                "title": "Turbocharger Garrett (New) 836847-5",
                "short_description": "Garrett turbocharger new",
                "brand": "garrett",
                "category": "turbocharger",
                "condition": "new",
                "price": Decimal("690.20"),
                "weight": Decimal("5.200"),
                "part_numbers": [
                    {"number": "836847-5", "type": "internal"},
                    {"number": "8368475002", "type": "equivalent"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-TUR-KKK-001",
                "supplier_code": "BV39B-0059",
                "title": "Turbocharger KKK (Exchange) BV39B-0059",
                "short_description": "KKK turbo exchange unit",
                "brand": "kkk",
                "category": "turbocharger",
                "condition": "exchange",
                "price": Decimal("359.99"),
                "weight": Decimal("4.800"),
                "part_numbers": [
                    {"number": "BV39B-0059", "type": "internal"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-TUR-GAR-002",
                "supplier_code": "700830-1-I",
                "title": "Turbocharger Garrett (Rebuilt) 700830-1-I",
                "short_description": "Garrett rebuilt turbo",
                "brand": "garrett",
                "category": "turbocharger",
                "condition": "refurbished",
                "price": Decimal("333.33"),
                "weight": Decimal("5.000"),
                "part_numbers": [
                    {"number": "700830-1-I", "type": "internal"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-TUR-HOL-001",
                "supplier_code": "4041791",
                "title": "Turbocharger Holset (New) 4041791",
                "short_description": "Holset turbocharger new",
                "brand": "holset",
                "category": "turbocharger",
                "condition": "new",
                "price": Decimal("559.90"),
                "weight": Decimal("6.500"),
                "part_numbers": [
                    {"number": "4041791", "type": "internal"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-TUR-MHI-001",
                "supplier_code": "49377-07080",
                "title": "Turbocharger MHI (New) 49377-07080",
                "short_description": "Mitsubishi Heavy Industries turbo",
                "brand": "mhi",
                "category": "turbocharger",
                "condition": "new",
                "price": Decimal("479.99"),
                "weight": Decimal("5.200"),
                "part_numbers": [
                    {"number": "49377-07080", "type": "internal"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-KLI-DEN-001",
                "supplier_code": "042400-3261",
                "title": "AC Compressor Denso ESBA34C (New) 042400-3261",
                "short_description": "A/C compressor Denso ESBA34C",
                "brand": "denso",
                "category": "air-conditioning-compressors",
                "condition": "new",
                "price": Decimal("571.20"),
                "weight": Decimal("5.000"),
                "part_numbers": [
                    {"number": "042400-3261", "type": "oe"},
                    {"number": "ESBA34C", "type": "internal"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-KLI-DEN-002",
                "supplier_code": "447150-8610",
                "title": "AC Compressor Denso (New) 447150-8610",
                "short_description": "Denso A/C compressor new",
                "brand": "denso",
                "category": "air-conditioning-compressors",
                "condition": "new",
                "price": Decimal("399.99"),
                "weight": Decimal("4.800"),
                "part_numbers": [
                    {"number": "447150-8610", "type": "oe"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-KLI-SAN-001",
                "supplier_code": "TRSE09-3773AE",
                "title": "AC Compressor Sanden (New) TRSE09-3773AE",
                "short_description": "Sanden A/C compressor",
                "brand": "sanden",
                "category": "air-conditioning-compressors",
                "condition": "new",
                "price": Decimal("258.50"),
                "weight": Decimal("4.200"),
                "part_numbers": [
                    {"number": "TRSE09-3773AE", "type": "internal"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-KLI-SAN-002",
                "supplier_code": "PXC14-1749",
                "title": "AC Compressor Sanden (New) PXC14-1749",
                "short_description": "Sanden PXC14 A/C compressor made in Poland",
                "brand": "sanden",
                "category": "air-conditioning-compressors",
                "condition": "new",
                "price": Decimal("369.99"),
                "weight": Decimal("4.500"),
                "part_numbers": [
                    {"number": "PXC14-1749", "type": "internal"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-KLI-ACE-001",
                "supplier_code": "ACE05017",
                "title": "AC Compressor AC Edge (New) ACE05017",
                "short_description": "AC Edge A/C compressor",
                "brand": "ac-edge",
                "category": "air-conditioning-compressors",
                "condition": "new",
                "price": Decimal("256.33"),
                "weight": Decimal("4.000"),
                "part_numbers": [
                    {"number": "ACE05017", "type": "internal"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-KON-VAL-001",
                "supplier_code": "TD297",
                "title": "AC Evaporator Valeo (New - Take off) TD297",
                "short_description": "A/C evaporator Valeo",
                "brand": "valeo",
                "category": "air-conditioning-compressors",
                "condition": "take_off",
                "price": Decimal("35.70"),
                "weight": Decimal("3.500"),
                "part_numbers": [
                    {"number": "TD297", "type": "internal"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-SEN-BOS-001",
                "supplier_code": "0280218067",
                "title": "Air Flow Meter Bosch (New) 0280218067",
                "short_description": "Air mass meter Bosch",
                "brand": "bosch",
                "category": "air-flow-meter",
                "condition": "new",
                "price": Decimal("125.00"),
                "weight": Decimal("0.350"),
                "part_numbers": [
                    {"number": "0280218067", "type": "oe"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-SEN-DEN-001",
                "supplier_code": "195500-0631",
                "title": "Lambda Sensor Denso (New) 195500-0631",
                "short_description": "Lambda sensor Denso",
                "brand": "denso",
                "category": "sensors-lambda-sensors",
                "condition": "new",
                "price": Decimal("89.50"),
                "weight": Decimal("0.250"),
                "part_numbers": [
                    {"number": "195500-0631", "type": "oe"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-ZUN-BOS-001",
                "supplier_code": "0221504470",
                "title": "Ignition Coil Bosch (New) 0221504470",
                "short_description": "Ignition coil Bosch",
                "brand": "bosch",
                "category": "ignition-coils",
                "condition": "new",
                "price": Decimal("45.00"),
                "weight": Decimal("0.350"),
                "part_numbers": [
                    {"number": "0221504470", "type": "oe"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-KER-NGK-001",
                "supplier_code": "ILZKBR7B8DG",
                "title": "Spark Plug NGK (New) ILZKBR7B8DG",
                "short_description": "Spark plug NGK iridium",
                "brand": "ngk",
                "category": "spark-plugs",
                "condition": "new",
                "price": Decimal("12.50"),
                "weight": Decimal("0.050"),
                "part_numbers": [
                    {"number": "ILZKBR7B8DG", "type": "internal"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-LEN-VAL-001",
                "supplier_code": "2518242",
                "title": "Servo Pump Valeo (Rebuilt) 2518242",
                "short_description": "Power steering pump Valeo rebuilt",
                "brand": "valeo",
                "category": "steering-servo-pumps",
                "condition": "refurbished",
                "price": Decimal("175.00"),
                "weight": Decimal("4.500"),
                "part_numbers": [
                    {"number": "2518242", "type": "oe"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-GET-ZF-001",
                "supplier_code": "6HP28",
                "title": "Transmission ZF (Used) 6HP28",
                "short_description": "Automatic transmission ZF 6HP28 used",
                "brand": "zf",
                "category": "transmission",
                "condition": "used",
                "price": Decimal("1850.00"),
                "weight": Decimal("85.000"),
                "part_numbers": [
                    {"number": "6HP28", "type": "internal"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-KUP-LUK-001",
                "supplier_code": "621309809",
                "title": "Clutch Kit Luk (New) 621309809",
                "short_description": "Clutch kit Luk",
                "brand": "luk",
                "category": "flywheels-clutches",
                "condition": "new",
                "price": Decimal("285.00"),
                "weight": Decimal("8.500"),
                "part_numbers": [
                    {"number": "621309809", "type": "oe"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-SWS-SAC-001",
                "supplier_code": "334367",
                "title": "Shock Absorber Sachs (New) 334367",
                "short_description": "Shock absorber Sachs",
                "brand": "sachs",
                "category": "shock-absorbers-springs-axles",
                "condition": "new",
                "price": Decimal("85.00"),
                "weight": Decimal("3.200"),
                "part_numbers": [
                    {"number": "334367", "type": "oe"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-RAL-SKF-001",
                "supplier_code": "VKBA3648",
                "title": "Wheel Bearing SKF (New) VKBA3648",
                "short_description": "Wheel bearing SKF",
                "brand": "skf",
                "category": "wheel-bearings",
                "condition": "new",
                "price": Decimal("45.00"),
                "weight": Decimal("1.200"),
                "part_numbers": [
                    {"number": "VKBA3648", "type": "internal"},
                ],
                "fitments": [],
            },
            {
                "sku": "RG-THER-VER-001",
                "supplier_code": "3521215",
                "title": "Thermostat Vernet (New) 3521215",
                "short_description": "Thermostat Vernet with housing",
                "brand": "vernet",
                "category": "thermostat",
                "condition": "new",
                "price": Decimal("32.00"),
                "weight": Decimal("0.450"),
                "part_numbers": [
                    {"number": "3521215", "type": "oe"},
                ],
                "fitments": [],
            },
        ]

        for data in products_data:
            brand = brands.get(data["brand"])
            category = categories.get(data["category"])
            condition = conditions.get(data["condition"])

            product, created = Product.objects.get_or_create(
                sku=data["sku"],
                defaults={
                    "supplier": supplier,
                    "supplier_product_code": data.get("supplier_code"),
                    "title": data["title"],
                    "short_description": data.get("short_description", ""),
                    "brand": brand,
                    "category": category,
                    "condition": condition,
                    "publication_status": Product.PublicationStatus.PUBLISHED,
                    "published_at": datetime.now(timezone.utc),
                    "price_visibility_mode": Product.PriceVisibilityMode.VISIBLE_INFO,
                    "last_known_price": data.get("price"),
                    "currency": "EUR",
                    "unit_of_sale": "unit",
                    "weight": data.get("weight"),
                    "is_active": True,
                },
            )

            if created:
                self.stdout.write(f"  Created product: {product.title}")

                for pn_data in data.get("part_numbers", []):
                    mapped_type_code = self._map_sample_part_number_type(pn_data.get("type", ""))
                    part_type = part_number_types[mapped_type_code]
                    PartNumber.objects.create(
                        product=product,
                        brand=brand,
                        number_raw=pn_data["number"],
                        part_number_type=part_type,
                        is_primary=(mapped_type_code == "OES"),
                    )

                for fitment_key, notes in data.get("fitments", []):
                    vehicle = vehicles.get(fitment_key)
                    if vehicle:
                        ProductVehicleFitment.objects.create(
                            product=product,
                            vehicle=vehicle,
                            fitment_notes=notes,
                            source=ProductVehicleFitment.FitmentSource.IMPORT,
                            is_verified=False,
                        )
            else:
                self.stdout.write(f"  Product already exists: {data['sku']}")
