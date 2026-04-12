from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from apps.catalog.models import Brand, Category, Condition, Product

from .models import SupplierImport, SupplierImportRow
from .schema import CANONICAL_IMPORT_COLUMNS, REQUIRED_IMPORT_COLUMNS, validate_template_headers

PRICE_MODE_VALUES = {
    Product.PriceVisibilityMode.HIDDEN,
    Product.PriceVisibilityMode.VISIBLE_INFO,
}
TRUE_VALUES = {"1", "true", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "no", "n", "off"}


class ImportProcessingError(Exception):
    pass


@dataclass
class ImportProcessingSummary:
    total_rows: int = 0
    successful_rows: int = 0
    failed_rows: int = 0
    skipped_rows: int = 0
    auto_created_brands: set[str] | None = None
    auto_created_categories: set[str] | None = None

    def __post_init__(self) -> None:
        if self.auto_created_brands is None:
            self.auto_created_brands = set()
        if self.auto_created_categories is None:
            self.auto_created_categories = set()


def run_supplier_import(
    import_record: SupplierImport,
    requested_by: AbstractBaseUser,
) -> SupplierImport:
    import_record = SupplierImport.objects.select_related("supplier").get(pk=import_record.pk)
    import_record.import_status = SupplierImport.ImportStatus.PROCESSING
    import_record.started_at = timezone.now()
    import_record.finished_at = None
    import_record.total_rows = 0
    import_record.successful_rows = 0
    import_record.failed_rows = 0
    import_record.processing_notes = ""
    import_record.save(
        update_fields=[
            "import_status",
            "started_at",
            "finished_at",
            "total_rows",
            "successful_rows",
            "failed_rows",
            "processing_notes",
            "updated_at",
        ]
    )
    import_record.rows.all().delete()

    workbook = None
    try:
        workbook, worksheet, normalized_headers = _load_worksheet(import_record)
        header_result = validate_template_headers(normalized_headers)
        if header_result.duplicate_columns:
            duplicates = ", ".join(header_result.duplicate_columns)
            raise ImportProcessingError(f"Duplicate columns are not allowed: {duplicates}.")
        if header_result.missing_required:
            missing = ", ".join(header_result.missing_required)
            raise ImportProcessingError(f"Missing required columns: {missing}.")
    except ImportProcessingError as exc:
        if workbook is not None:
            workbook.close()
        return _mark_import_failed(import_record, str(exc))

    summary = ImportProcessingSummary()
    import_warnings: list[str] = []
    if header_result.unknown_columns:
        unknown = ", ".join(header_result.unknown_columns)
        import_warnings.append(f"Unknown columns ignored: {unknown}.")

    try:
        row_headers = normalized_headers
        for row_number, row_values in enumerate(
            worksheet.iter_rows(min_row=2, values_only=True),
            start=2,
        ):
            summary.total_rows += 1
            raw_payload = _build_raw_payload(row_headers, row_values)
            if _is_empty_payload(raw_payload):
                SupplierImportRow.objects.create(
                    supplier_import=import_record,
                    row_number=row_number,
                    raw_payload=raw_payload,
                    processing_status=SupplierImportRow.ProcessingStatus.SKIPPED,
                    error_message="Empty row skipped.",
                )
                summary.skipped_rows += 1
                continue

            try:
                with transaction.atomic():
                    product, row_messages, created_brand, created_category = _process_data_row(
                        import_record=import_record,
                        raw_payload=raw_payload,
                    )
                    SupplierImportRow.objects.create(
                        supplier_import=import_record,
                        row_number=row_number,
                        raw_payload=raw_payload,
                        processing_status=SupplierImportRow.ProcessingStatus.SUCCESS,
                        linked_product=product,
                        error_message="; ".join(row_messages),
                    )
                summary.successful_rows += 1
                if created_brand:
                    summary.auto_created_brands.add(created_brand)
                if created_category:
                    summary.auto_created_categories.add(created_category)
            except ImportProcessingError as exc:
                SupplierImportRow.objects.create(
                    supplier_import=import_record,
                    row_number=row_number,
                    raw_payload=raw_payload,
                    processing_status=SupplierImportRow.ProcessingStatus.ERROR,
                    error_message=str(exc),
                )
                summary.failed_rows += 1
            except IntegrityError as exc:
                SupplierImportRow.objects.create(
                    supplier_import=import_record,
                    row_number=row_number,
                    raw_payload=raw_payload,
                    processing_status=SupplierImportRow.ProcessingStatus.ERROR,
                    error_message=f"Database integrity error: {exc}",
                )
                summary.failed_rows += 1
    except Exception as exc:
        return _mark_import_failed(import_record, f"Unexpected processing error: {exc}")
    finally:
        if workbook is not None:
            workbook.close()

    return _finalize_import(import_record, summary, import_warnings)


def _load_worksheet(import_record: SupplierImport):
    if not import_record.original_file:
        raise ImportProcessingError("Missing file: upload a .xlsx file before processing.")
    file_name = import_record.original_file.name.lower()
    if not file_name.endswith(".xlsx"):
        raise ImportProcessingError("Only .xlsx files are supported in v1.")

    try:
        import_record.original_file.open("rb")
        workbook = load_workbook(import_record.original_file, read_only=True, data_only=True)
    except (InvalidFileException, ValueError) as exc:
        raise ImportProcessingError(f"Invalid XLSX file: {exc}") from exc

    worksheet = workbook.active
    header_row = next(worksheet.iter_rows(min_row=1, max_row=1, values_only=True), None)
    if not header_row:
        raise ImportProcessingError("The worksheet is empty. Missing header row.")
    normalized_headers = [
        str(value).strip().lower() if value is not None else ""
        for value in header_row
    ]
    if not any(normalized_headers):
        raise ImportProcessingError("The header row is empty.")
    return workbook, worksheet, normalized_headers


def _mark_import_failed(import_record: SupplierImport, notes: str) -> SupplierImport:
    import_record.import_status = SupplierImport.ImportStatus.FAILED
    import_record.finished_at = timezone.now()
    import_record.processing_notes = notes
    import_record.save(
        update_fields=["import_status", "finished_at", "processing_notes", "updated_at"]
    )
    return import_record


def _finalize_import(
    import_record: SupplierImport,
    summary: ImportProcessingSummary,
    warnings: list[str],
) -> SupplierImport:
    notes: list[str] = []
    notes.extend(warnings)
    if summary.auto_created_brands:
        created_brands = ", ".join(sorted(summary.auto_created_brands))
        notes.append(f"Auto-created brands: {created_brands}.")
    if summary.auto_created_categories:
        created_categories = ", ".join(sorted(summary.auto_created_categories))
        notes.append(f"Auto-created categories: {created_categories}.")
    if summary.skipped_rows:
        notes.append(f"Skipped empty rows: {summary.skipped_rows}.")

    if summary.total_rows == 0:
        import_record.import_status = SupplierImport.ImportStatus.FAILED
        notes.append("No data rows found to process.")
    elif summary.failed_rows == 0 and not warnings:
        import_record.import_status = SupplierImport.ImportStatus.COMPLETED
    else:
        import_record.import_status = SupplierImport.ImportStatus.COMPLETED_WITH_ERRORS

    import_record.total_rows = summary.total_rows
    import_record.successful_rows = summary.successful_rows
    import_record.failed_rows = summary.failed_rows
    import_record.finished_at = timezone.now()
    import_record.processing_notes = "\n".join(notes)
    import_record.save(
        update_fields=[
            "import_status",
            "total_rows",
            "successful_rows",
            "failed_rows",
            "finished_at",
            "processing_notes",
            "updated_at",
        ]
    )
    return import_record


def _process_data_row(
    import_record: SupplierImport,
    raw_payload: dict[str, Any],
) -> tuple[Product, list[str], str | None, str | None]:
    title = _clean_text(raw_payload.get("title"))
    brand_name = _clean_text(raw_payload.get("brand_name"))
    category_name = _clean_text(raw_payload.get("category_name"))
    condition_code = _clean_text(raw_payload.get("condition_code"))
    sku = _clean_text(raw_payload.get("sku"))
    supplier_product_code = _clean_text(raw_payload.get("supplier_product_code"))

    row_messages: list[str] = []
    if not title:
        raise ImportProcessingError("Missing required value: title.")
    if not category_name:
        raise ImportProcessingError("Missing required value: category_name.")
    if not condition_code:
        raise ImportProcessingError("Missing required value: condition_code.")
    if not sku and not supplier_product_code:
        raise ImportProcessingError("Each row must include sku or supplier_product_code.")

    target_product = _match_existing_product(
        import_record=import_record,
        sku=sku,
        supplier_product_code=supplier_product_code,
    )

    if target_product is None and not sku:
        raise ImportProcessingError(
            "sku is required to create a new product when no existing match is found."
        )

    brand = None
    brand_created = False
    if brand_name:
        brand, brand_created = _get_or_create_brand(brand_name)
    category, category_created = _get_or_create_category(category_name)
    condition = Condition.objects.filter(code__iexact=condition_code).first()
    if not condition:
        raise ImportProcessingError(
            f"Unknown condition_code '{condition_code}'. Create it first in canonical conditions."
        )

    price_visibility_mode = _parse_price_visibility_mode(raw_payload.get("price_visibility_mode"))
    last_known_price = _parse_decimal(
        raw_payload.get("last_known_price"),
        field_name="last_known_price",
    )
    is_active = _parse_bool(raw_payload.get("is_active"), field_name="is_active")
    featured = _parse_bool(raw_payload.get("featured"), field_name="featured")
    currency = _clean_text(raw_payload.get("currency")).upper()
    unit_of_sale = _clean_text(raw_payload.get("unit_of_sale"))
    short_description = _clean_text(raw_payload.get("short_description"))
    long_description = _clean_text(raw_payload.get("long_description"))

    if currency and len(currency) != 3:
        raise ImportProcessingError("currency must be a 3-letter code.")

    if target_product is None:
        product = Product(
            supplier=import_record.supplier,
            sku=sku,
            supplier_product_code=supplier_product_code or None,
            title=title,
            short_description=short_description,
            long_description=long_description,
            brand=brand,
            category=category,
            condition=condition,
            price_visibility_mode=price_visibility_mode or Product.PriceVisibilityMode.HIDDEN,
            last_known_price=last_known_price,
            currency=currency or "EUR",
            unit_of_sale=unit_of_sale or "unit",
            is_active=True if is_active is None else is_active,
            featured=False if featured is None else featured,
        )
        product.save()
    else:
        product = target_product
        product.title = title
        if brand_name:
            product.brand = brand
        product.category = category
        product.condition = condition
        product.supplier = import_record.supplier

        if sku and sku != product.sku:
            conflict = Product.objects.exclude(pk=product.pk).filter(sku=sku).exists()
            if conflict:
                raise ImportProcessingError(f"sku '{sku}' already exists in another product.")
            product.sku = sku

        if supplier_product_code:
            product.supplier_product_code = supplier_product_code
        if short_description:
            product.short_description = short_description
        if long_description:
            product.long_description = long_description
        if price_visibility_mode:
            product.price_visibility_mode = price_visibility_mode
        if last_known_price is not None:
            product.last_known_price = last_known_price
        if currency:
            product.currency = currency
        if unit_of_sale:
            product.unit_of_sale = unit_of_sale
        if is_active is not None:
            product.is_active = is_active
        if featured is not None:
            product.featured = featured

        product.save()

    created_brand_name = brand.name if brand and brand_created else None
    created_category_name = category.name if category_created else None
    if created_brand_name:
        row_messages.append(f"Auto-created brand '{created_brand_name}'")
    if created_category_name:
        row_messages.append(f"Auto-created category '{created_category_name}'")
    return product, row_messages, created_brand_name, created_category_name


def _match_existing_product(
    import_record: SupplierImport,
    sku: str,
    supplier_product_code: str,
) -> Product | None:
    sku_match = Product.objects.filter(sku=sku).first() if sku else None
    supplier_match = (
        Product.objects.filter(
            supplier=import_record.supplier,
            supplier_product_code=supplier_product_code,
        ).first()
        if supplier_product_code
        else None
    )

    if sku_match and sku_match.supplier_id != import_record.supplier_id:
        raise ImportProcessingError(
            f"sku '{sku}' belongs to supplier '{sku_match.supplier.code}', "
            f"not '{import_record.supplier.code}'."
        )
    if sku_match and supplier_match and sku_match.pk != supplier_match.pk:
        raise ImportProcessingError("sku and supplier_product_code point to different products.")

    matched_product = sku_match or supplier_match
    if matched_product and matched_product.supplier_id != import_record.supplier_id:
        raise ImportProcessingError(
            "Matched product belongs to another supplier and cannot be updated in this import."
        )
    return matched_product


def _get_or_create_brand(name: str) -> tuple[Brand, bool]:
    normalized_name = _normalize_entity_name(name)
    brand = Brand.objects.filter(name__iexact=normalized_name).first()
    if brand:
        return brand, False
    brand = Brand.objects.create(
        name=normalized_name,
        slug=_build_unique_slug(Brand, normalized_name, max_length=140, fallback_prefix="brand"),
        brand_type=Brand.BrandType.PARTS,
    )
    return brand, True


def _get_or_create_category(name: str) -> tuple[Category, bool]:
    normalized_name = _normalize_entity_name(name)
    category = Category.objects.filter(parent__isnull=True, name__iexact=normalized_name).first()
    if category:
        return category, False
    category = Category.objects.create(
        name=normalized_name,
        slug=_build_unique_slug(
            Category,
            normalized_name,
            max_length=140,
            fallback_prefix="category",
        ),
        parent=None,
    )
    return category, True


def _normalize_entity_name(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ImportProcessingError("Entity names cannot be empty after normalization.")
    return cleaned


def _build_unique_slug(model_class, value: str, *, max_length: int, fallback_prefix: str) -> str:
    base_slug = slugify(value).strip("-") or fallback_prefix
    base_slug = base_slug[:max_length].rstrip("-") or fallback_prefix
    candidate = base_slug
    suffix = 2
    while model_class.objects.filter(slug=candidate).exists():
        suffix_text = f"-{suffix}"
        truncated = base_slug[: max_length - len(suffix_text)].rstrip("-")
        candidate = f"{truncated}{suffix_text}"
        suffix += 1
    return candidate


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_price_visibility_mode(value: Any) -> str | None:
    text_value = _clean_text(value).lower()
    if not text_value:
        return None
    if text_value not in PRICE_MODE_VALUES:
        allowed = ", ".join(sorted(PRICE_MODE_VALUES))
        raise ImportProcessingError(
            f"Invalid price_visibility_mode '{text_value}'. Allowed values: {allowed}."
        )
    return text_value


def _parse_decimal(value: Any, *, field_name: str) -> Decimal | None:
    text_value = _clean_text(value)
    if not text_value:
        return None
    try:
        return Decimal(text_value)
    except (InvalidOperation, ValueError) as exc:
        raise ImportProcessingError(
            f"Invalid decimal value for {field_name}: '{text_value}'."
        ) from exc


def _parse_bool(value: Any, *, field_name: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value

    text_value = _clean_text(value).lower()
    if not text_value:
        return None
    if text_value in TRUE_VALUES:
        return True
    if text_value in FALSE_VALUES:
        return False
    raise ImportProcessingError(f"Invalid boolean value for {field_name}: '{value}'.")


def _serialize_cell_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return str(value)


def _build_raw_payload(headers: list[str], row_values: tuple[Any, ...]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for index, header in enumerate(headers):
        if not header:
            continue
        cell_value = row_values[index] if index < len(row_values) else None
        payload[header] = _serialize_cell_value(cell_value)
    for required_column in REQUIRED_IMPORT_COLUMNS:
        payload.setdefault(required_column, None)
    for known_column in CANONICAL_IMPORT_COLUMNS:
        payload.setdefault(known_column, None)
    return payload


def _is_empty_payload(raw_payload: dict[str, Any]) -> bool:
    for value in raw_payload.values():
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        return False
    return True
