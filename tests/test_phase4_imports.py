from __future__ import annotations

from io import BytesIO

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from openpyxl import Workbook, load_workbook

from apps.catalog.models import Brand, Category, Condition, Product
from apps.imports.admin import SupplierImportAdmin
from apps.imports.models import SupplierImport, SupplierImportRow
from apps.imports.schema import CANONICAL_IMPORT_COLUMNS, validate_template_headers
from apps.imports.services import run_supplier_import
from apps.imports.template_builder import build_supplier_import_template_xlsx
from apps.suppliers.models import Supplier
from apps.users.roles import ROLE_INTERNAL_STAFF, ROLE_RESTRICTED_SUPPLIER


def make_supplier(code: str = "SUP-IMP") -> Supplier:
    return Supplier.objects.create(
        name=f"Supplier {code}",
        slug=f"supplier-{code.lower()}",
        code=code,
    )


def make_condition(code: str = "new", name: str = "Nuevo", slug: str = "new") -> Condition:
    return Condition.objects.create(code=code, name=name, slug=slug)


def make_staff_user(django_user_model, username: str):
    return django_user_model.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="pass1234",
        is_staff=True,
    )


def build_import_file(headers: list[str], rows: list[list[object]]) -> SimpleUploadedFile:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "products_import"
    sheet.append(headers)
    for row in rows:
        sheet.append(row)

    content = BytesIO()
    workbook.save(content)
    workbook.close()
    return SimpleUploadedFile(
        "supplier_import.xlsx",
        content.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@pytest.mark.django_db
def test_valid_template_headers_are_recognized() -> None:
    header_result = validate_template_headers(list(CANONICAL_IMPORT_COLUMNS))

    assert header_result.is_valid
    assert not header_result.missing_required
    assert not header_result.duplicate_columns


@pytest.mark.django_db
def test_template_builder_generates_canonical_headers() -> None:
    file_content = build_supplier_import_template_xlsx()
    workbook = load_workbook(BytesIO(file_content), read_only=True, data_only=True)
    sheet = workbook["products_import"]
    header_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True))
    workbook.close()

    normalized_headers = tuple(
        str(value).strip().lower() for value in header_row if value is not None
    )
    assert normalized_headers == CANONICAL_IMPORT_COLUMNS


@pytest.mark.django_db
def test_import_fails_when_required_columns_are_missing(django_user_model) -> None:
    supplier = make_supplier("SUP-MISS-COL")
    user = make_staff_user(django_user_model, "import_user_missing")
    import_file = build_import_file(
        headers=["title", "condition_code", "sku"],
        rows=[["Starter Motor", "new", "SKU-1"]],
    )
    import_record = SupplierImport.objects.create(
        supplier=supplier,
        uploaded_by=user,
        original_file=import_file,
    )

    result = run_supplier_import(import_record, user)

    assert result.import_status == SupplierImport.ImportStatus.FAILED
    assert "Missing required columns" in result.processing_notes
    assert result.rows.count() == 0


@pytest.mark.django_db
def test_import_creates_product_with_blank_brand_name(django_user_model) -> None:
    supplier = make_supplier("SUP-BRAND-BLANK")
    user = make_staff_user(django_user_model, "import_user_brand_blank")
    make_condition("new", "Nuevo", "new")

    import_file = build_import_file(
        headers=list(CANONICAL_IMPORT_COLUMNS),
        rows=[
            [
                "Brand Optional Product",
                "",
                "Alternator",
                "new",
                "SKU-BRAND-BLANK-1",
                "SUP-BRAND-BLANK-1",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        ],
    )
    import_record = SupplierImport.objects.create(
        supplier=supplier,
        uploaded_by=user,
        original_file=import_file,
    )

    result = run_supplier_import(import_record, user)
    product = Product.objects.get(sku="SKU-BRAND-BLANK-1")

    assert result.import_status == SupplierImport.ImportStatus.COMPLETED
    assert product.brand is None


@pytest.mark.django_db
def test_import_records_row_level_traceability(django_user_model) -> None:
    supplier = make_supplier("SUP-TRACE")
    user = make_staff_user(django_user_model, "import_user_trace")
    make_condition("new", "Nuevo", "new")
    import_file = build_import_file(
        headers=list(CANONICAL_IMPORT_COLUMNS),
        rows=[
            [
                "Starter Motor",
                "Bosch",
                "Starter",
                "new",
                "SKU-TRACE-1",
                "SP-1",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "Brake Pad",
                "Brembo",
                "Brakes",
                "missing",
                "SKU-TRACE-2",
                "SP-2",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ],
        ],
    )
    import_record = SupplierImport.objects.create(
        supplier=supplier,
        uploaded_by=user,
        original_file=import_file,
    )

    result = run_supplier_import(import_record, user)

    assert result.import_status == SupplierImport.ImportStatus.COMPLETED_WITH_ERRORS
    assert result.total_rows == 2
    assert result.successful_rows == 1
    assert result.failed_rows == 1

    success_row = SupplierImportRow.objects.get(supplier_import=result, row_number=2)
    error_row = SupplierImportRow.objects.get(supplier_import=result, row_number=3)
    assert success_row.processing_status == SupplierImportRow.ProcessingStatus.SUCCESS
    assert success_row.linked_product is not None
    assert success_row.raw_payload["sku"] == "SKU-TRACE-1"
    assert error_row.processing_status == SupplierImportRow.ProcessingStatus.ERROR
    assert "Unknown condition_code" in error_row.error_message


@pytest.mark.django_db
def test_import_updates_existing_product_by_sku(django_user_model) -> None:
    supplier = make_supplier("SUP-SKU-UPD")
    user = make_staff_user(django_user_model, "import_user_sku")
    brand = Brand.objects.create(name="Brand One", slug="brand-one")
    category = Category.objects.create(name="Category One", slug="category-one")
    condition = make_condition("new", "Nuevo", "new")
    product = Product.objects.create(
        supplier=supplier,
        supplier_product_code="SUP-SKU-UPD-1",
        sku="SKU-UPD-1",
        slug="sku-upd-1",
        title="Old title",
        brand=brand,
        category=category,
        condition=condition,
    )
    import_file = build_import_file(
        headers=list(CANONICAL_IMPORT_COLUMNS),
        rows=[
            [
                "Updated title",
                "Brand One",
                "Category One",
                "new",
                "SKU-UPD-1",
                "SUP-SKU-UPD-1",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        ],
    )
    import_record = SupplierImport.objects.create(
        supplier=supplier,
        uploaded_by=user,
        original_file=import_file,
    )

    result = run_supplier_import(import_record, user)
    product.refresh_from_db()

    assert result.import_status == SupplierImport.ImportStatus.COMPLETED
    assert product.title == "Updated title"
    assert Product.objects.filter(supplier=supplier).count() == 1


@pytest.mark.django_db
def test_import_preserves_existing_brand_when_brand_name_is_blank(django_user_model) -> None:
    supplier = make_supplier("SUP-BRAND-PRES")
    user = make_staff_user(django_user_model, "import_user_brand_preserve")
    brand = Brand.objects.create(name="Preserve Brand", slug="preserve-brand")
    category = Category.objects.create(name="Starter", slug="starter-pres")
    condition = make_condition("pres-new", "Nuevo Pres", "pres-new")
    product = Product.objects.create(
        supplier=supplier,
        supplier_product_code="SUP-BRAND-PRES-1",
        sku="SKU-BRAND-PRES-1",
        slug="sku-brand-pres-1",
        title="Old Brand Product",
        brand=brand,
        category=category,
        condition=condition,
    )

    import_file = build_import_file(
        headers=list(CANONICAL_IMPORT_COLUMNS),
        rows=[
            [
                "Updated Brand Product",
                "",
                "Starter",
                "pres-new",
                "SKU-BRAND-PRES-1",
                "SUP-BRAND-PRES-1",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        ],
    )
    import_record = SupplierImport.objects.create(
        supplier=supplier,
        uploaded_by=user,
        original_file=import_file,
    )

    result = run_supplier_import(import_record, user)
    product.refresh_from_db()

    assert result.import_status == SupplierImport.ImportStatus.COMPLETED
    assert product.title == "Updated Brand Product"
    assert product.brand_id == brand.id


@pytest.mark.django_db
def test_import_updates_by_supplier_product_code_when_sku_missing(django_user_model) -> None:
    supplier = make_supplier("SUP-SUPCODE-UPD")
    user = make_staff_user(django_user_model, "import_user_supcode")
    brand = Brand.objects.create(name="Valeo", slug="valeo")
    category = Category.objects.create(name="Alternator", slug="alternator")
    condition = make_condition("used", "Usado", "used")
    product = Product.objects.create(
        supplier=supplier,
        supplier_product_code="SUPCODE-42",
        sku="SKU-SUPCODE-42",
        slug="sku-supcode-42",
        title="Old title",
        brand=brand,
        category=category,
        condition=condition,
    )
    import_file = build_import_file(
        headers=list(CANONICAL_IMPORT_COLUMNS),
        rows=[
            [
                "Updated by supplier code",
                "Valeo",
                "Alternator",
                "used",
                "",
                "SUPCODE-42",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        ],
    )
    import_record = SupplierImport.objects.create(
        supplier=supplier,
        uploaded_by=user,
        original_file=import_file,
    )

    result = run_supplier_import(import_record, user)
    product.refresh_from_db()

    assert result.import_status == SupplierImport.ImportStatus.COMPLETED
    assert product.title == "Updated by supplier code"


@pytest.mark.django_db
def test_import_errors_when_sku_and_supplier_code_conflict(django_user_model) -> None:
    supplier = make_supplier("SUP-CONFLICT")
    user = make_staff_user(django_user_model, "import_user_conflict")
    brand = Brand.objects.create(name="Brand C", slug="brand-c")
    category = Category.objects.create(name="Category C", slug="category-c")
    condition = make_condition("new", "Nuevo", "new")
    Product.objects.create(
        supplier=supplier,
        supplier_product_code="SUP-CODE-1",
        sku="SKU-C-1",
        slug="sku-c-1",
        title="P1",
        brand=brand,
        category=category,
        condition=condition,
    )
    Product.objects.create(
        supplier=supplier,
        supplier_product_code="SUP-CODE-2",
        sku="SKU-C-2",
        slug="sku-c-2",
        title="P2",
        brand=brand,
        category=category,
        condition=condition,
    )
    import_file = build_import_file(
        headers=list(CANONICAL_IMPORT_COLUMNS),
        rows=[
            [
                "Conflict row",
                "Brand C",
                "Category C",
                "new",
                "SKU-C-1",
                "SUP-CODE-2",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        ],
    )
    import_record = SupplierImport.objects.create(
        supplier=supplier,
        uploaded_by=user,
        original_file=import_file,
    )

    result = run_supplier_import(import_record, user)
    row = result.rows.get(row_number=2)

    assert result.import_status == SupplierImport.ImportStatus.COMPLETED_WITH_ERRORS
    assert result.failed_rows == 1
    assert "different products" in row.error_message


@pytest.mark.django_db
def test_import_avoids_duplicate_brand_and_category_from_case_variants(django_user_model) -> None:
    supplier = make_supplier("SUP-NODUP")
    user = make_staff_user(django_user_model, "import_user_nodup")
    Brand.objects.create(name="Bosch", slug="bosch")
    Category.objects.create(name="Alternator", slug="alternator")
    make_condition("new", "Nuevo", "new")
    import_file = build_import_file(
        headers=list(CANONICAL_IMPORT_COLUMNS),
        rows=[
            [
                "Case variant row",
                "bosch",
                "ALTERNATOR",
                "new",
                "SKU-NODUP-1",
                "SUP-NODUP-1",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        ],
    )
    import_record = SupplierImport.objects.create(
        supplier=supplier,
        uploaded_by=user,
        original_file=import_file,
    )

    result = run_supplier_import(import_record, user)

    assert result.import_status == SupplierImport.ImportStatus.COMPLETED
    assert Brand.objects.filter(name__iexact="bosch").count() == 1
    assert Category.objects.filter(name__iexact="alternator").count() == 1


@pytest.mark.django_db
def test_unknown_extra_columns_are_ignored_with_warning(django_user_model) -> None:
    supplier = make_supplier("SUP-WARN")
    user = make_staff_user(django_user_model, "import_user_warn")
    make_condition("new", "Nuevo", "new")
    headers = list(CANONICAL_IMPORT_COLUMNS) + ["unexpected_column"]
    import_file = build_import_file(
        headers=headers,
        rows=[
            [
                "Warn row",
                "Brand Warn",
                "Category Warn",
                "new",
                "SKU-WARN-1",
                "SUP-WARN-1",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "ignored value",
            ]
        ],
    )
    import_record = SupplierImport.objects.create(
        supplier=supplier,
        uploaded_by=user,
        original_file=import_file,
    )

    result = run_supplier_import(import_record, user)

    assert result.import_status == SupplierImport.ImportStatus.COMPLETED_WITH_ERRORS
    assert "Unknown columns ignored" in result.processing_notes
    assert Product.objects.filter(sku="SKU-WARN-1").exists()


@pytest.mark.django_db
def test_supplier_import_admin_processing_action_authorization(django_user_model) -> None:
    admin_instance = SupplierImportAdmin(SupplierImport, AdminSite())
    internal_user = make_staff_user(django_user_model, "internal_processor")
    internal_user.groups.add(Group.objects.get(name=ROLE_INTERNAL_STAFF))
    restricted_user = make_staff_user(django_user_model, "restricted_processor")
    restricted_user.groups.add(Group.objects.get(name=ROLE_RESTRICTED_SUPPLIER))

    internal_request = RequestFactory().get("/admin/imports/supplierimport/")
    internal_request.user = internal_user
    restricted_request = RequestFactory().get("/admin/imports/supplierimport/")
    restricted_request.user = restricted_user

    internal_actions = admin_instance.get_actions(internal_request)
    restricted_actions = admin_instance.get_actions(restricted_request)

    assert "process_selected_imports" in internal_actions
    assert "process_selected_imports" not in restricted_actions
