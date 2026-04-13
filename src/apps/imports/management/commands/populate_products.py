"""
Populate database with realistic test products.
"""
import random
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.catalog.models import (
    Brand,
    Category,
    Condition,
    PartNumber,
    PartNumberType,
    Product,
    ProductImage,
)
from apps.suppliers.models import Supplier
from apps.vehicles.models import ProductVehicleFitment, Vehicle


class Command(BaseCommand):
    help = "Populate database with realistic test products"

    PRODUCT_TEMPLATES = [
        # Category: Air Conditioning Compressors
        {
            "category": "Air Conditioning Compressors",
            "type": "AC Compressor",
            "templates": [
                "{brand} AC Compressor {series}",
                "Air Conditioning Compressor {brand} {model}",
            ],
            "oe_patterns": ["{brand}{year}{code}", "{brand} {year}"],
        },
        # Category: Air Flow Meters
        {
            "category": "Air Flow Meters",
            "type": "Air Flow Meter",
            "templates": [
                "Mass Air Flow Sensor {brand} {series}",
                "Air Flow Meter {brand} {model}",
            ],
            "oe_patterns": ["{brand}{code}", "MAF {brand}{code}"],
        },
        # Category: Alternators
        {
            "category": "Alternators",
            "type": "Alternator",
            "templates": [
                "Alternator {brand} {amp}A {series}",
                "{brand} Alternator Unit {model}",
            ],
            "oe_patterns": ["ALT {brand}{code}", "{brand} {code}ALT"],
        },
        # Category: Brake Parts
        {
            "category": "Brake Parts",
            "type": "Brake Component",
            "templates": [
                "Brake Caliper {brand} {position}",
                "Brake Disc {brand} {series} {size}",
                "Brake Pad Set {brand} {series}",
            ],
            "oe_patterns": ["{brand}{code}", "BRK{brand}{year}"],
        },
        # Category: Ignition Coils
        {
            "category": "Ignition Coils",
            "type": "Ignition Coil",
            "templates": [
                "Ignition Coil {brand} {series}",
                "Coil Pack {brand} {cylinders}-Cylinder",
            ],
            "oe_patterns": ["IC{brand}{code}", "{brand}{code}IC"],
        },
        # Category: Injectors
        {
            "category": "Injectors",
            "type": "Fuel Injector",
            "templates": [
                "Fuel Injector {brand} {flow}cc",
                "Injecteur {brand} {series}",
            ],
            "oe_patterns": ["INJ{brand}{code}", "{brand}{code}INJ"],
        },
        # Category: Sensors
        {
            "category": "Sensors",
            "type": "Sensor",
            "templates": [
                "{sensor_type} Sensor {brand} {series}",
                "{brand} {sensor_type} Sensor",
            ],
            "oe_patterns": ["SEN{brand}{code}", "{brand}{code}SEN"],
        },
        # Category: Spark Plugs
        {
            "category": "Spark Plugs",
            "type": "Spark Plug",
            "templates": [
                "Spark Plug {brand} {series}",
                "Iridium Spark Plug {brand} {heat}",
            ],
            "oe_patterns": ["SP{brand}{code}", "{brand}SP{code}"],
        },
        # Category: Starter
        {
            "category": "Starter",
            "type": "Starter Motor",
            "templates": [
                "Starter Motor {brand} {power}KW",
                "{brand} Starter {series}",
            ],
            "oe_patterns": ["ST{brand}{code}", "{brand}ST{code}"],
        },
        # Category: Turbochargers
        {
            "category": "Turbochargers",
            "type": "Turbocharger",
            "templates": [
                "Turbocharger {brand} {series}",
                "{brand} Turbo {power}KW",
            ],
            "oe_patterns": ["TB{brand}{code}", "{brand}TB{code}"],
        },
        # Category: Thermostats
        {
            "category": "Thermostats",
            "type": "Thermostat",
            "templates": [
                "Thermostat {brand} {temp}°C",
                "{brand} Engine Thermostat {series}",
            ],
            "oe_patterns": ["TH{brand}{code}", "{brand}TH{code}"],
        },
        # Category: Shock Absorbers
        {
            "category": "Shock Absorbers / Springs / Axles",
            "type": "Shock Absorber",
            "templates": [
                "Shock Absorber {brand} {position}",
                "{brand} Damper {series} {type}",
            ],
            "oe_patterns": ["SA{brand}{code}", "{brand}SA{code}"],
        },
        # Category: Wheels
        {
            "category": "Wheels",
            "type": "Wheel Rim",
            "templates": [
                "Alloy Wheel {brand} {size}\" {finish}",
                "{brand} Rim {series} {specs}",
            ],
            "oe_patterns": ["WH{brand}{code}", "{brand}WH{code}"],
        },
        # Category: Steering
        {
            "category": "Steering",
            "type": "Steering Component",
            "templates": [
                "Power Steering Pump {brand} {series}",
                "Steering Rack {brand} {type}",
            ],
            "oe_patterns": ["ST{brand}{code}", "{brand}ST{code}"],
        },
        # Category: Wheel Bearings
        {
            "category": "Wheel Bearings",
            "type": "Wheel Bearing",
            "templates": [
                "Wheel Bearing {brand} {size}",
                "{brand} Hub Bearing {series}",
            ],
            "oe_patterns": ["WB{brand}{code}", "{brand}WB{code}"],
        },
    ]

    SENSOR_TYPES = [
        "Coolant Temperature", "Intake Air Temperature", "Mass Air Flow",
        "Crankshaft Position", "Camshaft Position", "Oxygen", "Knock",
        "Throttle Position", "Vehicle Speed", "ABS", "Oil Pressure",
        "Fuel Level", "Manifold Absolute Pressure", "Parking Brake",
    ]

    BRAND_CODES = {
        "Volkswagen": ["VW", "VWK"],
        "Audi": ["AUDI", "AUD"],
        "BMW": ["BMW", "BMWM"],
        "Mercedes-Benz": ["MB", "MERC"],
        "Ford": ["FORD", "FD"],
        "Opel": ["OPEL", "OP"],
        "Renault": ["REN", "RNLT"],
        "Peugeot": ["PEU", "PGT"],
        "Citroen": ["CIT", "CTRN"],
        "Fiat": ["FIAT", "FT"],
        "Alfa Romeo": ["AR", "ALF"],
        "Lancia": ["LAN", "LNC"],
        "Seat": ["SEA", "ST"],
        "Skoda": ["SKD", "SKO"],
        "Toyota": ["TYT", "TOY"],
        "Honda": ["HON", "HDA"],
        "Nissan": ["NIS", "NSS"],
        "Mazda": ["MZ", "MZD"],
        "Hyundai": ["HYU", "HYND"],
        "Kia": ["KIA", "KIA"],
        "Volvo": ["VOL", "VLV"],
        "Porsche": ["POR", "PCH"],
    }

    VEHICLE_SERIES = {
        "Volkswagen": ["Golf", "Polo", "Passat", "Jetta", "Tiguan", "Touareg", "Up", "Fox", "Scirocco", "Beetle"],
        "Audi": ["A1", "A3", "A4", "A5", "A6", "Q3", "Q5", "Q7", "TT", "R8"],
        "BMW": ["Serie 1", "Serie 3", "Serie 5", "X1", "X3", "X5", "Z4", "M3"],
        "Mercedes-Benz": ["Clase A", "Clase C", "Clase E", "Clase S", "GLA", "GLC", "GLE", "ML"],
        "Ford": ["Fiesta", "Focus", "Mondeo", "Kuga", "Transit", "Mustang", "Puma", "EcoSport"],
        "Opel": ["Corsa", "Astra", "Insignia", "Mokka", "Crossland", "Grandland"],
        "Renault": ["Clio", "Megane", "Captur", "Kadjar", "Scenic", "Twingo", "Koleos"],
        "Peugeot": ["208", "308", "3008", "5008", "2008", "Partner", "Expert"],
        "Citroen": ["C3", "C4", "C5", "Berlingo", "DS3", "DS4", "C-Elysee"],
        "Fiat": ["500", "Panda", "Punto", "Tipo", "500X", "500L", "Ducato"],
        "Alfa Romeo": ["Giulia", "Stelvio", "Giulietta", "Mito", "Giulia Quadrifoglio"],
        "Seat": ["Ibiza", "Leon", "Ateca", "Arona", "Tarraco", "Alhambra"],
        "Skoda": ["Octavia", "Fabia", "Superb", "Kodiaq", "Karoq", "Scala"],
        "Toyota": ["Yaris", "Corolla", "Camry", "RAV4", "C-HR", "Land Cruiser", "Prius"],
        "Honda": ["Civic", "CR-V", "HR-V", "Jazz", "Accord", "City"],
        "Hyundai": ["i20", "i30", "Tucson", "Santa Fe", "Kona", "i10"],
        "Kia": ["Sportage", "Ceed", "Rio", "Picanto", "Sorento", "Niro"],
    }

    YEARS = list(range(2000, 2026))
    FLOW_RATES = ["150", "180", "200", "220", "250", "280", "300", "350", "400", "500", "600", "750", "1000", "1200", "1500"]
    POWER_KW = ["1.4", "2.0", "2.2", "2.5", "3.0", "3.5", "4.0", "5.0", "6.0", "7.0", "8.0"]
    TEMPS = ["80", "85", "88", "90", "92", "95"]
    HEAT_RANGES = ["Cold", "Medium", "Hot", "Super Hot"]
    POSITIONS = ["Front Left", "Front Right", "Rear Left", "Rear Right"]
    TIRE_SIZES = ["15", "16", "17", "18", "19", "20", "21"]
    FINISHES = ["Silver", "Gloss Black", "Matte Black", "Gunmetal", "Chrome", "Bronze"]

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=200,
            help="Number of products to create (default: 200)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing products before creating new ones",
        )

    def handle(self, *args, **options):
        count = options["count"]
        clear = options["clear"]

        self.stdout.write(f"Creating {count} products...")

        if clear:
            self.stdout.write("Clearing existing products...")
            with transaction.atomic():
                ProductVehicleFitment.objects.all().delete()
                ProductImage.objects.all().delete()
                PartNumber.objects.all().delete()
                Product.objects.all().delete()
                Vehicle.objects.all().delete()
                Brand.objects.filter(brand_type=Brand.BrandType.VEHICLE).delete()

        with transaction.atomic():
            created = self._create_products(count)

        self.stdout.write(self.style.SUCCESS("\nImport complete!"))
        self.stdout.write(f"  Products: {created['products']}")
        self.stdout.write(f"  Part Numbers: {created['part_numbers']}")
        self.stdout.write(f"  Vehicles: {created['vehicles']}")
        self.stdout.write(f"  Fitments: {created['fitments']}")
        self.stdout.write(f"  Images: {created['images']}")

    def _create_products(self, count: int) -> dict:
        created = {
            "products": 0,
            "part_numbers": 0,
            "vehicles": 0,
            "fitments": 0,
            "images": 0,
        }

        supplier = Supplier.objects.first()
        if not supplier:
            self.stderr.write(self.style.ERROR("No supplier found. Please run populate_rg_data first."))
            return created

        condition = Condition.objects.filter(code="NEW").first()
        part_types = {
            "OEM": PartNumberType.objects.filter(code="OEM").first(),
            "OES": PartNumberType.objects.filter(code="OES").first(),
            "AIM": PartNumberType.objects.filter(code="AIM").first(),
        }

        categories = list(Category.objects.all())
        brands = list(Brand.objects.filter(brand_type=Brand.BrandType.PARTS))
        vehicle_brands = list(Brand.objects.filter(brand_type=Brand.BrandType.VEHICLE))

        if not vehicle_brands:
            vehicle_brands = self._create_vehicle_brands()
            created["vehicles"] += len(vehicle_brands)

        vehicles = self._get_or_create_vehicles(vehicle_brands)
        created["vehicles"] = len(vehicles)

        template_pool = []
        for template in self.PRODUCT_TEMPLATES:
            template_pool.extend([template] * 3)

        for i in range(count):
            product = self._create_product(
                supplier, condition, part_types, categories, brands,
                vehicles, template_pool[i % len(template_pool)], i + 1
            )
            created["products"] += 1

            pn_count = random.randint(2, 6)
            for _ in range(pn_count):
                self._create_part_number(product, brands, part_types)
                created["part_numbers"] += 1

            fitment_count = random.randint(3, 12)
            fitment_vehicles = random.sample(vehicles, min(fitment_count, len(vehicles)))
            for vehicle in fitment_vehicles:
                ProductVehicleFitment.objects.get_or_create(
                    product=product,
                    vehicle=vehicle,
                    defaults={"source": ProductVehicleFitment.FitmentSource.SUPPLIER}
                )
                created["fitments"] += 1

            if i % 20 == 0:
                img_created = self._create_product_image(product)
                if img_created:
                    created["images"] += 1

            if (i + 1) % 50 == 0:
                self.stdout.write(f"  Created {i + 1}/{count} products...")

        return created

    def _create_vehicle_brands(self) -> list:
        vehicle_brand_names = list(self.VEHICLE_SERIES.keys())
        brands = []
        for name in vehicle_brand_names:
            brand, _ = Brand.objects.get_or_create(
                slug=slugify(name),
                defaults={"name": name, "brand_type": Brand.BrandType.VEHICLE}
            )
            brands.append(brand)
        return brands

    def _get_or_create_vehicles(self, vehicle_brands: list) -> list:
        vehicles = []
        for brand in vehicle_brands:
            brand_name = brand.name
            if brand_name not in self.VEHICLE_SERIES:
                continue

            models = self.VEHICLE_SERIES[brand_name]
            vehicle_count = random.randint(2, min(6, len(models)))

            for _ in range(vehicle_count):
                model = random.choice(models)
                year_from = random.choice(self.YEARS)
                year_to = random.choice([y for y in self.YEARS if y >= year_from])

                vehicle, created = Vehicle.objects.get_or_create(
                    brand=brand,
                    model=model,
                    defaults={
                        "year_start": year_from,
                        "year_end": year_to,
                        "vehicle_type": Vehicle.VehicleType.CAR,
                    }
                )
                if vehicle not in vehicles:
                    vehicles.append(vehicle)

        return vehicles

    def _create_product(
        self, supplier, condition, part_types, categories, brands, vehicles, template, counter
    ):
        brand = random.choice(brands)
        category = random.choice(categories)
        supplier_code = supplier.code.replace("-", "")
        sku = f"{supplier_code}{counter:06d}"
        supplier_product_code = f"{counter:06d}"

        title = self._generate_title(template, brand.name)
        short_desc = self._generate_short_description(template["type"])

        product = Product.objects.create(
            supplier=supplier,
            supplier_product_code=supplier_product_code,
            sku=sku,
            title=title,
            short_description=short_desc,
            brand=brand,
            category=category,
            condition=condition,
            publication_status=Product.PublicationStatus.PUBLISHED,
            published_at=timezone.now(),
            price_visibility_mode=Product.PriceVisibilityMode.VISIBLE_INFO,
            last_known_price=Decimal(str(random.randint(50, 2000))),
            currency="EUR",
            unit_of_sale="unit",
            weight=Decimal(str(round(random.uniform(0.5, 25.0), 2))),
            featured=random.random() < 0.1,
            is_active=True,
        )

        return product

    def _generate_title(self, template: dict, brand: str) -> str:
        title_template = random.choice(template["templates"])

        title = title_template.replace("{brand}", brand)
        title = title.replace("{series}", f"{random.randint(1, 9)}{random.choice(['A', 'B', 'C', 'S', 'X'])}")
        title = title.replace("{model}", f"{random.randint(1, 6)}{random.choice(['.0', '.5', 'S', 'T'])}")
        title = title.replace("{amp}A", f"{random.choice([90, 110, 120, 140, 150])}A")
        title = title.replace("{power}KW", f"{random.choice([1.4, 1.8, 2.0, 2.2, 3.0])}KW")
        title = title.replace("{flow}cc", f"{random.choice(self.FLOW_RATES)}cc")
        title = title.replace("{cylinders}", str(random.choice([4, 5, 6, 8])))
        title = title.replace("{temp}°C", f"{random.choice(self.TEMPS)}°C")
        title = title.replace("{heat}", random.choice(self.HEAT_RANGES))
        title = title.replace("{position}", random.choice(self.POSITIONS))
        title = title.replace("{size}\"", f"{random.choice(self.TIRE_SIZES)}\"")
        title = title.replace("{size}", random.choice(["25x52x25", "30x62x20", "35x72x25", "40x80x30"]))
        title = title.replace("{finish}", random.choice(self.FINISHES))
        title = title.replace("{specs}", f"{random.choice([5, 6, 8])}x{random.choice([100, 112, 114, 120])}")

        if "{sensor_type}" in title:
            title = title.replace("{sensor_type}", random.choice(self.SENSOR_TYPES))

        return title

    def _generate_short_description(self, product_type: str) -> str:
        descriptions = [
            f"High quality {product_type.lower()} for European vehicles. OEM equivalent.",
            f"Professional grade {product_type.lower()}. Exact fit guarantee.",
            f"{product_type} with excellent performance and durability.",
            f"Original equipment quality {product_type.lower()} for optimal engine operation.",
            f"Premium {product_type.lower()} meeting or exceeding OEM specifications.",
        ]
        return random.choice(descriptions)

    def _create_part_number(self, product, brands, part_types):
        brand = random.choice(brands)
        part_type = random.choice(list(part_types.values()))

        code = f"{random.randint(1000, 9999)}{random.choice(['A', 'B', 'C', ''])}"
        number_raw = f"{brand.name[:4].upper()}{code}"

        existing_primary = PartNumber.objects.filter(
            product=product, is_primary=True
        ).exists()

        PartNumber.objects.create(
            product=product,
            brand=brand,
            number_raw=number_raw,
            part_number_type=part_type,
            is_primary=not existing_primary and random.random() < 0.3,
        )

    def _create_product_image(self, product) -> bool:
        svg_content = self._generate_placeholder_svg(product)
        try:
            image = ProductImage.objects.create(
                product=product,
                alt_text=product.title,
                sort_order=0,
                is_primary=True,
            )
            image.image.save(
                f"product_{product.id}.svg",
                ContentFile(svg_content.encode()),
                save=True
            )
            return True
        except Exception as e:
            self.stderr.write(f"Error creating image for {product.sku}: {e}")
            return False

    def _generate_placeholder_svg(self, product) -> str:
        colors = ["#3498db", "#e74c3c", "#2ecc71", "#9b59b6", "#f39c12", "#1abc9c"]
        color = random.choice(colors)

        return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="400" height="400" xmlns="http://www.w3.org/2000/svg">
  <rect width="400" height="400" fill="{color}" opacity="0.2"/>
  <rect x="20" y="20" width="360" height="360" fill="white" rx="10" ry="10" stroke="{color}" stroke-width="2"/>
  <text x="200" y="180" font-family="Arial, sans-serif" font-size="24" fill="#333" text-anchor="middle">{product.brand.name}</text>
  <text x="200" y="220" font-family="Arial, sans-serif" font-size="18" fill="#666" text-anchor="middle">{product.sku}</text>
  <text x="200" y="260" font-family="Arial, sans-serif" font-size="14" fill="#999" text-anchor="middle">{product.category.name}</text>
  <circle cx="200" cy="320" r="40" fill="{color}" opacity="0.5"/>
  <text x="200" y="328" font-family="Arial, sans-serif" font-size="24" fill="white" text-anchor="middle">IMG</text>
</svg>'''
