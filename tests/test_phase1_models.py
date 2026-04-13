import pytest
from django.db import IntegrityError, transaction
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


def make_supplier(code: str = "SUP001") -> Supplier:
    return Supplier.objects.create(
        name=f"Supplier {code}",
        slug=f"supplier-{code.lower()}",
        code=code,
    )


def make_brand(name: str = "Bosch", slug: str = "bosch") -> Brand:
    return Brand.objects.create(name=name, slug=slug, brand_type=Brand.BrandType.PARTS)


def make_category(name: str = "Alternator", slug: str = "alternator") -> Category:
    return Category.objects.create(name=name, slug=slug)


def make_condition(code: str = "new", name: str = "Nuevo", slug: str = "new") -> Condition:
    return Condition.objects.create(code=code, name=name, slug=slug)


def get_part_number_type(code: str) -> PartNumberType:
    return PartNumberType.objects.get(code=code)


def make_product(sku: str = "SKU-0001") -> Product:
    supplier = make_supplier()
    brand = make_brand()
    category = make_category()
    condition = make_condition()
    return Product.objects.create(
        supplier=supplier,
        supplier_product_code=f"P-{sku}",
        sku=sku,
        title=f"Product {sku}",
        brand=brand,
        category=category,
        condition=condition,
    )


@pytest.mark.django_db
def test_product_sku_is_globally_unique() -> None:
    make_product(sku="SKU-UNIQUE")
    supplier_2 = make_supplier(code="SUP002")
    brand = make_brand(name="Valeo", slug="valeo")
    category = make_category(name="Starter", slug="starter")
    condition = make_condition(code="used", name="Usado", slug="used")

    with pytest.raises(IntegrityError), transaction.atomic():
        Product.objects.create(
            supplier=supplier_2,
            supplier_product_code="SUP2-1",
            sku="SKU-UNIQUE",
            title="Duplicated SKU",
            brand=brand,
            category=category,
            condition=condition,
        )


@pytest.mark.django_db
def test_product_brand_can_be_empty_when_not_required() -> None:
    supplier = make_supplier(code="SUP-NOBRAND")
    category = make_category(name="Electrical", slug="electrical")
    condition = make_condition(code="core", name="Core", slug="core")

    product = Product.objects.create(
        supplier=supplier,
        supplier_product_code="SUP-NOBRAND-1",
        sku="SKU-NOBRAND-1",
        title="No Brand Product",
        brand=None,
        category=category,
        condition=condition,
    )

    assert product.brand is None


@pytest.mark.django_db
def test_product_quantity_defaults_are_applied() -> None:
    product = make_product(sku="SKU-QTY-DEFAULT")

    assert product.quantity == 1
    assert product.unit_of_quantity == "Pcs"


@pytest.mark.django_db
def test_product_quantity_cannot_be_less_than_one() -> None:
    product = make_product(sku="SKU-QTY-ZERO")
    product.quantity = 0

    with pytest.raises(IntegrityError), transaction.atomic():
        product.save(update_fields=["quantity"])


@pytest.mark.django_db
def test_part_number_is_normalized_for_lookup() -> None:
    product = make_product(sku="SKU-PN")
    part_number = PartNumber.objects.create(
        product=product,
        number_raw=" ab-12 3 /x ",
        part_number_type=get_part_number_type("OEM"),
    )

    assert part_number.number_normalized == "AB123X"
    assert PartNumber.objects.get(number_normalized="AB123X").id == part_number.id


@pytest.mark.django_db
def test_only_one_primary_part_number_per_product() -> None:
    product = make_product(sku="SKU-PRIMARY-PN")
    PartNumber.objects.create(
        product=product,
        number_raw="A-100",
        part_number_type=get_part_number_type("AIM"),
        is_primary=True,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        PartNumber.objects.create(
            product=product,
            number_raw="B-200",
            part_number_type=get_part_number_type("OEM"),
            is_primary=True,
        )


@pytest.mark.django_db
def test_required_part_number_types_are_seeded() -> None:
    assert set(PartNumberType.objects.values_list("code", flat=True)) == {"OEM", "OES", "AIM"}


@pytest.mark.django_db
def test_custom_part_number_type_can_be_created() -> None:
    custom_type = PartNumberType.objects.create(code="aftermarket")

    assert custom_type.code == "AFTERMARKET"
    assert custom_type.name == "AFTERMARKET"


@pytest.mark.django_db
def test_part_number_uses_part_number_type_relation() -> None:
    product = make_product(sku="SKU-PN-TYPE")
    custom_type = PartNumberType.objects.create(code="XREF", name="Cross Reference")
    part_number = PartNumber.objects.create(
        product=product,
        number_raw="X-123",
        part_number_type=custom_type,
    )

    assert part_number.part_number_type_id == custom_type.id
    assert part_number.part_number_type.code == "XREF"


@pytest.mark.django_db
def test_product_slug_is_generated_from_sku_and_overrides_manual_value() -> None:
    supplier = make_supplier(code="SUP-SLUG")
    brand = make_brand(name="Slug Brand", slug="slug-brand")
    category = make_category(name="Slug Category", slug="slug-category")
    condition = make_condition(code="slug-new", name="Slug New", slug="slug-new")

    product = Product.objects.create(
        supplier=supplier,
        supplier_product_code="SUP-SLUG-1",
        sku="SKU / Slug 001",
        slug="manual-slug",
        title="Slug Product",
        brand=brand,
        category=category,
        condition=condition,
    )

    assert product.slug == slugify(product.sku)


@pytest.mark.django_db
def test_product_slug_appends_deterministic_suffix_when_slugified_skus_collide() -> None:
    supplier = make_supplier(code="SUP-SLUG-COLLIDE")
    brand = make_brand(name="Slug Collision Brand", slug="slug-collision-brand")
    category = make_category(name="Slug Collision Category", slug="slug-collision-category")
    condition = make_condition(code="slug-collision", name="Slug Collision", slug="slug-collision")

    first = Product.objects.create(
        supplier=supplier,
        supplier_product_code="SUP-SLUG-COLLIDE-1",
        sku="SKU A",
        title="Slug Collision 1",
        brand=brand,
        category=category,
        condition=condition,
    )
    second = Product.objects.create(
        supplier=supplier,
        supplier_product_code="SUP-SLUG-COLLIDE-2",
        sku="SKU-A",
        title="Slug Collision 2",
        brand=brand,
        category=category,
        condition=condition,
    )

    assert first.slug == "sku-a"
    assert second.slug.startswith("sku-a-")
    assert second.slug != first.slug
    assert len(second.slug.rsplit("-", maxsplit=1)[-1]) == 8


@pytest.mark.django_db
def test_fitment_relationship_is_unique_per_product_vehicle() -> None:
    product = make_product(sku="SKU-FITMENT")
    vehicle = Vehicle.objects.create(
        vehicle_type=Vehicle.VehicleType.CAR,
        brand=product.brand,
        model="3 Series",
        generation="E90",
        year_start=2008,
        year_end=2011,
    )
    ProductVehicleFitment.objects.create(product=product, vehicle=vehicle)

    with pytest.raises(IntegrityError), transaction.atomic():
        ProductVehicleFitment.objects.create(product=product, vehicle=vehicle)


@pytest.mark.django_db
def test_vehicle_string_representation_includes_variant_and_year_range() -> None:
    brand = make_brand(name="BMW", slug="bmw")
    vehicle = Vehicle.objects.create(
        vehicle_type=Vehicle.VehicleType.CAR,
        brand=brand,
        model="3 Series",
        generation="E90",
        variant="320d",
        year_start=2008,
        year_end=2011,
    )

    assert str(vehicle) == "BMW 3 Series E90 320d [2008-2011]"


@pytest.mark.django_db
def test_vehicle_string_representation_handles_partial_or_missing_years() -> None:
    brand = make_brand(name="Audi", slug="audi")
    year_start_only = Vehicle.objects.create(
        vehicle_type=Vehicle.VehicleType.CAR,
        brand=brand,
        model="A4",
        generation="B8",
        year_start=2008,
    )
    year_end_only = Vehicle.objects.create(
        vehicle_type=Vehicle.VehicleType.CAR,
        brand=brand,
        model="A4",
        generation="B8",
        variant="Avant",
        year_end=2015,
    )
    no_years = Vehicle.objects.create(
        vehicle_type=Vehicle.VehicleType.CAR,
        brand=brand,
        model="A4",
        generation="B8",
    )

    assert str(year_start_only) == "Audi A4 B8 [2008+]"
    assert str(year_end_only) == "Audi A4 B8 Avant [-2015]"
    assert str(no_years) == "Audi A4 B8"


@pytest.mark.django_db
def test_only_one_primary_image_per_product() -> None:
    product = make_product(sku="SKU-PRIMARY-IMG")
    ProductImage.objects.create(
        product=product,
        image="product_images/sku-primary-img-1.jpg",
        is_primary=True,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        ProductImage.objects.create(
            product=product,
            image="product_images/sku-primary-img-2.jpg",
            is_primary=True,
        )
