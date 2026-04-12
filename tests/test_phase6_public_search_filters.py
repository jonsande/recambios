from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.models import (
    AttributeDefinition,
    Brand,
    Category,
    Condition,
    PartNumber,
    Product,
    ProductAttributeValue,
)
from apps.suppliers.models import Supplier
from apps.vehicles.models import ProductVehicleFitment, Vehicle


def make_supplier(code: str) -> Supplier:
    return Supplier.objects.create(
        name=f"Supplier {code}",
        slug=f"supplier-{code.lower()}",
        code=code,
        is_active=True,
    )



def make_brand(
    name: str,
    slug: str,
    *,
    brand_type: str = Brand.BrandType.PARTS,
    is_active: bool = True,
) -> Brand:
    return Brand.objects.create(
        name=name,
        slug=slug,
        brand_type=brand_type,
        is_active=is_active,
    )



def make_category(name: str, slug: str, *, is_active: bool = True) -> Category:
    return Category.objects.create(name=name, slug=slug, is_active=is_active)



def make_condition(code: str, name: str, slug: str, *, is_active: bool = True) -> Condition:
    return Condition.objects.create(code=code, name=name, slug=slug, is_active=is_active)



def make_product(
    *,
    supplier: Supplier,
    sku: str,
    title: str,
    category: Category,
    condition: Condition,
    brand: Brand | None = None,
    publication_status: str = Product.PublicationStatus.PUBLISHED,
    is_active: bool = True,
) -> Product:
    published_at = None
    if publication_status == Product.PublicationStatus.PUBLISHED:
        published_at = timezone.now() - timedelta(hours=1)

    return Product.objects.create(
        supplier=supplier,
        supplier_product_code=f"{supplier.code}-{sku}",
        sku=sku,
        slug=f"product-{sku.lower()}",
        title=title,
        short_description=f"Short {title}",
        long_description=f"Long {title}",
        brand=brand,
        category=category,
        condition=condition,
        publication_status=publication_status,
        published_at=published_at,
        price_visibility_mode=Product.PriceVisibilityMode.HIDDEN,
        is_active=is_active,
    )



def add_fitment(
    *,
    product: Product,
    vehicle_brand: Brand,
    model: str,
    generation: str = "",
    variant: str = "",
    year_start: int | None = None,
    year_end: int | None = None,
) -> ProductVehicleFitment:
    vehicle = Vehicle.objects.create(
        vehicle_type=Vehicle.VehicleType.CAR,
        brand=vehicle_brand,
        model=model,
        generation=generation,
        variant=variant,
        year_start=year_start,
        year_end=year_end,
        is_active=True,
    )
    return ProductVehicleFitment.objects.create(product=product, vehicle=vehicle)



def product_ids_from_response(response) -> list[int]:
    return [product.id for product in response.context["products"]]


@pytest.mark.django_db
def test_search_by_sku_returns_expected_public_product(client) -> None:
    supplier = make_supplier("P6-SKU")
    category = make_category("Alternators", "p6-alternators")
    condition = make_condition("p6-new", "Nuevo P6", "p6-new")

    expected = make_product(
        supplier=supplier,
        sku="SKU-P6-001",
        title="Alternator A",
        category=category,
        condition=condition,
    )
    make_product(
        supplier=supplier,
        sku="SKU-P6-XYZ",
        title="Alternator B",
        category=category,
        condition=condition,
    )

    response = client.get("/es/productos/?q=SKU-P6-001")

    assert response.status_code == 200
    assert product_ids_from_response(response) == [expected.id]


@pytest.mark.django_db
def test_search_by_part_number_raw_and_normalized_returns_product(client) -> None:
    supplier = make_supplier("P6-REF")
    category = make_category("Turbo", "p6-turbo")
    condition = make_condition("p6-ref-new", "Nuevo Ref", "p6-ref-new")
    product = make_product(
        supplier=supplier,
        sku="SKU-P6-REF",
        title="Turbo Unit",
        category=category,
        condition=condition,
    )
    PartNumber.objects.create(
        product=product,
        number_raw="06A-145-710N",
        part_number_type=PartNumber.PartNumberType.OEM,
    )

    raw_response = client.get("/es/productos/?q=06A-145-710N")
    normalized_response = client.get("/es/productos/?q=06A145710N")

    assert product_ids_from_response(raw_response) == [product.id]
    assert product_ids_from_response(normalized_response) == [product.id]


@pytest.mark.django_db
def test_vehicle_term_search_in_q_matches_vehicle_fields(client) -> None:
    supplier = make_supplier("P6-VEH-Q")
    category = make_category("Brakes", "p6-brakes")
    condition = make_condition("p6-veh-new", "Nuevo Veh", "p6-veh-new")
    vehicle_brand = make_brand(
        "Mercedes",
        "mercedes-p6",
        brand_type=Brand.BrandType.VEHICLE,
    )

    product = make_product(
        supplier=supplier,
        sku="SKU-P6-VEH-Q",
        title="Brake Set",
        category=category,
        condition=condition,
    )
    add_fitment(
        product=product,
        vehicle_brand=vehicle_brand,
        model="Sprinter",
        generation="W906",
    )

    response = client.get("/es/productos/?q=Sprinter")

    assert response.status_code == 200
    assert product_ids_from_response(response) == [product.id]


@pytest.mark.django_db
def test_combined_filters_apply_with_attribute_filtering(client) -> None:
    supplier = make_supplier("P6-COMB")
    product_brand = make_brand("Valeo", "valeo-p6")
    vehicle_brand = make_brand(
        "BMW",
        "bmw-veh-p6",
        brand_type=Brand.BrandType.VEHICLE,
    )
    category_match = make_category("Electrico", "electrico-p6")
    category_other = make_category("Motor", "motor-p6")
    condition_match = make_condition("p6-cond-new", "Nuevo Comb", "p6-cond-new")
    condition_other = make_condition("p6-cond-used", "Usado Comb", "p6-cond-used")

    side_attr = AttributeDefinition.objects.create(
        name="Lado montaje",
        slug="lado-montaje",
        data_type=AttributeDefinition.DataType.TEXT,
        is_filterable=True,
    )

    matching = make_product(
        supplier=supplier,
        sku="SKU-P6-MATCH",
        title="Matching Product",
        category=category_match,
        condition=condition_match,
        brand=product_brand,
    )
    add_fitment(
        product=matching,
        vehicle_brand=vehicle_brand,
        model="320d",
        year_start=2008,
        year_end=2012,
    )
    ProductAttributeValue.objects.create(
        product=matching,
        attribute_definition=side_attr,
        value_text="Izquierdo",
    )

    wrong_model = make_product(
        supplier=supplier,
        sku="SKU-P6-WRONG-MODEL",
        title="Wrong Model Product",
        category=category_match,
        condition=condition_match,
        brand=product_brand,
    )
    add_fitment(
        product=wrong_model,
        vehicle_brand=vehicle_brand,
        model="330d",
        year_start=2008,
        year_end=2012,
    )
    ProductAttributeValue.objects.create(
        product=wrong_model,
        attribute_definition=side_attr,
        value_text="Izquierdo",
    )

    wrong_attribute = make_product(
        supplier=supplier,
        sku="SKU-P6-WRONG-ATTR",
        title="Wrong Attr Product",
        category=category_match,
        condition=condition_match,
        brand=product_brand,
    )
    add_fitment(
        product=wrong_attribute,
        vehicle_brand=vehicle_brand,
        model="320d",
        year_start=2008,
        year_end=2012,
    )
    ProductAttributeValue.objects.create(
        product=wrong_attribute,
        attribute_definition=side_attr,
        value_text="Derecho",
    )

    wrong_category = make_product(
        supplier=supplier,
        sku="SKU-P6-WRONG-CAT",
        title="Wrong Category Product",
        category=category_other,
        condition=condition_match,
        brand=product_brand,
    )
    add_fitment(
        product=wrong_category,
        vehicle_brand=vehicle_brand,
        model="320d",
        year_start=2008,
        year_end=2012,
    )
    ProductAttributeValue.objects.create(
        product=wrong_category,
        attribute_definition=side_attr,
        value_text="Izquierdo",
    )

    wrong_condition = make_product(
        supplier=supplier,
        sku="SKU-P6-WRONG-COND",
        title="Wrong Condition Product",
        category=category_match,
        condition=condition_other,
        brand=product_brand,
    )
    add_fitment(
        product=wrong_condition,
        vehicle_brand=vehicle_brand,
        model="320d",
        year_start=2008,
        year_end=2012,
    )
    ProductAttributeValue.objects.create(
        product=wrong_condition,
        attribute_definition=side_attr,
        value_text="Izquierdo",
    )

    response = client.get(
        "/es/productos/?brand=bmw-veh-p6&model=320d&year=2010"
        "&category=electrico-p6&condition=p6-cond-new&attr_lado-montaje=IZQUIERDO"
    )

    assert response.status_code == 200
    assert product_ids_from_response(response) == [matching.id]


@pytest.mark.django_db
def test_search_results_do_not_duplicate_products_when_multiple_joins_match(client) -> None:
    supplier = make_supplier("P6-DUP")
    category = make_category("Bombas", "p6-bombas")
    condition = make_condition("p6-dup-new", "Nuevo Dup", "p6-dup-new")

    product = make_product(
        supplier=supplier,
        sku="SKU-P6-DUP",
        title="Duplicate Guard Product",
        category=category,
        condition=condition,
    )
    PartNumber.objects.create(
        product=product,
        number_raw="REF-777",
        part_number_type=PartNumber.PartNumberType.OE,
    )
    PartNumber.objects.create(
        product=product,
        number_raw="REF 777",
        part_number_type=PartNumber.PartNumberType.OEM,
    )

    response = client.get("/es/productos/?q=REF777")
    ids = product_ids_from_response(response)

    assert ids == [product.id]
    assert len(ids) == len(set(ids))


@pytest.mark.django_db
def test_public_visibility_rules_are_preserved_under_search_and_filters(client) -> None:
    supplier = make_supplier("P6-VIS")
    category = make_category("Dirección", "p6-direccion")
    condition = make_condition("p6-vis-new", "Nuevo Vis", "p6-vis-new")
    vehicle_brand = make_brand(
        "SEAT",
        "seat-veh-p6",
        brand_type=Brand.BrandType.VEHICLE,
    )

    public_product = make_product(
        supplier=supplier,
        sku="SKU-P6-VIS-PUB",
        title="Visible Product",
        category=category,
        condition=condition,
        publication_status=Product.PublicationStatus.PUBLISHED,
        is_active=True,
    )
    add_fitment(
        product=public_product,
        vehicle_brand=vehicle_brand,
        model="Ibiza",
        year_start=2010,
        year_end=2016,
    )

    draft_product = make_product(
        supplier=supplier,
        sku="SKU-P6-VIS-DRAFT",
        title="Draft Product",
        category=category,
        condition=condition,
        publication_status=Product.PublicationStatus.DRAFT,
        is_active=True,
    )
    add_fitment(
        product=draft_product,
        vehicle_brand=vehicle_brand,
        model="Ibiza",
        year_start=2010,
        year_end=2016,
    )

    inactive_product = make_product(
        supplier=supplier,
        sku="SKU-P6-VIS-INACTIVE",
        title="Inactive Product",
        category=category,
        condition=condition,
        publication_status=Product.PublicationStatus.PUBLISHED,
        is_active=False,
    )
    add_fitment(
        product=inactive_product,
        vehicle_brand=vehicle_brand,
        model="Ibiza",
        year_start=2010,
        year_end=2016,
    )

    response = client.get("/es/productos/?brand=seat-veh-p6&model=Ibiza")

    assert response.status_code == 200
    assert product_ids_from_response(response) == [public_product.id]


@pytest.mark.django_db
def test_category_route_precedence_over_category_query_param(client) -> None:
    supplier = make_supplier("P6-CAT-ROUTE")
    condition = make_condition("p6-cat-new", "Nuevo Cat", "p6-cat-new")
    route_category = make_category("Route Category", "route-cat-p6")
    query_category = make_category("Query Category", "query-cat-p6")

    route_product = make_product(
        supplier=supplier,
        sku="SKU-P6-ROUTE",
        title="Route Product",
        category=route_category,
        condition=condition,
    )
    make_product(
        supplier=supplier,
        sku="SKU-P6-QUERY",
        title="Query Product",
        category=query_category,
        condition=condition,
    )

    response = client.get(f"/es/categorias/{route_category.slug}/?category={query_category.slug}")

    assert response.status_code == 200
    assert product_ids_from_response(response) == [route_product.id]


@pytest.mark.django_db
def test_pagination_preserves_search_and_filter_query_params(client) -> None:
    supplier = make_supplier("P6-PAGE")
    category = make_category("Page Category", "page-category-p6")
    condition = make_condition("p6-page-new", "Nuevo Page", "p6-page-new")
    vehicle_brand = make_brand(
        "Ford",
        "ford-veh-p6",
        brand_type=Brand.BrandType.VEHICLE,
    )

    for index in range(1, 14):
        product = make_product(
            supplier=supplier,
            sku=f"SKU-PAGE-{index:03d}",
            title=f"Page Product {index:03d}",
            category=category,
            condition=condition,
        )
        add_fitment(
            product=product,
            vehicle_brand=vehicle_brand,
            model="Transit",
            year_start=2014,
            year_end=2022,
        )

    response = client.get("/es/productos/?q=SKU-PAGE&brand=ford-veh-p6")
    content = response.content.decode()

    assert response.status_code == 200
    assert response.context["is_paginated"] is True
    assert response.context["query_string_without_page"] == "q=SKU-PAGE&brand=ford-veh-p6"
    assert "q=SKU-PAGE" in content
    assert "brand=ford-veh-p6" in content
    assert "page=2" in content
