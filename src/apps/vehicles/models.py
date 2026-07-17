from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


class Vehicle(models.Model):
    class VehicleType(models.TextChoices):
        CAR = "car", _("Coche")
        MOTORCYCLE = "motorcycle", _("Moto")
        TRUCK = "truck", _("Camión")
        VAN = "van", _("Furgoneta")
        OTHER = "other", _("Otro")

    class FuelType(models.TextChoices):
        GASOLINE = "gasoline", _("Gasolina")
        DIESEL = "diesel", _("Diésel")
        HYBRID = "hybrid", _("Híbrido")
        ELECTRIC = "electric", _("Eléctrico")
        LPG = "lpg", "LPG"
        CNG = "cng", "CNG"
        OTHER = "other", _("Otro")

    vehicle_type = models.CharField(
        _("tipo de vehículo"),
        max_length=20,
        choices=VehicleType.choices,
        default=VehicleType.CAR,
    )
    brand = models.ForeignKey(
        "catalog.Brand",
        on_delete=models.PROTECT,
        related_name="vehicles",
        verbose_name=_("marca"),
    )
    model = models.CharField(_("modelo"), max_length=120)
    generation = models.CharField(_("generación"), max_length=120, blank=True)
    variant = models.CharField(_("versión"), max_length=120, blank=True)
    year_start = models.PositiveSmallIntegerField(_("año inicial"), null=True, blank=True)
    year_end = models.PositiveSmallIntegerField(_("año final"), null=True, blank=True)
    engine_code = models.CharField(_("código de motor"), max_length=80, blank=True)
    fuel_type = models.CharField(
        _("combustible"), max_length=20, choices=FuelType.choices, blank=True
    )
    displacement_cc = models.PositiveIntegerField(
        _("cilindrada (cc)"), null=True, blank=True
    )
    power_hp = models.PositiveIntegerField(_("potencia (CV)"), null=True, blank=True)
    power_kw = models.PositiveIntegerField(_("potencia (kW)"), null=True, blank=True)
    notes = models.TextField(_("notas"), blank=True)
    is_active = models.BooleanField(_("activo"), default=True, db_index=True)
    created_at = models.DateTimeField(_("creado el"), auto_now_add=True)
    updated_at = models.DateTimeField(_("actualizado el"), auto_now=True)

    class Meta:
        verbose_name = _("vehículo")
        verbose_name_plural = _("vehículos")
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
        label_parts = [self.brand.name, self.model]
        if self.generation:
            label_parts.append(self.generation)
        if self.variant:
            label_parts.append(self.variant)

        year_label = ""
        if self.year_start and self.year_end:
            year_label = f"{self.year_start}-{self.year_end}"
        elif self.year_start:
            year_label = f"{self.year_start}+"
        elif self.year_end:
            year_label = f"-{self.year_end}"

        label = " ".join(label_parts)
        if year_label:
            return f"{label} [{year_label}]"
        return label


class ProductVehicleFitment(models.Model):
    class FitmentSource(models.TextChoices):
        SUPPLIER = "supplier", _("Proveedor")
        IMPORT = "import", _("Importación")
        MANUAL = "manual", _("Manual")

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="fitments",
        verbose_name=_("producto"),
    )
    vehicle = models.ForeignKey(
        "vehicles.Vehicle",
        on_delete=models.CASCADE,
        related_name="fitments",
        verbose_name=_("vehículo"),
    )
    fitment_notes = models.TextField(_("notas de compatibilidad"), blank=True)
    source = models.CharField(
        _("origen"),
        max_length=20,
        choices=FitmentSource.choices,
        default=FitmentSource.IMPORT,
    )
    is_verified = models.BooleanField(_("verificada"), default=False, db_index=True)
    created_at = models.DateTimeField(_("creada el"), auto_now_add=True)
    updated_at = models.DateTimeField(_("actualizada el"), auto_now=True)

    class Meta:
        verbose_name = _("compatibilidad con vehículo")
        verbose_name_plural = _("compatibilidades con vehículos")
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
