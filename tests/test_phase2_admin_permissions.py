import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.test import RequestFactory

from apps.catalog.admin import ProductAdmin
from apps.catalog.models import Brand, Category, Condition, Product
from apps.imports.admin import SupplierImportAdmin
from apps.imports.models import SupplierImport
from apps.suppliers.models import Supplier, SupplierUserAssignment
from apps.users.roles import (
    ROLE_ADMINISTRATOR,
    ROLE_INTERNAL_STAFF,
    ROLE_REGISTERED_CUSTOMER,
    ROLE_RESTRICTED_SUPPLIER,
)
from apps.vehicles.models import ProductVehicleFitment, Vehicle


def make_supplier(code: str) -> Supplier:
    return Supplier.objects.create(
        name=f"Supplier {code}",
        slug=f"supplier-{code.lower()}",
        code=code,
    )


def make_brand(name: str, slug: str) -> Brand:
    return Brand.objects.create(name=name, slug=slug, brand_type=Brand.BrandType.PARTS)


def make_category(name: str, slug: str) -> Category:
    return Category.objects.create(name=name, slug=slug)


def make_condition(code: str, name: str, slug: str) -> Condition:
    return Condition.objects.create(code=code, name=name, slug=slug)


def make_product(
    supplier: Supplier,
    brand: Brand,
    category: Category,
    condition: Condition,
    sku: str,
    status: str = Product.PublicationStatus.DRAFT,
) -> Product:
    product = Product.objects.create(
        supplier=supplier,
        supplier_product_code=f"{supplier.code}-{sku}",
        sku=sku,
        slug=f"product-{sku.lower()}",
        title=f"Product {sku}",
        brand=brand,
        category=category,
        condition=condition,
        publication_status=status,
    )
    return product


def make_staff_user(django_user_model, username: str):
    return django_user_model.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="pass1234",
        is_staff=True,
    )


def build_request(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


@pytest.mark.django_db
def test_role_groups_and_publish_permission_are_seeded() -> None:
    group_names = set(Group.objects.values_list("name", flat=True))
    expected_names = {
        ROLE_ADMINISTRATOR,
        ROLE_INTERNAL_STAFF,
        ROLE_RESTRICTED_SUPPLIER,
        ROLE_REGISTERED_CUSTOMER,
    }
    assert expected_names.issubset(group_names)

    internal_staff = Group.objects.get(name=ROLE_INTERNAL_STAFF)
    restricted_supplier = Group.objects.get(name=ROLE_RESTRICTED_SUPPLIER)

    assert internal_staff.permissions.filter(
        content_type__app_label="catalog",
        codename="can_publish_product",
    ).exists()
    assert not restricted_supplier.permissions.filter(
        content_type__app_label="catalog",
        codename="can_publish_product",
    ).exists()


@pytest.mark.django_db
def test_supplier_user_assignment_is_unique_per_supplier_user_pair(django_user_model) -> None:
    supplier = make_supplier("SUP-A")
    user = make_staff_user(django_user_model, "supplier_editor")
    SupplierUserAssignment.objects.create(supplier=supplier, user=user, is_active=True)

    with pytest.raises(IntegrityError), transaction.atomic():
        SupplierUserAssignment.objects.create(supplier=supplier, user=user, is_active=True)


@pytest.mark.django_db
def test_product_admin_queryset_is_supplier_scoped_for_restricted_users(django_user_model) -> None:
    supplier_a = make_supplier("SUP-A")
    supplier_b = make_supplier("SUP-B")
    brand = make_brand("Bosch", "bosch")
    category = make_category("Alternator", "alternator")
    condition = make_condition("new", "Nuevo", "new")
    own_product = make_product(supplier_a, brand, category, condition, "SKU-A")
    other_product = make_product(supplier_b, brand, category, condition, "SKU-B")

    supplier_user = make_staff_user(django_user_model, "restricted_supplier")
    supplier_user.groups.add(Group.objects.get(name=ROLE_RESTRICTED_SUPPLIER))
    SupplierUserAssignment.objects.create(supplier=supplier_a, user=supplier_user, is_active=True)

    product_admin = ProductAdmin(Product, AdminSite())
    request = build_request(supplier_user)
    queryset = product_admin.get_queryset(request)

    assert list(queryset.values_list("id", flat=True)) == [own_product.id]
    assert product_admin.has_view_permission(request, own_product)
    assert not product_admin.has_view_permission(request, other_product)


@pytest.mark.django_db
def test_restricted_supplier_cannot_publish_and_cannot_edit_non_draft(django_user_model) -> None:
    supplier = make_supplier("SUP-A")
    brand = make_brand("Valeo", "valeo")
    category = make_category("Starter", "starter")
    condition = make_condition("used", "Usado", "used")
    draft_product = make_product(supplier, brand, category, condition, "SKU-DRAFT")
    review_product = make_product(
        supplier,
        brand,
        category,
        condition,
        "SKU-REVIEW",
        status=Product.PublicationStatus.REVIEW,
    )

    supplier_user = make_staff_user(django_user_model, "restricted_editor")
    supplier_user.groups.add(Group.objects.get(name=ROLE_RESTRICTED_SUPPLIER))
    SupplierUserAssignment.objects.create(supplier=supplier, user=supplier_user, is_active=True)

    product_admin = ProductAdmin(Product, AdminSite())
    request = build_request(supplier_user)

    assert product_admin.has_change_permission(request, draft_product)
    assert not product_admin.has_change_permission(request, review_product)

    draft_product.publication_status = Product.PublicationStatus.PUBLISHED
    with pytest.raises(PermissionDenied):
        product_admin.save_model(request, draft_product, form=None, change=True)


@pytest.mark.django_db
def test_internal_staff_can_publish_and_published_at_is_set(django_user_model) -> None:
    supplier = make_supplier("SUP-PUB")
    brand = make_brand("Delphi", "delphi")
    category = make_category("Ignition", "ignition")
    condition = make_condition("reman", "Reacondicionado", "reman")
    product = make_product(supplier, brand, category, condition, "SKU-PUBLISH")

    staff_user = make_staff_user(django_user_model, "internal_staff_user")
    staff_user.groups.add(Group.objects.get(name=ROLE_INTERNAL_STAFF))

    product_admin = ProductAdmin(Product, AdminSite())
    request = build_request(staff_user)
    product.publication_status = Product.PublicationStatus.PUBLISHED
    product.published_at = None

    product_admin.save_model(request, product, form=None, change=True)
    product.refresh_from_db()

    assert product.publication_status == Product.PublicationStatus.PUBLISHED
    assert product.published_at is not None


@pytest.mark.django_db
def test_product_admin_includes_fitment_inline() -> None:
    product_admin = ProductAdmin(Product, AdminSite())

    inline_models = {inline.model for inline in product_admin.inlines}
    assert ProductVehicleFitment in inline_models


@pytest.mark.django_db
def test_restricted_supplier_fitment_inline_forces_source_and_verification(
    django_user_model,
) -> None:
    supplier = make_supplier("SUP-FIT")
    brand = make_brand("Fit Brand", "fit-brand")
    category = make_category("Fit Category", "fit-category")
    condition = make_condition("fit-cond", "Fit Condition", "fit-condition")
    product = make_product(supplier, brand, category, condition, "SKU-FIT")
    vehicle = Vehicle.objects.create(
        vehicle_type=Vehicle.VehicleType.CAR,
        brand=brand,
        model="A3",
        generation="8P",
        year_start=2006,
        year_end=2012,
    )

    supplier_user = make_staff_user(django_user_model, "restricted_fitment_editor")
    supplier_user.groups.add(Group.objects.get(name=ROLE_RESTRICTED_SUPPLIER))
    SupplierUserAssignment.objects.create(supplier=supplier, user=supplier_user, is_active=True)

    product_admin = ProductAdmin(Product, AdminSite())
    request = build_request(supplier_user)

    fitment = ProductVehicleFitment(
        product=product,
        vehicle=vehicle,
        source=ProductVehicleFitment.FitmentSource.MANUAL,
        is_verified=True,
    )

    class DummyFormset:
        model = ProductVehicleFitment
        deleted_objects = []
        save_m2m_called = False

        def save(self, commit=True):
            assert not commit
            return [fitment]

        def save_m2m(self):
            self.save_m2m_called = True

    formset = DummyFormset()
    product_admin.save_formset(request, form=None, formset=formset, change=True)
    fitment.refresh_from_db()

    assert fitment.source == ProductVehicleFitment.FitmentSource.SUPPLIER
    assert fitment.is_verified is False
    assert formset.save_m2m_called


@pytest.mark.django_db
def test_supplier_import_admin_is_scoped_and_blocks_cross_supplier_edits(django_user_model) -> None:
    supplier_a = make_supplier("SUP-A")
    supplier_b = make_supplier("SUP-B")

    restricted_user = make_staff_user(django_user_model, "restricted_importer")
    restricted_user.groups.add(Group.objects.get(name=ROLE_RESTRICTED_SUPPLIER))
    SupplierUserAssignment.objects.create(supplier=supplier_a, user=restricted_user, is_active=True)

    own_import = SupplierImport.objects.create(supplier=supplier_a, uploaded_by=restricted_user)
    other_import = SupplierImport.objects.create(supplier=supplier_b, uploaded_by=restricted_user)

    import_admin = SupplierImportAdmin(SupplierImport, AdminSite())
    request = build_request(restricted_user)

    queryset = import_admin.get_queryset(request)
    assert list(queryset.values_list("id", flat=True)) == [own_import.id]
    assert import_admin.has_add_permission(request)
    assert import_admin.has_view_permission(request, own_import)
    assert not import_admin.has_view_permission(request, other_import)
    assert not import_admin.has_change_permission(request, own_import)

    cross_supplier_import = SupplierImport(supplier=supplier_b)
    with pytest.raises(PermissionDenied):
        import_admin.save_model(request, cross_supplier_import, form=None, change=False)
