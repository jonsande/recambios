from __future__ import annotations

import json
import math
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import Brand, Category, Condition, PartNumber, PartNumberType, Product
from apps.suppliers.models import Supplier
from apps.vehicles.models import ProductVehicleFitment, Vehicle

RG_BASE_URL = "https://www.rg-gmbh.de"
RG_EN_BASE_URL = f"{RG_BASE_URL}/en"
DEFAULT_OUTPUT_DIR = Path("data/rg")
CLEAN_DATASET_FILENAME = "rg_products_clean.json"
REPORT_FILENAME = "rg_import_report.json"

DEFAULT_CATEGORY_SLUGS: tuple[str, ...] = (
    "starter",
    "injectors",
    "alternators",
    "high-pressure-pumps-injection-pumps",
    "transmission",
    "flywheels-clutches",
    "turbocharger",
    "spark-plugs",
    "ignition-coils",
    "air-conditioning-compressors",
    "sensors-lambda-sensors",
    "thermostats",
    "wheel-bearings",
    "shock-absorbers-springs-axles",
    "air-flow-meter",
    "engines",
    "special-items",
    "headlights",
)

KNOWN_VEHICLE_BRANDS: tuple[str, ...] = (
    "MERCEDES BENZ",
    "MERCEDES-BENZ",
    "VOLKSWAGEN",
    "CITROEN",
    "PEUGEOT",
    "RENAULT",
    "PORSCHE",
    "TOYOTA",
    "NISSAN",
    "SUZUKI",
    "HYUNDAI",
    "CHEVROLET",
    "LAND ROVER",
    "RANGE ROVER",
    "ALFA ROMEO",
    "MITSUBISHI",
    "DACIA",
    "SKODA",
    "SEAT",
    "HONDA",
    "MAZDA",
    "LEXUS",
    "JAGUAR",
    "FIAT",
    "FORD",
    "OPEL",
    "AUDI",
    "BMW",
    "VW",
    "KIA",
)

ROMAN_NUMERAL_RE = re.compile(r"^(?:I|II|III|IV|V|VI|VII|VIII|IX|X)$")
CATALOG_COUNT_RE = re.compile(r"Items\s+\d+-\d+\s+of\s+(\d+)", re.IGNORECASE)
PART_NUMBER_CANDIDATE_RE = re.compile(r"\b[A-Z0-9][A-Z0-9.-]{2,}\b")
YEAR_MARKER_RE = re.compile(r"Bj\.\s*(\d{4})(?:\s*-\s*(\d{4})?)?", re.IGNORECASE)
SPACES_RE = re.compile(r"\s+")


@dataclass
class CategorySnapshot:
    slug: str
    url: str
    name: str
    product_count: int


@dataclass
class FetchResult:
    url: str
    status_code: int
    html: str


def _clean_spaces(value: str) -> str:
    return SPACES_RE.sub(" ", value or "").strip()


def _normalize_code(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", (value or "").upper())


def _json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_slug(value: str, fallback: str = "item") -> str:
    slug = slugify(value)
    return slug or fallback


def _fetch_html(url: str, timeout: float = 20.0) -> FetchResult:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:  # nosec B310
            status = int(getattr(response, "status", 200) or 200)
            html = response.read().decode("utf-8", errors="replace")
            return FetchResult(url=url, status_code=status, html=html)
    except HTTPError as exc:
        html = ""
        try:
            html = exc.read().decode("utf-8", errors="replace")
        except Exception:
            html = ""
        return FetchResult(url=url, status_code=int(exc.code), html=html)
    except URLError:
        return FetchResult(url=url, status_code=0, html="")


def _parse_category_snapshot(category_slug: str, html: str, url: str) -> CategorySnapshot:
    soup = BeautifulSoup(html, "html.parser")
    title = _clean_spaces(soup.title.get_text(" ", strip=True) if soup.title else category_slug)
    match = CATALOG_COUNT_RE.search(soup.get_text(" ", strip=True))
    product_count = int(match.group(1)) if match else 0
    return CategorySnapshot(
        slug=category_slug,
        url=url,
        name=title,
        product_count=product_count,
    )


def _is_product_page(html: str) -> bool:
    if not html:
        return False
    soup = BeautifulSoup(html, "html.parser")
    body = soup.find("body")
    classes = body.get("class", []) if body else []
    if any("catalog-product-view" == cls for cls in classes):
        return True
    title = soup.title.get_text(" ", strip=True).lower() if soup.title else ""
    return "seite nicht gefunden" not in title and bool(
        soup.select_one("#product-attribute-specs-table")
    )


def _extract_product_links(category_html: str) -> list[str]:
    soup = BeautifulSoup(category_html, "html.parser")
    links: list[str] = []
    for anchor in soup.select("a.product-item-link[href]"):
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        if not href.startswith(f"{RG_EN_BASE_URL}/"):
            continue
        if any(href.endswith(f"/{slug}.html") for slug in DEFAULT_CATEGORY_SLUGS):
            continue
        links.append(href)

    deduped: list[str] = []
    seen: set[str] = set()
    for link in links:
        if link in seen:
            continue
        seen.add(link)
        deduped.append(link)
    return deduped


def _parse_total_count(category_html: str) -> int:
    category_text = BeautifulSoup(category_html, "html.parser").get_text(" ", strip=True)
    match = CATALOG_COUNT_RE.search(category_text)
    if not match:
        return 0
    return int(match.group(1))


def _collect_links_for_category(
    category_slug: str,
    *,
    limit_hint: int,
    delay_seconds: float,
) -> tuple[CategorySnapshot | None, list[str], list[str]]:
    errors: list[str] = []
    category_url = f"{RG_EN_BASE_URL}/{category_slug}.html"
    first_result = _fetch_html(category_url)

    if first_result.status_code != 200:
        errors.append(f"Category fetch failed ({first_result.status_code}): {category_url}")
        return None, [], errors

    snapshot = _parse_category_snapshot(category_slug, first_result.html, category_url)
    links = _extract_product_links(first_result.html)

    total_count = snapshot.product_count or len(links)
    if total_count <= len(links) or len(links) >= limit_hint:
        return snapshot, links, errors

    per_page = max(len(links), 1)
    total_pages = int(math.ceil(total_count / per_page))
    page = 2

    while len(links) < limit_hint and page <= total_pages:
        page_url = f"{category_url}?{urlencode({'p': page})}"
        time.sleep(max(delay_seconds, 0.0))
        result = _fetch_html(page_url)
        if result.status_code != 200:
            errors.append(f"Category page fetch failed ({result.status_code}): {page_url}")
            break
        page_links = _extract_product_links(result.html)
        if not page_links:
            break
        links.extend(page_links)
        page += 1

    deduped: list[str] = []
    seen: set[str] = set()
    for link in links:
        if link in seen:
            continue
        seen.add(link)
        deduped.append(link)

    return snapshot, deduped, errors


def _extract_attributes(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("#product-attribute-specs-table")
    attributes: dict[str, str] = {}
    if not table:
        return attributes

    for row in table.select("tr"):
        label_el = row.select_one("th")
        value_el = row.select_one("td")
        if not label_el or not value_el:
            continue
        label = _clean_spaces(label_el.get_text(" ", strip=True))
        value = _clean_spaces(value_el.get_text(" ", strip=True))
        if label:
            attributes[label] = value
    return attributes


def _infer_condition_code(*values: str) -> str:
    haystack = " ".join(values).lower()
    if "new - take off" in haystack or "take off" in haystack or "kurz gelaufen" in haystack:
        return "take_off"
    if "rebuilt" in haystack or "refurbished" in haystack or "instandgesetzt" in haystack:
        return "refurbished"
    if "used" in haystack or "gebraucht" in haystack:
        return "used"
    if "exchange" in haystack:
        return "exchange"
    if "ii. choice" in haystack or "second quality" in haystack:
        return "second_quality"
    return "new"


def _extract_ean_codes(text: str) -> list[str]:
    if not text:
        return []
    return re.findall(r"\b\d{8,14}\b", text)


def _tokenize_codes(text: str) -> list[str]:
    if not text:
        return []

    normalized = text.replace("Nr.:", ":").replace("Nr.", ":")
    normalized = normalized.replace("No.", ":").replace("no.", ":")
    normalized = normalized.replace("|", ",").replace(";", ",")

    chunks: list[str] = []
    for piece in normalized.split(","):
        part = piece.strip()
        if not part:
            continue
        if ":" in part:
            left, right = part.split(":", 1)
            if 1 <= len(left.strip()) <= 40:
                part = right.strip()
        chunks.extend(segment.strip() for segment in part.split("/") if segment.strip())

    candidates: list[str] = []
    for chunk in chunks:
        upper_chunk = chunk.upper()
        for match in PART_NUMBER_CANDIDATE_RE.findall(upper_chunk):
            candidate = match.strip(".-")
            if len(candidate) < 3:
                continue
            if not re.search(r"\d", candidate):
                continue
            if re.fullmatch(r"\d{4}", candidate) and 1900 <= int(candidate) <= 2099:
                continue
            candidates.append(candidate)

    return candidates


def _extract_part_numbers(
    attributes: dict[str, str],
    *,
    supplier_product_code: str,
) -> list[dict[str, str]]:
    lower_map = {key.lower(): value for key, value in attributes.items()}
    supplier_norm = _normalize_code(supplier_product_code)

    collected: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add_codes(raw_codes: list[str], type_code: str, source_field: str) -> None:
        for raw_code in raw_codes:
            code = _clean_spaces(raw_code).upper()
            if not code:
                continue
            normalized = _normalize_code(code)
            if not normalized:
                continue
            if normalized == supplier_norm:
                continue
            key = (normalized, type_code)
            if key in seen:
                continue
            seen.add(key)
            collected.append(
                {
                    "number_raw": code,
                    "part_number_type": type_code,
                    "source_field": source_field,
                }
            )

    add_codes(_tokenize_codes(lower_map.get("matchcode", "")), "XREF", "matchcode")
    add_codes(
        _tokenize_codes(lower_map.get("comparison numbers", "")),
        "XREF",
        "comparison_numbers",
    )
    add_codes(_extract_ean_codes(lower_map.get("ean", "")), "EAN", "ean")

    ignored_fields = {
        "sku",
        "description",
        "matchcode",
        "comparison numbers",
        "ean",
        "unit",
        "weight",
        "delivery time",
        "vehicle use",
        "packaging",
    }
    for label, value in lower_map.items():
        if label in ignored_fields:
            continue
        if not any(marker in label for marker in ("code", "number", "nr")):
            continue
        add_codes(_tokenize_codes(value), "UNK", label)

    return collected


def _split_vehicle_segments(raw: str) -> list[str]:
    if not raw:
        return []

    text = _clean_spaces(raw)
    text = re.sub(r"(\d{4})-(?=[A-Za-z]{2,})", r"\1-; ", text)
    parts = [segment.strip(" ,") for segment in text.split(";") if segment.strip(" ,")]

    brand_pattern = "|".join(
        sorted((re.escape(brand) for brand in KNOWN_VEHICLE_BRANDS), key=len, reverse=True)
    )
    if not brand_pattern:
        return parts

    result: list[str] = []
    for part in parts:
        match_positions = [
            match.start()
            for match in re.finditer(
                rf"\b(?:{brand_pattern})\b",
                part,
                flags=re.IGNORECASE,
            )
        ]
        if len(match_positions) <= 1:
            result.append(part)
            continue
        for index, start in enumerate(match_positions):
            end = match_positions[index + 1] if index + 1 < len(match_positions) else len(part)
            chunk = part[start:end].strip(" ,")
            if chunk:
                result.append(chunk)
    return result


def _pick_brand(segment: str) -> tuple[str | None, str]:
    cleaned = _clean_spaces(segment)
    upper = cleaned.upper()
    canonical_map = {
        "MERCEDES BENZ": "Mercedes-Benz",
        "MERCEDES-BENZ": "Mercedes-Benz",
        "VW": "Volkswagen",
        "BMW": "BMW",
        "AUDI": "Audi",
        "OPEL": "Opel",
        "FIAT": "Fiat",
        "FORD": "Ford",
        "SEAT": "Seat",
        "SKODA": "Skoda",
        "KIA": "Kia",
    }

    for brand in sorted(KNOWN_VEHICLE_BRANDS, key=len, reverse=True):
        if upper.startswith(f"{brand} ") or upper == brand:
            rest = cleaned[len(brand) :].strip(" ,")
            canonical = canonical_map.get(brand, brand.title())
            return canonical, rest
    return None, cleaned


def _split_model_variant(model_blob: str) -> tuple[str, str]:
    cleaned = _clean_spaces(model_blob)
    if not cleaned:
        return "", ""

    tokens = cleaned.split()
    model_tokens = [tokens[0]]
    if len(tokens) > 1:
        next_token = tokens[1]
        first_has_letters = bool(re.search(r"[A-Za-z]", tokens[0]))
        if ROMAN_NUMERAL_RE.match(next_token) or (
            first_has_letters and re.fullmatch(r"[A-Z]\d?", next_token)
        ):
            model_tokens.append(next_token)

    model = " ".join(model_tokens)
    variant = " ".join(tokens[len(model_tokens) :])
    return model, variant


def parse_vehicle_use_text(raw: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    segments = _split_vehicle_segments(raw)
    confident: list[dict[str, Any]] = []
    unparsed: list[dict[str, Any]] = []

    for segment in segments:
        year_match = YEAR_MARKER_RE.search(segment)
        if not year_match:
            unparsed.append({"source_text": segment, "reason": "missing_year_marker"})
            continue

        year_start = int(year_match.group(1))
        year_end = int(year_match.group(2)) if year_match.group(2) else None

        prefix = _clean_spaces(segment[: year_match.start()]).strip(" ,")
        brand_name, remainder = _pick_brand(prefix)
        if not brand_name:
            unparsed.append({"source_text": segment, "reason": "missing_brand"})
            continue

        generation = ""
        generation_match = re.search(r"\(([^)]*)\)", remainder)
        if generation_match:
            generation = _clean_spaces(generation_match.group(1))

        remainder_no_paren = _clean_spaces(re.sub(r"\([^)]*\)", "", remainder)).strip(" ,")
        model, variant = _split_model_variant(remainder_no_paren)

        if not model or not year_start:
            unparsed.append({"source_text": segment, "reason": "low_confidence_model_or_year"})
            continue

        confident.append(
            {
                "brand_name": brand_name,
                "model": model,
                "generation": generation,
                "variant": variant,
                "year_start": year_start,
                "year_end": year_end,
                "source_text": segment,
            }
        )

    return confident, unparsed


def parse_product_html(
    *,
    html: str,
    source_url: str,
    category_slug: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []

    if not _is_product_page(html):
        return None, [f"Not a product page: {source_url}"]

    soup = BeautifulSoup(html, "html.parser")
    title_el = soup.select_one("h1.page-title span.base")
    title = _clean_spaces(title_el.get_text(" ", strip=True) if title_el else "")
    if not title and soup.title:
        title = _clean_spaces(soup.title.get_text(" ", strip=True))

    attributes = _extract_attributes(html)
    lower_attributes = {key.lower(): value for key, value in attributes.items()}

    supplier_product_code = _clean_spaces(lower_attributes.get("sku", ""))
    if not supplier_product_code:
        errors.append("Missing SKU in More Information table")
        return None, errors

    description = _clean_spaces(lower_attributes.get("description", ""))
    if not title:
        title = description or supplier_product_code

    condition_code = _infer_condition_code(title, description)
    vehicle_use_raw = _clean_spaces(lower_attributes.get("vehicle use", ""))
    fitments_confident, fitments_unparsed = parse_vehicle_use_text(vehicle_use_raw)
    part_numbers = _extract_part_numbers(
        attributes,
        supplier_product_code=supplier_product_code,
    )

    record: dict[str, Any] = {
        "source_url": source_url,
        "category_slug": category_slug,
        "supplier_product_code": supplier_product_code,
        "sku": f"RG-{supplier_product_code}",
        "title": title,
        "condition_code": condition_code,
        "part_numbers": part_numbers,
        "vehicle_use_raw": vehicle_use_raw,
        "fitments_confident": fitments_confident,
        "fitments_unparsed": fitments_unparsed,
        "raw_attributes": attributes,
    }

    return record, errors


def scrape_rg_products_sample(
    *,
    limit: int = 30,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    delay_seconds: float = 0.05,
    top_categories: int = 6,
    category_slugs: tuple[str, ...] = DEFAULT_CATEGORY_SLUGS,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    raw_html_dir = output_dir / "raw_html"
    raw_html_dir.mkdir(parents=True, exist_ok=True)

    category_rows: list[dict[str, Any]] = []
    errors: list[str] = []
    links_by_category: dict[str, list[str]] = {}

    for category_slug in category_slugs:
        snapshot, links, category_errors = _collect_links_for_category(
            category_slug,
            limit_hint=max(limit, 10),
            delay_seconds=delay_seconds,
        )
        errors.extend(category_errors)
        if snapshot is None:
            continue
        category_rows.append(
            {
                "slug": snapshot.slug,
                "name": snapshot.name,
                "product_count": snapshot.product_count,
                "url": snapshot.url,
            }
        )
        links_by_category[category_slug] = links
        time.sleep(max(delay_seconds, 0.0))

    selected_categories = sorted(
        category_rows,
        key=lambda row: row["product_count"],
        reverse=True,
    )[: max(top_categories, 1)]

    selected_links: list[tuple[str, str]] = []
    seen_links: set[str] = set()

    for category in selected_categories:
        links = links_by_category.get(category["slug"], [])
        for link in links:
            if link in seen_links:
                continue
            seen_links.add(link)
            selected_links.append((category["slug"], link))
            if len(selected_links) >= limit:
                break
        if len(selected_links) >= limit:
            break

    clean_rows: list[dict[str, Any]] = []
    code_stats: Counter[str] = Counter()
    fitment_stats = Counter({"confident": 0, "unparsed": 0})

    for category_slug, product_url in selected_links:
        result = _fetch_html(product_url)
        if result.status_code != 200:
            errors.append(f"Product fetch failed ({result.status_code}): {product_url}")
            continue

        file_slug = Path(urlparse(product_url).path).name.replace(".html", "")
        html_path = raw_html_dir / f"{_safe_slug(file_slug, fallback='product')}.html"
        html_path.write_text(result.html, encoding="utf-8")

        parsed_row, row_errors = parse_product_html(
            html=result.html,
            source_url=product_url,
            category_slug=category_slug,
        )

        if row_errors:
            errors.extend(row_errors)
        if not parsed_row:
            continue

        for part_number in parsed_row["part_numbers"]:
            code_stats.update([part_number["part_number_type"]])

        fitment_stats["confident"] += len(parsed_row["fitments_confident"])
        fitment_stats["unparsed"] += len(parsed_row["fitments_unparsed"])

        clean_rows.append(parsed_row)
        time.sleep(max(delay_seconds, 0.0))

    clean_path = output_dir / CLEAN_DATASET_FILENAME
    report_path = output_dir / REPORT_FILENAME

    _json_dump(clean_path, clean_rows)

    report_payload: dict[str, Any] = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "base_url": RG_EN_BASE_URL,
        "sample_limit": limit,
        "selected_categories": selected_categories,
        "products": {
            "collected_urls": len(selected_links),
            "clean_records": len(clean_rows),
            "raw_html_dir": str(raw_html_dir),
        },
        "cleaning": {
            "part_numbers": {
                "EAN": code_stats.get("EAN", 0),
                "XREF": code_stats.get("XREF", 0),
                "UNK": code_stats.get("UNK", 0),
            },
            "fitments": {
                "confident": fitment_stats["confident"],
                "unparsed": fitment_stats["unparsed"],
            },
        },
        "errors": errors,
    }

    _json_dump(report_path, report_payload)
    return report_payload


def _build_unique_slug(model_class, value: str, *, max_length: int, fallback_prefix: str) -> str:
    base_slug = slugify(value).strip("-") or fallback_prefix
    base_slug = base_slug[:max_length].rstrip("-") or fallback_prefix
    candidate = base_slug
    suffix = 2
    while model_class.objects.filter(slug=candidate).exists():
        suffix_text = f"-{suffix}"
        truncated = base_slug[: max_length - len(suffix_text)].rstrip("-")
        candidate = f"{truncated}{suffix_text}" if truncated else f"{fallback_prefix}{suffix_text}"
        suffix += 1
    return candidate


def _ensure_supplier() -> Supplier:
    supplier, _created = Supplier.objects.get_or_create(
        code="RG-GMBH",
        defaults={
            "name": "RG GmbH",
            "slug": "rg-gmbh",
            "country": "Germany",
            "website": "https://www.rg-gmbh.de/en/",
            "is_active": True,
        },
    )
    return supplier


def _ensure_conditions() -> dict[str, Condition]:
    condition_specs = (
        ("new", "New"),
        ("take_off", "New - Take off"),
        ("refurbished", "Rebuilt"),
        ("used", "Used"),
        ("exchange", "Exchange"),
        ("second_quality", "II. Choice"),
    )
    conditions: dict[str, Condition] = {}
    for code, name in condition_specs:
        condition = Condition.objects.filter(code__iexact=code).first()
        if condition is None:
            condition = Condition.objects.filter(name__iexact=name).first()

        if condition is None:
            condition = Condition.objects.create(
                code=code,
                name=name,
                slug=_safe_slug(code, fallback="condition"),
                description="",
                is_active=True,
            )
        else:
            changed = False
            if condition.code != code:
                condition.code = code
                changed = True
            if condition.name != name:
                condition.name = name
                changed = True
            if not condition.slug:
                condition.slug = _safe_slug(code, fallback="condition")
                changed = True
            if not condition.is_active:
                condition.is_active = True
                changed = True
            if changed:
                condition.save()

        conditions[code] = condition
    return conditions


def _ensure_part_number_types() -> dict[str, PartNumberType]:
    specs = (
        ("OEM", 1),
        ("OES", 2),
        ("AIM", 3),
        ("XREF", 10),
        ("EAN", 11),
        ("UNK", 12),
    )
    types: dict[str, PartNumberType] = {}
    for code, sort_order in specs:
        part_type, _ = PartNumberType.objects.get_or_create(
            code=code,
            defaults={
                "name": code,
                "sort_order": sort_order,
                "is_active": True,
            },
        )
        types[code] = part_type
    return types


def _ensure_category(category_slug: str) -> Category:
    category_name = _clean_spaces(category_slug.replace("-", " ").title())
    category, _ = Category.objects.get_or_create(
        slug=category_slug,
        defaults={
            "name": category_name,
            "parent": None,
            "description": "Imported from RG category slug",
            "is_active": True,
        },
    )
    return category


def _ensure_vehicle_brand(brand_name: str) -> Brand:
    brand = Brand.objects.filter(name__iexact=brand_name).first()
    if brand:
        if brand.brand_type == Brand.BrandType.PARTS:
            brand.brand_type = Brand.BrandType.BOTH
            brand.save(update_fields=["brand_type", "updated_at"])
        return brand

    slug = _build_unique_slug(Brand, brand_name, max_length=140, fallback_prefix="vehicle-brand")
    return Brand.objects.create(
        name=brand_name,
        slug=slug,
        brand_type=Brand.BrandType.VEHICLE,
        is_active=True,
    )


def import_rg_clean_dataset(
    *,
    input_file: Path,
    report_file: Path | None = None,
) -> dict[str, Any]:
    input_file = Path(input_file)
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    rows = json.loads(input_file.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Clean dataset must be a JSON list")

    supplier = _ensure_supplier()
    conditions = _ensure_conditions()
    part_types = _ensure_part_number_types()

    summary: dict[str, Any] = {
        "processed": 0,
        "created_products": 0,
        "updated_products": 0,
        "skipped": 0,
        "created_part_numbers": 0,
        "created_fitments": 0,
        "errors": [],
    }

    with transaction.atomic():
        for index, row in enumerate(rows, start=1):
            summary["processed"] += 1

            supplier_product_code = _clean_spaces(str(row.get("supplier_product_code", "")))
            sku = _clean_spaces(str(row.get("sku", "")))
            title = _clean_spaces(str(row.get("title", "")))
            category_slug = _clean_spaces(str(row.get("category_slug", "")))
            condition_code = _clean_spaces(str(row.get("condition_code", "new"))).lower() or "new"

            if not supplier_product_code or not sku or not title or not category_slug:
                summary["skipped"] += 1
                summary["errors"].append(
                    f"Row {index}: missing one of supplier_product_code/sku/title/category_slug"
                )
                continue

            category = _ensure_category(category_slug)
            condition = conditions.get(condition_code, conditions["new"])

            product = Product.objects.filter(
                supplier=supplier,
                supplier_product_code=supplier_product_code,
            ).first()

            if product is None:
                product = Product(
                    supplier=supplier,
                    supplier_product_code=supplier_product_code,
                    sku=sku,
                    title=title,
                    short_description=_clean_spaces(
                        str(row.get("raw_attributes", {}).get("Description", ""))
                    )[:280],
                    category=category,
                    condition=condition,
                    publication_status=Product.PublicationStatus.DRAFT,
                    published_at=None,
                    price_visibility_mode=Product.PriceVisibilityMode.HIDDEN,
                    is_active=True,
                )
                product.save()
                summary["created_products"] += 1
            else:
                product.title = title
                product.category = category
                product.condition = condition
                product.publication_status = Product.PublicationStatus.DRAFT
                product.published_at = None
                if product.sku != sku:
                    conflict = Product.objects.exclude(pk=product.pk).filter(sku=sku).exists()
                    if not conflict:
                        product.sku = sku
                short_description = _clean_spaces(
                    str(row.get("raw_attributes", {}).get("Description", ""))
                )[:280]
                if short_description:
                    product.short_description = short_description
                product.save()
                summary["updated_products"] += 1

            for part_payload in row.get("part_numbers", []):
                number_raw = _clean_spaces(str(part_payload.get("number_raw", ""))).upper()
                type_code = _clean_spaces(str(part_payload.get("part_number_type", "UNK"))).upper()
                if not number_raw:
                    continue

                part_type = part_types.get(type_code, part_types["UNK"])
                normalized = _normalize_code(number_raw)
                exists = PartNumber.objects.filter(
                    product=product,
                    part_number_type=part_type,
                    number_normalized=normalized,
                ).exists()
                if exists:
                    continue

                PartNumber.objects.create(
                    product=product,
                    number_raw=number_raw,
                    part_number_type=part_type,
                    is_primary=False,
                )
                summary["created_part_numbers"] += 1

            for fitment_payload in row.get("fitments_confident", []):
                brand_name = _clean_spaces(str(fitment_payload.get("brand_name", "")))
                model = _clean_spaces(str(fitment_payload.get("model", "")))
                if not brand_name or not model:
                    continue

                brand = _ensure_vehicle_brand(brand_name)
                year_start = fitment_payload.get("year_start")
                year_end = fitment_payload.get("year_end")
                generation = _clean_spaces(str(fitment_payload.get("generation", "")))
                variant = _clean_spaces(str(fitment_payload.get("variant", "")))

                vehicle, _ = Vehicle.objects.get_or_create(
                    vehicle_type=Vehicle.VehicleType.CAR,
                    brand=brand,
                    model=model,
                    generation=generation,
                    variant=variant,
                    year_start=year_start,
                    year_end=year_end,
                    defaults={
                        "is_active": True,
                    },
                )

                _, created_fitment = ProductVehicleFitment.objects.get_or_create(
                    product=product,
                    vehicle=vehicle,
                    defaults={
                        "fitment_notes": _clean_spaces(
                            str(fitment_payload.get("source_text", ""))
                        ),
                        "source": ProductVehicleFitment.FitmentSource.IMPORT,
                        "is_verified": False,
                    },
                )
                if created_fitment:
                    summary["created_fitments"] += 1

    summary["generated_at"] = datetime.now(tz=UTC).isoformat()

    if report_file is not None:
        report_path = Path(report_file)
        report_payload: dict[str, Any] = {}
        if report_path.exists():
            try:
                report_payload = json.loads(report_path.read_text(encoding="utf-8"))
            except Exception:
                report_payload = {}
        report_payload["import"] = summary
        _json_dump(report_path, report_payload)

    return summary
