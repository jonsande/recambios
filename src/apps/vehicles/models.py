from django.db import models
from django.db.models import Q


class Vehicle(models.Model):
    class VehicleType(models.TextChoices):
        CAR = "car", "Car"
        MOTORCYCLE = "motorcycle", "Motorcycle"
        TRUCK = "truck", "Truck"
        VAN = "van", "Van"
        OTHER = "other", "Other"

    class FuelType(models.TextChoices):
        GASOLINE = "gasoline", "Gasoline"
        DIESEL = "diesel", "Diesel"
        HYBRID = "hybrid", "Hybrid"
        ELECTRIC = "electric", "Electric"
        LPG = "lpg", "LPG"
        CNG = "cng", "CNG"
        OTHER = "other", "Other"

    vehicle_type = models.CharField(
        max_length=20,
        choices=VehicleType.choices,
        default=VehicleType.CAR,
    )
    brand = models.ForeignKey(
        "catalog.Brand",
        on_delete=models.PROTECT,
        related_name="vehicles",
    )
    model = models.CharField(max_length=120)
    generation = models.CharField(max_length=120, blank=True)
    variant = models.CharField(max_length=120, blank=True)
    year_start = models.PositiveSmallIntegerField(null=True, blank=True)
    year_end = models.PositiveSmallIntegerField(null=True, blank=True)
    engine_code = models.CharField(max_length=80, blank=True)
    fuel_type = models.CharField(max_length=20, choices=FuelType.choices, blank=True)
    displacement_cc = models.PositiveIntegerField(null=True, blank=True)
    power_hp = models.PositiveIntegerField(null=True, blank=True)
    power_kw = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["brand__name", "model", "generation", "variant", "year_start"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(year_end__isnull=True)
                    | Q(year_start__isnull=True)
                    | Q(year_end__gte=models.F("year_start"))
                ),
                name="vehicles_vehicle_year_range_ck",
            )
        ]
        indexes = [
            models.Index(
                fields=["vehicle_type", "brand"],
                name="veh_type_brand_idx",
            ),
            models.Index(
                fields=["model", "year_start", "year_end"],
                name="veh_model_year_idx",
            ),
            models.Index(fields=["engine_code"], name="vehicles_vehicle_engine_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.brand.name} {self.model} {self.generation}".strip()


class ProductVehicleFitment(models.Model):
    class FitmentSource(models.TextChoices):
        SUPPLIER = "supplier", "Supplier"
        IMPORT = "import", "Import"
        MANUAL = "manual", "Manual"

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="fitments",
    )
    vehicle = models.ForeignKey(
        "vehicles.Vehicle",
        on_delete=models.CASCADE,
        related_name="fitments",
    )
    fitment_notes = models.TextField(blank=True)
    source = models.CharField(
        max_length=20,
        choices=FitmentSource.choices,
        default=FitmentSource.IMPORT,
    )
    is_verified = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product__sku", "vehicle__brand__name", "vehicle__model"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "vehicle"],
                name="vehicles_fitment_product_vehicle_uq",
            )
        ]
        indexes = [
            models.Index(
                fields=["product", "is_verified"],
                name="veh_fit_prod_ver_idx",
            ),
            models.Index(
                fields=["vehicle", "is_verified"],
                name="veh_fit_veh_ver_idx",
            ),
            models.Index(
                fields=["source", "is_verified"],
                name="veh_fit_src_ver_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product.sku} -> {self.vehicle}"
