import hashlib
import re
from decimal import ROUND_HALF_UP, Decimal

from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

PART_NUMBER_NORMALIZER_RE = re.compile(r"[^A-Z0-9]+")
ATTRIBUTE_SPACES_RE = re.compile(r"\s+")


def normalize_part_number(value: str) -> str:
    return PART_NUMBER_NORMALIZER_RE.sub("", value.strip().upper())


def normalize_attribute_text(value: str) -> str:
    return ATTRIBUTE_SPACES_RE.sub(" ", value.strip().upper())


class Brand(models.Model):
    class BrandType(models.TextChoices):
        VEHICLE = "vehicle", _("Vehículos")
        PARTS = "parts", _("Recambios")
        BOTH = "both", _("Vehículos y recambios")

    name = models.CharField(_("nombre"), max_length=120, unique=True)
    slug = models.SlugField(_("slug"), max_length=140, unique=True)
    brand_type = models.CharField(
        _("tipo de marca"),
        max_length=20,
        choices=BrandType.choices,
        default=BrandType.PARTS,
    )
    country = models.CharField(_("país"), max_length=100, blank=True)
    is_active = models.BooleanField(_("activo"), default=True, db_index=True)
    created_at = models.DateTimeField(_("creado el"), auto_now_add=True)
    updated_at = models.DateTimeField(_("actualizado el"), auto_now=True)

    class Meta:
        verbose_name = _("marca")
        verbose_name_plural = _("marcas")
        ordering = ["name"]
        indexes = [
            models.Index(
                fields=["brand_type", "is_active"],
                name="catalog_brand_type_active_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Category(models.Model):
    name = models.CharField(_("nombre"), max_length=120)
    slug = models.SlugField(_("slug"), max_length=140, unique=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        verbose_name=_("categoría superior"),
    )
    description = models.TextField(_("descripción"), blank=True)
    sort_order = models.PositiveIntegerField(_("orden"), default=0)
    is_active = models.BooleanField(_("activa"), default=True, db_index=True)
    created_at = models.DateTimeField(_("creada el"), auto_now_add=True)
    updated_at = models.DateTimeField(_("actualizada el"), auto_now=True)

    class Meta:
        verbose_name = _("categoría")
        verbose_name_plural = _("categorías")
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "name"],
                name="catalog_category_parent_name_uq",
            )
        ]
        indexes = [
            models.Index(
                fields=["is_active", "sort_order"],
                name="cat_cat_active_sort_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Condition(models.Model):
    code = models.CharField(_("código"), max_length=32, unique=True)
    name = models.CharField(_("nombre"), max_length=80, unique=True)
    slug = models.SlugField(_("slug"), max_length=100, unique=True)
    description = models.TextField(_("descripción"), blank=True)
    is_active = models.BooleanField(_("activo"), default=True, db_index=True)
    created_at = models.DateTimeField(_("creado el"), auto_now_add=True)
    updated_at = models.DateTimeField(_("actualizado el"), auto_now=True)

    class Meta:
        verbose_name = _("estado del producto")
        verbose_name_plural = _("estados de los productos")
        ordering = ["name"]
        indexes = [
            models.Index(
                fields=["is_active", "code"],
                name="cat_cond_active_code_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class PartNumberType(models.Model):
    REQUIRED_BASE_CODES = ("OEM", "OES", "AIM")

    code = models.CharField(_("código"), max_length=20, unique=True)
    name = models.CharField(_("nombre"), max_length=80, blank=True)
    sort_order = models.PositiveSmallIntegerField(_("orden"), default=0)
    is_active = models.BooleanField(_("activo"), default=True, db_index=True)
    created_at = models.DateTimeField(_("creado el"), auto_now_add=True)
    updated_at = models.DateTimeField(_("actualizado el"), auto_now=True)

    class Meta:
        verbose_name = _("tipo de referencia de pieza")
        verbose_name_plural = _("tipos de referencia de pieza")
        ordering = ["sort_order", "code"]
        indexes = [
            models.Index(
                fields=["is_active", "sort_order"],
                name="cat_pntype_active_sort_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.code

    def save(self, *args, **kwargs) -> None:
        self.code = normalize_part_number(self.code or "")
        if not self.name:
            self.name = self.code
        super().save(*args, **kwargs)


class Product(models.Model):
    class PublicationStatus(models.TextChoices):
        DRAFT = "draft", _("Borrador")
        REVIEW = "review", _("En revisión")
        PUBLISHED = "published", _("Publicado")

    class PriceVisibilityMode(models.TextChoices):
        HIDDEN = "hidden", _("Precio oculto")
        VISIBLE_INFO = "visible_info", _("Visible (último precio conocido)")

    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name=_("proveedor"),
    )
    supplier_product_code = models.CharField(
        _("código de producto del proveedor"), max_length=64, null=True, blank=True
    )
    sku = models.CharField(
        max_length=64,
        unique=True,
        verbose_name=_("Código de Fabricante (OES/OE)"),
        help_text=_("Referencia OE principal del producto"),
    )
    slug = models.SlugField(_("slug"), max_length=180, unique=True, editable=False)
    title = models.CharField(_("título"), max_length=220)
    short_description = models.CharField(_("descripción breve"), max_length=280, blank=True)
    long_description = models.TextField(_("descripción completa"), blank=True)
    brand = models.ForeignKey(
        "catalog.Brand",
        on_delete=models.PROTECT,
        related_name="products",
        null=True,
        blank=True,
        verbose_name=_("Marca"),
        help_text=_(
            "Marca fabricante asociada a la referencia OE (no la marca del vehículo)"
        ),
    )
    category = models.ForeignKey(
        "catalog.Category",
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name=_("categoría"),
    )
    condition = models.ForeignKey(
        "catalog.Condition",
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name=_("estado del producto"),
    )
    publication_status = models.CharField(
        _("estado de publicación"),
        max_length=20,
        choices=PublicationStatus.choices,
        default=PublicationStatus.DRAFT,
        db_index=True,
    )
    published_at = models.DateTimeField(_("publicado el"), null=True, blank=True)
    price_visibility_mode = models.CharField(
        _("visibilidad del precio"),
        max_length=20,
        choices=PriceVisibilityMode.choices,
        default=PriceVisibilityMode.HIDDEN,
        db_index=True,
    )
    last_known_price = models.DecimalField(
        _("último precio conocido"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Precio unitario sin IVA."),
    )
    product_vat_rate = models.DecimalField(
        _("IVA del producto (%)"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("21.00"),
        help_text=_("Porcentaje de IVA que se aplica al último precio conocido."),
    )
    last_known_price_updated_at = models.DateTimeField(
        _("último precio conocido actualizado el"),
        null=True,
        blank=True,
        editable=False,
    )
    currency = models.CharField(_("moneda"), max_length=3, default="EUR")
    unit_of_sale = models.CharField(_("unidad de venta"), max_length=32, default="unit")
    quantity = models.PositiveIntegerField(_("cantidad"), default=1)
    unit_of_quantity = models.CharField(
        _("unidad de cantidad"), max_length=32, default="Pcs"
    )
    weight = models.DecimalField(
        _("peso"), max_digits=10, decimal_places=3, null=True, blank=True
    )
    length = models.DecimalField(
        _("largo"), max_digits=10, decimal_places=3, null=True, blank=True
    )
    width = models.DecimalField(
        _("ancho"), max_digits=10, decimal_places=3, null=True, blank=True
    )
    height = models.DecimalField(
        _("alto"), max_digits=10, decimal_places=3, null=True, blank=True
    )
    featured = models.BooleanField(_("destacado"), default=False, db_index=True)
    is_active = models.BooleanField(_("activo"), default=True, db_index=True)
    created_at = models.DateTimeField(_("creado el"), auto_now_add=True)
    updated_at = models.DateTimeField(_("actualizado el"), auto_now=True)

    @property
    def last_known_price_with_vat(self) -> Decimal | None:
        if self.last_known_price is None:
            return None
        multiplier = Decimal("1.00") + (self.product_vat_rate / Decimal("100"))
        return (self.last_known_price * multiplier).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    class Meta:
        verbose_name = _("producto")
        verbose_name_plural = _("productos")
        ordering = ["-updated_at"]
        permissions = [
            ("can_publish_product", _("Puede publicar productos")),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["supplier", "supplier_product_code"],
                condition=Q(supplier_product_code__isnull=False) & ~Q(supplier_product_code=""),
                name="catalog_product_supplier_code_uq",
            ),
            models.CheckConstraint(
                condition=~Q(publication_status="published") | Q(published_at__isnull=False),
                name="catalog_product_pub_requires_date_ck",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gte=1),
                name="catalog_product_quantity_gte_1_ck",
            ),
            models.CheckConstraint(
                condition=Q(product_vat_rate__gte=0) & Q(product_vat_rate__lte=100),
                name="catalog_product_vat_range_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=["publication_status", "is_active"],
                name="cat_prod_status_active_idx",
            ),
            models.Index(
                fields=["price_visibility_mode", "is_active"],
                name="catalog_product_price_mode_idx",
            ),
            models.Index(
                fields=["brand", "category"],
                name="cat_prod_brand_cat_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sku} - {self.title}"

    def _build_slug_from_sku(self) -> str:
        max_length = self._meta.get_field("slug").max_length
        base_slug = slugify(self.sku).strip("-") or "product"
        base_slug = base_slug[:max_length].rstrip("-") or "product"

        if not Product.objects.exclude(pk=self.pk).filter(slug=base_slug).exists():
            return base_slug

        suffix = hashlib.sha1(self.sku.encode("utf-8")).hexdigest()[:8]
        trimmed_length = max_length - len(suffix) - 1
        trimmed_base = base_slug[:trimmed_length].rstrip("-") or "product"
        return f"{trimmed_base}-{suffix}"

    def sync_primary_oem_part_number(self) -> None:
        reference_value = (self.sku or "").strip()
        if not reference_value:
            return

        with transaction.atomic():
            oem_part_number_type, _ = PartNumberType.objects.get_or_create(
                code="OEM",
                defaults={"name": "OEM", "sort_order": 1, "is_active": True},
            )
            normalized_reference = normalize_part_number(reference_value)

            matching_oem_part_number = (
                self.part_numbers.filter(
                    part_number_type=oem_part_number_type,
                    number_normalized=normalized_reference,
                )
                .order_by("pk")
                .first()
            )
            primary_oem_part_number = (
                self.part_numbers.filter(
                    part_number_type=oem_part_number_type,
                    is_primary=True,
                )
                .order_by("pk")
                .first()
            )
            target_part_number = matching_oem_part_number or primary_oem_part_number

            self.part_numbers.exclude(pk=getattr(target_part_number, "pk", None)).filter(
                is_primary=True
            ).update(is_primary=False)

            if target_part_number is None:
                PartNumber.objects.create(
                    product=self,
                    brand=self.brand,
                    number_raw=reference_value,
                    part_number_type=oem_part_number_type,
                    is_primary=True,
                )
                return

            target_part_number.number_raw = reference_value
            target_part_number.brand = self.brand
            target_part_number.part_number_type = oem_part_number_type
            target_part_number.is_primary = True
            target_part_number.save()

    def save(self, *args, **kwargs) -> None:
        price_changed = self._state.adding and self.last_known_price is not None
        if not self._state.adding and self.pk:
            previous_price = type(self).objects.filter(pk=self.pk).values_list(
                "last_known_price", flat=True
            ).first()
            price_changed = previous_price != self.last_known_price
        if price_changed:
            self.last_known_price_updated_at = timezone.now()
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = tuple(
                    set(kwargs["update_fields"]) | {"last_known_price_updated_at"}
                )
        self.slug = self._build_slug_from_sku()
        super().save(*args, **kwargs)
        self.sync_primary_oem_part_number()


class PartNumber(models.Model):
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="part_numbers",
        verbose_name=_("producto"),
    )
    brand = models.ForeignKey(
        "catalog.Brand",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="part_numbers",
        verbose_name=_("marca"),
    )
    number_raw = models.CharField(_("referencia original"), max_length=128)
    number_normalized = models.CharField(
        _("referencia normalizada"), max_length=128, editable=False, db_index=True
    )
    part_number_type = models.ForeignKey(
        "catalog.PartNumberType",
        on_delete=models.PROTECT,
        related_name="part_numbers",
        verbose_name=_("tipo de referencia"),
    )
    is_primary = models.BooleanField(_("principal"), default=False, db_index=True)
    notes = models.TextField(_("notas"), blank=True)
    created_at = models.DateTimeField(_("creada el"), auto_now_add=True)
    updated_at = models.DateTimeField(_("actualizada el"), auto_now=True)

    class Meta:
        verbose_name = _("referencia de pieza")
        verbose_name_plural = _("referencias de pieza")
        ordering = ["number_normalized"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "number_normalized", "part_number_type"],
                name="catalog_partnumber_product_number_type_uq",
            ),
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(is_primary=True),
                name="catalog_partnumber_primary_per_product_uq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["part_number_type", "number_normalized"],
                name="cat_pn_type_norm_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.number_raw

    def save(self, *args, **kwargs) -> None:
        source_value = self.number_raw or self.number_normalized or ""
        self.number_normalized = normalize_part_number(source_value)
        super().save(*args, **kwargs)


class AttributeDefinition(models.Model):
    class DataType(models.TextChoices):
        TEXT = "text", _("Texto")
        NUMBER = "number", _("Número")
        BOOLEAN = "boolean", _("Sí/No")

    name = models.CharField(_("nombre"), max_length=120, unique=True)
    slug = models.SlugField(_("slug"), max_length=140, unique=True)
    data_type = models.CharField(
        _("tipo de dato"),
        max_length=20,
        choices=DataType.choices,
        default=DataType.TEXT,
        db_index=True,
    )
    unit = models.CharField(_("unidad"), max_length=24, blank=True)
    is_filterable = models.BooleanField(_("filtrable"), default=True, db_index=True)
    is_visible_on_product = models.BooleanField(
        _("visible en el producto"), default=True, db_index=True
    )
    allows_multiple_values = models.BooleanField(
        _("admite varios valores"), default=False, db_index=True
    )
    sort_order = models.PositiveIntegerField(_("orden"), default=0)
    created_at = models.DateTimeField(_("creada el"), auto_now_add=True)
    updated_at = models.DateTimeField(_("actualizada el"), auto_now=True)

    class Meta:
        verbose_name = _("definición de atributo")
        verbose_name_plural = _("definiciones de atributos")
        ordering = ["sort_order", "name"]
        indexes = [
            models.Index(
                fields=["is_filterable", "sort_order"],
                name="cat_attr_filter_sort_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class ProductAttributeValue(models.Model):
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="attribute_values",
        verbose_name=_("producto"),
    )
    attribute_definition = models.ForeignKey(
        "catalog.AttributeDefinition",
        on_delete=models.CASCADE,
        related_name="product_values",
        verbose_name=_("atributo"),
    )
    value_text = models.CharField(_("valor de texto"), max_length=255, blank=True)
    value_number = models.DecimalField(
        _("valor numérico"), max_digits=14, decimal_places=4, null=True, blank=True
    )
    value_boolean = models.BooleanField(_("valor Sí/No"), null=True, blank=True)
    value_normalized = models.CharField(
        _("valor normalizado"), max_length=255, blank=True, db_index=True
    )
    created_at = models.DateTimeField(_("creado el"), auto_now_add=True)
    updated_at = models.DateTimeField(_("actualizado el"), auto_now=True)

    class Meta:
        verbose_name = _("valor de atributo de producto")
        verbose_name_plural = _("valores de atributos de productos")
        ordering = ["attribute_definition__sort_order", "attribute_definition__name"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    (
                        Q(value_text__gt="")
                        & Q(value_number__isnull=True)
                        & Q(value_boolean__isnull=True)
                    )
                    | (
                        Q(value_text="")
                        & Q(value_number__isnull=False)
                        & Q(value_boolean__isnull=True)
                    )
                    | (
                        Q(value_text="")
                        & Q(value_number__isnull=True)
                        & Q(value_boolean__isnull=False)
                    )
                ),
                name="catalog_pav_exactly_one_value_ck",
            ),
            models.UniqueConstraint(
                fields=["product", "attribute_definition", "value_normalized"],
                name="catalog_pav_product_attr_value_uq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["attribute_definition", "value_normalized"],
                name="catalog_pav_attr_value_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product.sku} · {self.attribute_definition.name}"

    def _normalized_number(self, value: Decimal) -> str:
        text = format(value.normalize(), "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"

    def _compute_normalized_value(self) -> str:
        if self.value_text:
            return normalize_attribute_text(self.value_text)
        if self.value_number is not None:
            return self._normalized_number(self.value_number)
        if self.value_boolean is not None:
            return "TRUE" if self.value_boolean else "FALSE"
        return ""

    def save(self, *args, **kwargs) -> None:
        self.value_normalized = self._compute_normalized_value()
        super().save(*args, **kwargs)


class ProductImage(models.Model):
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("producto"),
    )
    image = models.ImageField(_("imagen"), upload_to="product_images/%Y/%m/")
    alt_text = models.CharField(_("texto alternativo"), max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(_("orden"), default=0)
    is_primary = models.BooleanField(_("principal"), default=False, db_index=True)
    created_at = models.DateTimeField(_("creada el"), auto_now_add=True)
    updated_at = models.DateTimeField(_("actualizada el"), auto_now=True)

    class Meta:
        verbose_name = _("imagen de producto")
        verbose_name_plural = _("imágenes de productos")
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(is_primary=True),
                name="catalog_productimage_primary_per_product_uq",
            )
        ]
        indexes = [
            models.Index(
                fields=["product", "sort_order"],
                name="cat_img_prod_sort_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"ProductImage {self.pk}"
