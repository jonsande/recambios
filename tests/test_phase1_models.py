import pytest
from django.db import IntegrityError, transaction

from apps.catalog.models import Brand, Category, Condition, PartNumber, Product, ProductImage
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


def make_product(sku: str = "SKU-0001") -> Product:
    supplier = make_supplier()
    brand = make_brand()
    category = make_category()
    condition = make_condition()
    return Product.objects.create(
        supplier=supplier,
        supplier_product_code=f"P-{sku}",
        sku=sku,
        slug=f"product-{sku.lower()}",
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
            slug="product-sku-unique-2",
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
        slug="product-sku-nobrand-1",
        title="No Brand Product",
        brand=None,
        category=category,
        condition=condition,
    )

    assert product.brand is None


@pytest.mark.django_db
def test_part_number_is_normalized_for_lookup() -> None:
    product = make_product(sku="SKU-PN")
    part_number = PartNumber.objects.create(
        product=product,
        number_raw=" ab-12 3 /x ",
        part_number_type=PartNumber.PartNumberType.OEM,
    )

    assert part_number.number_normalized == "AB123X"
    assert PartNumber.objects.get(number_normalized="AB123X").id == part_number.id


@pytest.mark.django_db
def test_only_one_primary_part_number_per_product() -> None:
    product = make_product(sku="SKU-PRIMARY-PN")
    PartNumber.objects.create(
        product=product,
        number_raw="A-100",
        part_number_type=PartNumber.PartNumberType.INTERNAL,
        is_primary=True,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        PartNumber.objects.create(
            product=product,
            number_raw="B-200",
            part_number_type=PartNumber.PartNumberType.OEM,
            is_primary=True,
        )


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
