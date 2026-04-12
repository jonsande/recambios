from __future__ import annotations

from dataclasses import dataclass

REQUIRED_IMPORT_COLUMNS: tuple[str, ...] = (
    "title",
    "category_name",
    "condition_code",
)

OPTIONAL_IMPORT_COLUMNS: tuple[str, ...] = (
    "brand_name",
    "sku",
    "supplier_product_code",
    "short_description",
    "long_description",
    "price_visibility_mode",
    "last_known_price",
    "currency",
    "unit_of_sale",
    "is_active",
    "featured",
)

CANONICAL_IMPORT_COLUMNS: tuple[str, ...] = (
    "title",
    "brand_name",
    "category_name",
    "condition_code",
    "sku",
    "supplier_product_code",
    "short_description",
    "long_description",
    "price_visibility_mode",
    "last_known_price",
    "currency",
    "unit_of_sale",
    "is_active",
    "featured",
)
KNOWN_IMPORT_COLUMNS: set[str] = set(CANONICAL_IMPORT_COLUMNS)


@dataclass(frozen=True)
class HeaderValidationResult:
    column_index_map: dict[str, int]
    missing_required: tuple[str, ...]
    duplicate_columns: tuple[str, ...]
    unknown_columns: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.missing_required and not self.duplicate_columns


def normalize_header(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def validate_template_headers(headers: list[object]) -> HeaderValidationResult:
    normalized_headers = [normalize_header(value) for value in headers]
    column_index_map: dict[str, int] = {}
    duplicate_columns: list[str] = []
    unknown_columns: list[str] = []

    for index, header in enumerate(normalized_headers):
        if not header:
            continue
        if header in column_index_map:
            duplicate_columns.append(header)
            continue
        column_index_map[header] = index
        if header not in KNOWN_IMPORT_COLUMNS:
            unknown_columns.append(header)

    missing_required = tuple(
        column for column in REQUIRED_IMPORT_COLUMNS if column not in column_index_map
    )
    return HeaderValidationResult(
        column_index_map=column_index_map,
        missing_required=missing_required,
        duplicate_columns=tuple(sorted(set(duplicate_columns))),
        unknown_columns=tuple(sorted(unknown_columns)),
    )
