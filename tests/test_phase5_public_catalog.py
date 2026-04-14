from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import resolve
from django.utils import timezone, translation

from apps.catalog.models import Brand, Category, Condition, Product
from apps.catalog.views import CategoryListView, ProductDetailView, ProductListView
from apps.pages.views import AboutView, ContactView, HomeView, LegalView
from apps.suppliers.models import Supplier
from apps.vehicles.models import ProductVehicleFitment, Vehicle


def make_supplier(code: str) -> Supplier:
    return Supplier.objects.create(
        name=f"Supplier {code}",
        slug=f"supplier-{code.lower()}",
        code=code,
        is_active=True,
    )


def make_brand(name: str, slug: str, *, is_active: bool = True) -> Brand:
    return Brand.objects.create(
        name=name,
        slug=slug,
        brand_type=Brand.BrandType.PARTS,
        is_active=is_active,
    )


def make_category(name: str, slug: str, *, is_active: bool = True) -> Category:
    return Category.objects.create(name=name, slug=slug, is_active=is_active)


def make_condition(code: str, name: str, slug: str, *, is_active: bool = True) -> Condition:
    return Condition.objects.create(code=code, name=name, slug=slug, is_active=is_active)


def make_product(
    *,
    supplier: Supplier,
    brand: Brand | None,
    category: Category,
    condition: Condition,
    sku: str,
    title: str,
    publication_status: str = Product.PublicationStatus.PUBLISHED,
    is_active: bool = True,
    featured: bool = False,
    price_visibility_mode: str = Product.PriceVisibilityMode.HIDDEN,
    last_known_price: Decimal | None = None,
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
        price_visibility_mode=price_visibility_mode,
        last_known_price=last_known_price,
        currency="EUR",
        is_active=is_active,
        featured=featured,
    )


def template_names(response) -> set[str]:
    return {template.name for template in response.templates if template.name}


@pytest.mark.django_db
def test_root_redirects_to_spanish_home(client) -> None:
    response = client.get("/")

    assert response.status_code == 302
    assert response.url == "/es/"


@pytest.mark.django_db
def test_public_base_pages_return_200_in_es_and_en(client) -> None:
    urls = [
        "/es/",
        "/en/",
        "/es/categorias/",
        "/en/categories/",
        "/es/productos/",
        "/en/products/",
        "/es/nosotros/",
        "/en/about/",
        "/es/contacto/",
        "/en/contact/",
        "/es/legal/",
        "/en/legal/",
    ]

    for url in urls:
        response = client.get(url)
        assert response.status_code == 200, f"{url} should return 200"


@pytest.mark.django_db
def test_view_resolution_and_templates_for_public_pages(client) -> None:
    with translation.override("es"):
        assert resolve("/es/").func.view_class is HomeView
        assert resolve("/es/categorias/").func.view_class is CategoryListView
        assert resolve("/es/productos/").func.view_class is ProductListView
        assert resolve("/es/nosotros/").func.view_class is AboutView
        assert resolve("/es/contacto/").func.view_class is ContactView
        assert resolve("/es/legal/").func.view_class is LegalView

    home_response = client.get("/es/")
    category_response = client.get("/es/categorias/")
    product_response = client.get("/es/productos/")
    about_response = client.get("/es/nosotros/")
    contact_response = client.get("/es/contacto/")
    legal_response = client.get("/es/legal/")

    assert "pages/home.html" in template_names(home_response)
    assert "catalog/category_list.html" in template_names(category_response)
    assert "catalog/product_list.html" in template_names(product_response)
    assert "pages/about.html" in template_names(about_response)
    assert "pages/contact.html" in template_names(contact_response)
    assert "pages/legal.html" in template_names(legal_response)


@pytest.mark.django_db
def test_public_category_and_product_views_use_only_public_products(client) -> None:
    supplier = make_supplier("SUP-P5")
    brand = make_brand("Bosch P5", "bosch-p5")
    category_ok = make_category("Alternators P5", "alternators-p5")
    category_draft = make_category("Draft Category P5", "draft-category-p5")
    condition = make_condition("new-p5", "Nuevo P5", "new-p5")

    public_product = make_product(
        supplier=supplier,
        brand=brand,
        category=category_ok,
        condition=condition,
        sku="SKU-PUB-1",
        title="Public Product",
        publication_status=Product.PublicationStatus.PUBLISHED,
    )
    make_product(
        supplier=supplier,
        brand=brand,
        category=category_draft,
        condition=condition,
        sku="SKU-DR-1",
        title="Draft Product",
        publication_status=Product.PublicationStatus.DRAFT,
    )
    make_product(
        supplier=supplier,
        brand=brand,
        category=category_ok,
        condition=condition,
        sku="SKU-INACT-1",
        title="Inactive Product",
        publication_status=Product.PublicationStatus.PUBLISHED,
        is_active=False,
    )

    category_response = client.get("/es/categorias/")
    product_response = client.get("/es/productos/")

    categories = list(category_response.context["categories"])
    products = list(product_response.context["products"])

    assert [category.slug for category in categories] == [category_ok.slug]
    assert [product.id for product in products] == [public_product.id]


@pytest.mark.django_db
def test_public_product_list_includes_published_products_with_null_brand(client) -> None:
    supplier = make_supplier("SUP-P5-NOBRAND")
    category = make_category("No Brand Category", "no-brand-category")
    condition = make_condition("nobrand-new", "Nuevo No Brand", "nobrand-new")
    product = make_product(
        supplier=supplier,
        brand=None,
        category=category,
        condition=condition,
        sku="SKU-P5-NOBRAND",
        title="No Brand Public Product",
    )

    response = client.get("/es/productos/")
    detail_response = client.get(f"/es/productos/{product.slug}/")
    products = list(response.context["products"])
    content = response.content.decode()
    detail_content = detail_response.content.decode()

    assert response.status_code == 200
    assert detail_response.status_code == 200
    assert [item.id for item in products] == [product.id]
    assert "Sin marca especificada" in content
    assert "Sin marca especificada" in detail_content


@pytest.mark.django_db
def test_category_and_product_detail_routes_work_in_both_languages(client) -> None:
    supplier = make_supplier("SUP-P5-ROUTES")
    brand = make_brand("Valeo P5", "valeo-p5")
    category = make_category("Starters P5", "starters-p5")
    condition = make_condition("used-p5", "Usado P5", "used-p5")
    product = make_product(
        supplier=supplier,
        brand=brand,
        category=category,
        condition=condition,
        sku="SKU-P5-ROUTE",
        title="Route Product",
    )

    es_category = client.get(f"/es/categorias/{category.slug}/")
    en_category = client.get(f"/en/categories/{category.slug}/")
    es_product = client.get(f"/es/productos/{product.slug}/")
    en_product = client.get(f"/en/products/{product.slug}/")

    assert es_category.status_code == 200
    assert en_category.status_code == 200
    assert es_product.status_code == 200
    assert en_product.status_code == 200
    with translation.override("es"):
        assert resolve(f"/es/productos/{product.slug}/").func.view_class is ProductDetailView


@pytest.mark.django_db
def test_non_public_product_detail_returns_404(client) -> None:
    supplier = make_supplier("SUP-P5-404")
    brand = make_brand("Brand P5 404", "brand-p5-404")
    category = make_category("Category P5 404", "category-p5-404")
    condition = make_condition("new-p5-404", "Nuevo P5 404", "new-p5-404")
    draft_product = make_product(
        supplier=supplier,
        brand=brand,
        category=category,
        condition=condition,
        sku="SKU-P5-404",
        title="Draft Only Product",
        publication_status=Product.PublicationStatus.DRAFT,
    )

    response = client.get(f"/es/productos/{draft_product.slug}/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_price_visibility_messages_follow_business_rules(client) -> None:
    supplier = make_supplier("SUP-P5-PRICE")
    brand = make_brand("Brand P5 Price", "brand-p5-price")
    category = make_category("Category P5 Price", "category-p5-price")
    condition = make_condition("new-p5-price", "Nuevo P5 Price", "new-p5-price")

    visible_product = make_product(
        supplier=supplier,
        brand=brand,
        category=category,
        condition=condition,
        sku="SKU-P5-VIS",
        title="Visible Price Product",
        price_visibility_mode=Product.PriceVisibilityMode.VISIBLE_INFO,
        last_known_price=Decimal("149.90"),
    )
    hidden_product = make_product(
        supplier=supplier,
        brand=brand,
        category=category,
        condition=condition,
        sku="SKU-P5-HID",
        title="Hidden Price Product",
        price_visibility_mode=Product.PriceVisibilityMode.HIDDEN,
        last_known_price=None,
    )

    visible_response = client.get(f"/es/productos/{visible_product.slug}/")
    hidden_response = client.get(f"/es/productos/{hidden_product.slug}/")

    visible_content = visible_response.content.decode()
    hidden_content = hidden_response.content.decode()

    assert "Último precio conocido" in visible_content
    assert "Solicitar precio y plazo" in visible_content
    assert "Añadir a carrito de solicitudes" in visible_content
    assert "Solicitar precio y plazo" in hidden_content
    assert "Añadir a carrito de solicitudes" in hidden_content
    assert "Este producto se gestiona bajo consulta previa." in hidden_content


@pytest.mark.django_db
def test_product_detail_renders_fitment_applications(client) -> None:
    supplier = make_supplier("SUP-P5-FIT")
    product_brand = make_brand("Brand P5 Fit", "brand-p5-fit")
    vehicle_brand = make_brand("Seat P5 Fit", "seat-p5-fit")
    category = make_category("Fit Category", "fit-category")
    condition = make_condition("fit-new", "Nuevo Fit", "fit-new")
    product = make_product(
        supplier=supplier,
        brand=product_brand,
        category=category,
        condition=condition,
        sku="SKU-P5-FIT",
        title="Fitment Product",
    )
    vehicle = Vehicle.objects.create(
        vehicle_type=Vehicle.VehicleType.CAR,
        brand=vehicle_brand,
        model="Leon",
        generation="III",
        variant="1.6 TDI",
        year_start=2014,
        year_end=2020,
        engine_code="CAYC",
        is_active=True,
    )
    ProductVehicleFitment.objects.create(
        product=product,
        vehicle=vehicle,
        fitment_notes="Montaje delantero",
        source=ProductVehicleFitment.FitmentSource.MANUAL,
        is_verified=True,
    )

    response = client.get(f"/es/productos/{product.slug}/")
    content = response.content.decode()

    assert response.status_code == 200
    assert "Compatibilidad por vehículo" in content
    assert "Coche · Seat P5 Fit Leon" in content
    assert "III 1.6 TDI" in content
    assert "Años: 2014-2020" in content
    assert "Motor: CAYC" in content
    assert "Compatibilidad verificada" in content
    assert "Montaje delantero" in content


@pytest.mark.django_db
def test_contact_page_receives_product_hint_from_catalog_cta(client) -> None:
    response = client.get("/es/contacto/?product=SKU-TEST-123")

    assert response.status_code == 200
    assert response.context["product_hint"] == "SKU-TEST-123"
    assert "SKU-TEST-123" in response.content.decode()


@pytest.mark.django_db
def test_english_home_uses_translated_public_chrome(client) -> None:
    response = client.get("/en/")
    content = response.content.decode()

    assert response.status_code == 200
    assert "Main navigation" in content
    assert "Explore categories" in content
