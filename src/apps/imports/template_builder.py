from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from .schema import CANONICAL_IMPORT_COLUMNS, OPTIONAL_IMPORT_COLUMNS, REQUIRED_IMPORT_COLUMNS


def build_supplier_import_template_xlsx() -> bytes:
    workbook = Workbook()
    data_sheet = workbook.active
    data_sheet.title = "products_import"
    data_sheet.append(list(CANONICAL_IMPORT_COLUMNS))
    data_sheet.freeze_panes = "A2"
    data_sheet.auto_filter.ref = f"A1:{get_column_letter(len(CANONICAL_IMPORT_COLUMNS))}1"

    for index, column_name in enumerate(CANONICAL_IMPORT_COLUMNS, start=1):
        data_sheet.column_dimensions[get_column_letter(index)].width = max(16, len(column_name) + 2)

    instructions_sheet = workbook.create_sheet("instructions")
    instructions_sheet.append(["Column", "Required", "Notes"])
    for column_name in REQUIRED_IMPORT_COLUMNS:
        instructions_sheet.append([column_name, "yes", "Canonical required column"])
    for column_name in OPTIONAL_IMPORT_COLUMNS:
        instructions_sheet.append([column_name, "no", "Canonical optional column"])

    instructions_sheet.append([])
    instructions_sheet.append(
        ["Rule", "", "At least one of sku or supplier_product_code is required per row"]
    )
    instructions_sheet.append(["Rule", "", "If creating a new product, sku is required"])
    instructions_sheet.append(
        ["Rule", "", "Unknown extra columns are ignored and logged as warning"]
    )
    instructions_sheet.append(
        ["Rule", "", "condition_code must already exist in canonical conditions (not auto-created)"]
    )

    content = BytesIO()
    workbook.save(content)
    workbook.close()
    return content.getvalue()
