import json

import pytest

from apps.catalog.models import Category, Condition, PartNumber, Product
from apps.imports.rg_pipeline import (
    import_rg_clean_dataset,
    parse_product_html,
    parse_vehicle_use_text,
)

PRODUCT_HTML_FIXTURE = """
<html>
  <head><title>Starter Denso (new - take off) TE438000-4913</title></head>
  <body class="catalog-product-view">
    <h1 class="page-title">
      <span class="base">Starter Denso (new - take off) TE438000-4913</span>
    </h1>
    <table class="data table additional-attributes" id="product-attribute-specs-table">
      <tbody>
        <tr><th class="col label" scope="row">SKU</th><td class="col data">TE438000-4913</td></tr>
        <tr>
          <th class="col label" scope="row">Description</th>
          <td class="col data">Starter Denso (new - take off)</td>
        </tr>
        <tr><th class="col label" scope="row">Matchcode</th><td class="col data">8687064</td></tr>
        <tr><th class="col label" scope="row">EAN</th><td class="col data">4047026407532</td></tr>
        <tr>
          <th class="col label" scope="row">Vehicle use</th>
          <td class="col data">BMW 7 (G11, G12) M 760 Li xDrive, Bj. 2016-2022</td>
        </tr>
        <tr>
          <th class="col label" scope="row">comparison numbers</th>
          <td class="col data">BMW Nr.: 8687064, 12418687064, TE438000-4913</td>
        </tr>
        <tr><th class="col label" scope="row">custom code</th><td class="col data">XX-9988</td></tr>
      </tbody>
    </table>
  </body>
</html>
"""


@pytest.mark.django_db
def test_parse_product_html_extracts_expected_fields_and_classifies_codes() -> None:
    record, errors = parse_product_html(
        html=PRODUCT_HTML_FIXTURE,
        source_url="https://www.rg-gmbh.de/en/anlasser-denso-neu-take-off-te438000-4913.html",
        category_slug="starter",
    )

    assert not errors
    assert record is not None
    assert record["supplier_product_code"] == "TE438000-4913"
    assert record["sku"] == "RG-TE438000-4913"
    assert record["condition_code"] == "take_off"

    part_numbers = {(row["number_raw"], row["part_number_type"]) for row in record["part_numbers"]}
    assert ("4047026407532", "EAN") in part_numbers
    assert ("8687064", "XREF") in part_numbers
    assert ("12418687064", "XREF") in part_numbers
    assert ("XX-9988", "UNK") in part_numbers

    # Supplier SKU must not be duplicated as part number.
    assert ("TE438000-4913", "XREF") not in part_numbers

    assert len(record["fitments_confident"]) == 1
    fitment = record["fitments_confident"][0]
    assert fitment["brand_name"] == "BMW"
    assert fitment["model"] == "7"
    assert fitment["year_start"] == 2016
    assert fitment["year_end"] == 2022


@pytest.mark.django_db
def test_parse_vehicle_use_splits_concatenated_brand_segments() -> None:
    raw = "RENAULT Clio IV 1.5 dCi, Bj. 2012-RENAULT Kangoo 1.5 dCi, Bj. 2015-"

    confident, unparsed = parse_vehicle_use_text(raw)

    assert len(confident) == 2
    assert not unparsed
    assert confident[0]["brand_name"] == "Renault"
    assert confident[0]["year_start"] == 2012
    assert confident[1]["brand_name"] == "Renault"
    assert confident[1]["year_start"] == 2015


@pytest.mark.django_db
def test_import_rg_clean_dataset_upserts_by_supplier_product_code(tmp_path) -> None:
    clean_path = tmp_path / "rg_products_clean.json"
    report_path = tmp_path / "rg_import_report.json"

    records = [
        {
            "source_url": "https://www.rg-gmbh.de/en/anlasser-denso-neu-take-off-te438000-4913.html",
            "category_slug": "starter",
            "supplier_product_code": "TE438000-4913",
            "sku": "RG-TE438000-4913",
            "title": "Starter Denso (new - take off) TE438000-4913",
            "condition_code": "take_off",
            "part_numbers": [
                {
                    "number_raw": "4047026407532",
                    "part_number_type": "EAN",
                    "source_field": "ean",
                },
                {
                    "number_raw": "12418687064",
                    "part_number_type": "XREF",
                    "source_field": "comparison_numbers",
                },
            ],
            "vehicle_use_raw": "BMW 7 (G11, G12) M 760 Li xDrive, Bj. 2016-2022",
            "fitments_confident": [
                {
                    "brand_name": "BMW",
                    "model": "7",
                    "generation": "G11, G12",
                    "variant": "M 760 Li xDrive",
                    "year_start": 2016,
                    "year_end": 2022,
                    "source_text": "BMW 7 (G11, G12) M 760 Li xDrive, Bj. 2016-2022",
                }
            ],
            "fitments_unparsed": [],
            "raw_attributes": {
                "Description": "Starter Denso (new - take off)",
            },
        }
    ]
    clean_path.write_text(json.dumps(records), encoding="utf-8")

    summary_first = import_rg_clean_dataset(input_file=clean_path, report_file=report_path)

    assert summary_first["processed"] == 1
    assert summary_first["created_products"] == 1
    assert summary_first["updated_products"] == 0
    assert summary_first["created_part_numbers"] == 2
    assert summary_first["created_fitments"] == 1

    product = Product.objects.get(supplier_product_code="TE438000-4913")
    assert product.sku == "RG-TE438000-4913"
    assert product.publication_status == Product.PublicationStatus.DRAFT
    assert product.published_at is None

    category = Category.objects.get(slug="starter")
    assert product.category_id == category.id
    assert PartNumber.objects.filter(product=product).count() == 2

    records[0]["title"] = "Starter Denso UPDATED"
    clean_path.write_text(json.dumps(records), encoding="utf-8")

    summary_second = import_rg_clean_dataset(input_file=clean_path, report_file=report_path)

    assert summary_second["created_products"] == 0
    assert summary_second["updated_products"] == 1
    assert Product.objects.filter(supplier_product_code="TE438000-4913").count() == 1

    product.refresh_from_db()
    assert product.title == "Starter Denso UPDATED"


@pytest.mark.django_db
def test_import_rg_clean_dataset_reuses_existing_condition_case_insensitive(tmp_path) -> None:
    Condition.objects.create(
        code="NEW",
        name="New",
        slug="new-existing",
        is_active=True,
    )

    clean_path = tmp_path / "rg_products_clean.json"
    records = [
        {
            "source_url": "https://www.rg-gmbh.de/en/anlasser-denso-neu-take-off-te438000-4913.html",
            "category_slug": "starter",
            "supplier_product_code": "TE438000-4913",
            "sku": "RG-TE438000-4913",
            "title": "Starter Denso (new - take off) TE438000-4913",
            "condition_code": "new",
            "part_numbers": [],
            "vehicle_use_raw": "",
            "fitments_confident": [],
            "fitments_unparsed": [],
            "raw_attributes": {"Description": "Starter Denso"},
        }
    ]
    clean_path.write_text(json.dumps(records), encoding="utf-8")

    summary = import_rg_clean_dataset(input_file=clean_path)

    assert summary["processed"] == 1
    assert summary["created_products"] == 1
    assert Condition.objects.filter(name="New").count() == 1
    product = Product.objects.get(supplier_product_code="TE438000-4913")
    assert product.condition.name == "New"
