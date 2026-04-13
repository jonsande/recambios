from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.models import Brand, Category, Condition, Product
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
    vehicle_type: str = Vehicle.VehicleType.CAR,
    generation: str = "",
    variant: str = "",
    year_start: int | None = None,
    year_end: int | None = None,
    engine_code: str = "",
    fitment_notes: str = "",
    is_verified: bool = False,
) -> ProductVehicleFitment:
    vehicle = Vehicle.objects.create(
        vehicle_type=vehicle_type,
        brand=vehicle_brand,
        model=model,
        generation=generation,
        variant=variant,
        year_start=year_start,
        year_end=year_end,
        engine_code=engine_code,
        is_active=True,
    )
    return ProductVehicleFitment.objects.create(
        product=product,
        vehicle=vehicle,
        fitment_notes=fitment_notes,
        is_verified=is_verified,
    )


def product_ids_from_response(response) -> list[int]:
    return [product.id for product in response.context["products"]]


def template_names(response) -> set[str]:
    return {template.name for template in response.templates if template.name}


@pytest.mark.django_db
def test_compatibility_browsing_pages_resolve_in_es_and_en(client) -> None:
    supplier = make_supplier("P7-BROWSE")
    category = make_category("Compatibilidad", "compatibilidad-p7")
    condition = make_condition("p7-new", "Nuevo P7", "p7-new")
    vehicle_brand = make_brand(
        "SEAT P7",
        "seat-veh-p7",
        brand_type=Brand.BrandType.VEHICLE,
    )
    product = make_product(
        supplier=supplier,
        sku="SKU-P7-BROWSE",
        title="Compatibility Browser Product",
        category=category,
        condition=condition,
    )
    add_fitment(
        product=product,
        vehicle_brand=vehicle_brand,
        model="Ibiza",
        vehicle_type=Vehicle.VehicleType.CAR,
        year_start=2010,
        year_end=2017,
    )

    es_types = client.get("/es/compatibilidad/")
    es_brands = client.get("/es/compatibilidad/car/")
    es_models = client.get(f"/es/compatibilidad/car/{vehicle_brand.slug}/")
    en_types = client.get("/en/compatibility/")
    en_brands = client.get("/en/compatibility/car/")
    en_models = client.get(f"/en/compatibility/car/{vehicle_brand.slug}/")

    assert es_types.status_code == 200
    assert es_brands.status_code == 200
    assert es_models.status_code == 200
    assert en_types.status_code == 200
    assert en_brands.status_code == 200
    assert en_models.status_code == 200
    assert "catalog/compatibility_vehicle_types.html" in template_names(es_types)
    assert "catalog/compatibility_brands.html" in template_names(es_brands)
    assert "catalog/compatibility_model_year.html" in template_names(es_models)


@pytest.mark.django_db
def test_invalid_compatibility_drilldown_combinations_return_404(client) -> None:
    supplier = make_supplier("P7-404")
    category = make_category("Compatibilidad 404", "compatibilidad-404-p7")
    condition = make_condition("p7-404-new", "Nuevo 404 P7", "p7-404-new")
    vehicle_brand = make_brand(
        "Ford P7",
        "ford-veh-p7",
        brand_type=Brand.BrandType.VEHICLE,
    )
    product = make_product(
        supplier=supplier,
        sku="SKU-P7-404",
        title="Product 404",
        category=category,
        condition=condition,
    )
    add_fitment(
        product=product,
        vehicle_brand=vehicle_brand,
        model="Transit",
        vehicle_type=Vehicle.VehicleType.VAN,
    )

    assert client.get("/es/compatibilidad/plane/").status_code == 404
    assert client.get("/es/compatibilidad/car/non-existing-brand/").status_code == 404
    assert client.get(f"/es/compatibilidad/car/{vehicle_brand.slug}/").status_code == 404


@pytest.mark.django_db
def test_selected_vehicle_context_returns_only_compatible_products(client) -> None:
    supplier = make_supplier("P7-CONTEXT")
    category = make_category("Filtros", "filtros-p7")
    condition = make_condition("p7-context-new", "Nuevo Contexto", "p7-context-new")
    vehicle_brand = make_brand(
        "BMW P7",
        "bmw-veh-p7",
        brand_type=Brand.BrandType.VEHICLE,
    )

    matching = make_product(
        supplier=supplier,
        sku="SKU-P7-MATCH",
        title="Match Product",
        category=category,
        condition=condition,
    )
    add_fitment(
        product=matching,
        vehicle_brand=vehicle_brand,
        model="320d",
        vehicle_type=Vehicle.VehicleType.CAR,
        year_start=2010,
        year_end=2018,
    )

    wrong_type = make_product(
        supplier=supplier,
        sku="SKU-P7-WRONG-TYPE",
        title="Wrong Type Product",
        category=category,
        condition=condition,
    )
    add_fitment(
        product=wrong_type,
        vehicle_brand=vehicle_brand,
        model="320d",
        vehicle_type=Vehicle.VehicleType.TRUCK,
        year_start=2010,
        year_end=2018,
    )

    wrong_model = make_product(
        supplier=supplier,
        sku="SKU-P7-WRONG-MODEL",
        title="Wrong Model Product",
        category=category,
        condition=condition,
    )
    add_fitment(
        product=wrong_model,
        vehicle_brand=vehicle_brand,
        model="330d",
        vehicle_type=Vehicle.VehicleType.CAR,
        year_start=2010,
        year_end=2018,
    )

    response = client.get(
        "/es/productos/?vehicle_type=car&brand=bmw-veh-p7&model=320d&year=2015"
    )

    assert response.status_code == 200
    assert product_ids_from_response(response) == [matching.id]
    assert "Compatibilidad seleccionada" in response.content.decode()


@pytest.mark.django_db
def test_year_filter_supports_closed_and_open_ranges(client) -> None:
    supplier = make_supplier("P7-YEAR")
    category = make_category("Year Category", "year-category-p7")
    condition = make_condition("p7-year-new", "Nuevo Año", "p7-year-new")
    vehicle_brand = make_brand(
        "Renault P7",
        "renault-veh-p7",
        brand_type=Brand.BrandType.VEHICLE,
    )

    closed_range = make_product(
        supplier=supplier,
        sku="SKU-P7-CLOSED",
        title="Closed Range Product",
        category=category,
        condition=condition,
    )
    add_fitment(
        product=closed_range,
        vehicle_brand=vehicle_brand,
        model="Clio",
        year_start=2010,
        year_end=2014,
    )

    open_end = make_product(
        supplier=supplier,
        sku="SKU-P7-OPEN-END",
        title="Open End Product",
        category=category,
        condition=condition,
    )
    add_fitment(
        product=open_end,
        vehicle_brand=vehicle_brand,
        model="Clio",
        year_start=2015,
        year_end=None,
    )

    open_start = make_product(
        supplier=supplier,
        sku="SKU-P7-OPEN-START",
        title="Open Start Product",
        category=category,
        condition=condition,
    )
    add_fitment(
        product=open_start,
        vehicle_brand=vehicle_brand,
        model="Clio",
        year_start=None,
        year_end=2009,
    )

    response_2012 = client.get(
        "/es/productos/?vehicle_type=car&brand=renault-veh-p7&model=Clio&year=2012"
    )
    response_2016 = client.get(
        "/es/productos/?vehicle_type=car&brand=renault-veh-p7&model=Clio&year=2016"
    )
    response_2008 = client.get(
        "/es/productos/?vehicle_type=car&brand=renault-veh-p7&model=Clio&year=2008"
    )

    assert set(product_ids_from_response(response_2012)) == {closed_range.id}
    assert set(product_ids_from_response(response_2016)) == {open_end.id}
    assert set(product_ids_from_response(response_2008)) == {open_start.id}


@pytest.mark.django_db
def test_compatibility_results_do_not_duplicate_products(client) -> None:
    supplier = make_supplier("P7-DUP")
    category = make_category("Dup Category", "dup-category-p7")
    condition = make_condition("p7-dup-new", "Nuevo Dup P7", "p7-dup-new")
    vehicle_brand = make_brand(
        "Iveco P7",
        "iveco-veh-p7",
        brand_type=Brand.BrandType.VEHICLE,
    )

    product = make_product(
        supplier=supplier,
        sku="SKU-P7-DUP",
        title="Duplicate Guard Product",
        category=category,
        condition=condition,
    )
    add_fitment(
        product=product,
        vehicle_brand=vehicle_brand,
        model="Daily",
        vehicle_type=Vehicle.VehicleType.VAN,
        year_start=2014,
        year_end=2022,
    )
    add_fitment(
        product=product,
        vehicle_brand=vehicle_brand,
        model="Daily",
        vehicle_type=Vehicle.VehicleType.VAN,
        year_start=2010,
        year_end=None,
    )

    response = client.get(
        "/es/productos/?vehicle_type=van&brand=iveco-veh-p7&model=Daily&year=2018"
    )
    ids = product_ids_from_response(response)

    assert response.status_code == 200
    assert ids == [product.id]
    assert len(ids) == len(set(ids))


@pytest.mark.django_db
def test_compatibility_visibility_rules_match_public_catalog_visibility(client) -> None:
    supplier = make_supplier("P7-VIS")
    category = make_category("Visibility", "visibility-p7")
    condition = make_condition("p7-vis-new", "Nuevo Vis P7", "p7-vis-new")
    vehicle_brand_public = make_brand(
        "Toyota Public P7",
        "toyota-public-veh-p7",
        brand_type=Brand.BrandType.VEHICLE,
    )
    vehicle_brand_hidden = make_brand(
        "Toyota Hidden P7",
        "toyota-hidden-veh-p7",
        brand_type=Brand.BrandType.VEHICLE,
    )

    public_product = make_product(
        supplier=supplier,
        sku="SKU-P7-VIS-PUBLIC",
        title="Public Compatibility Product",
        category=category,
        condition=condition,
        publication_status=Product.PublicationStatus.PUBLISHED,
        is_active=True,
    )
    add_fitment(
        product=public_product,
        vehicle_brand=vehicle_brand_public,
        model="Corolla",
    )

    draft_product = make_product(
        supplier=supplier,
        sku="SKU-P7-VIS-DRAFT",
        title="Draft Compatibility Product",
        category=category,
        condition=condition,
        publication_status=Product.PublicationStatus.DRAFT,
        is_active=True,
    )
    add_fitment(
        product=draft_product,
        vehicle_brand=vehicle_brand_hidden,
        model="Corolla",
    )

    inactive_product = make_product(
        supplier=supplier,
        sku="SKU-P7-VIS-INACTIVE",
        title="Inactive Compatibility Product",
        category=category,
        condition=condition,
        publication_status=Product.PublicationStatus.PUBLISHED,
        is_active=False,
    )
    add_fitment(
        product=inactive_product,
        vehicle_brand=vehicle_brand_hidden,
        model="Corolla",
    )

    brand_page = client.get("/es/compatibilidad/car/")
    hidden_results = client.get(
        "/es/productos/?vehicle_type=car&brand=toyota-hidden-veh-p7&model=Corolla"
    )
    public_results = client.get(
        "/es/productos/?vehicle_type=car&brand=toyota-public-veh-p7&model=Corolla"
    )

    brand_page_content = brand_page.content.decode()
    assert brand_page.status_code == 200
    assert "Toyota Public P7" in brand_page_content
    assert "Toyota Hidden P7" not in brand_page_content
    assert product_ids_from_response(hidden_results) == []
    assert product_ids_from_response(public_results) == [public_product.id]


@pytest.mark.django_db
def test_product_detail_renders_grouped_compatibility_information(client) -> None:
    supplier = make_supplier("P7-DETAIL")
    category = make_category("Detail Compat", "detail-compat-p7")
    condition = make_condition("p7-detail-new", "Nuevo Detail P7", "p7-detail-new")
    vehicle_brand = make_brand(
        "SEAT Detail P7",
        "seat-detail-veh-p7",
        brand_type=Brand.BrandType.VEHICLE,
    )
    product = make_product(
        supplier=supplier,
        sku="SKU-P7-DETAIL",
        title="Compatibility Detail Product",
        category=category,
        condition=condition,
    )

    add_fitment(
        product=product,
        vehicle_brand=vehicle_brand,
        model="Leon",
        generation="III",
        variant="1.6 TDI",
        year_start=2014,
        year_end=2020,
        engine_code="CAYC",
        fitment_notes="Aplicación delantera",
        is_verified=True,
    )
    add_fitment(
        product=product,
        vehicle_brand=vehicle_brand,
        model="Leon",
        generation="IV",
        variant="2.0 TSI",
        year_start=2020,
        year_end=None,
    )

    response = client.get(f"/es/productos/{product.slug}/")
    content = response.content.decode()

    assert response.status_code == 200
    assert "Compatibilidad por vehículo" in content
    assert "Coche · SEAT Detail P7 Leon" in content
    assert "III 1.6 TDI" in content
    assert "IV 2.0 TSI" in content
    assert "Años: 2014-2020" in content
    assert "Motor: CAYC" in content
    assert "Compatibilidad verificada" in content
    assert "Aplicación delantera" in content
