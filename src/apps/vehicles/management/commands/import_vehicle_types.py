from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from apps.catalog.models import Brand
from apps.vehicles.models import Vehicle

DEFAULT_IMPORT_PATHS = ("vehicle_types.csv", "vehicle_types.json")


@dataclass(frozen=True)
class ParsedVehicleRow:
    make: str
    model: str
    variant: str
    generation: str
    vehicle_type: str
    year_start: int | None
    year_end: int | None
    engine_code: str
    fuel_type: str
    displacement_cc: int | None
    power_kw: int | None
    power_hp: int | None
    notes: str


class Command(BaseCommand):
    help = "Import vehicle brands and vehicle records from vehicle_types CSV/JSON files."

    def add_arguments(self, parser):
        parser.add_argument(
            "paths",
            nargs="*",
            help=(
                "Input files (.csv and/or .json). "
                "Defaults to vehicle_types.csv and vehicle_types.json"
            ),
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=2000,
            help="Bulk create batch size (default: 2000).",
        )

    def handle(self, *args, **options):
        input_paths = self._resolve_input_paths(options["paths"])
        batch_size = max(1, int(options["batch_size"]))

        brand_cache, known_slugs = self._load_brand_cache()
        existing_vehicle_keys = set(
            Vehicle.objects.values_list(
                "vehicle_type",
                "brand_id",
                "model",
                "generation",
                "variant",
                "year_start",
                "year_end",
                "engine_code",
                "fuel_type",
                "displacement_cc",
                "power_kw",
                "power_hp",
                "notes",
            )
        )

        rows_seen = 0
        rows_skipped = 0
        duplicate_rows = 0
        brands_created = 0
        brands_updated = 0
        created_vehicles = 0
        to_create: list[Vehicle] = []

        self.stdout.write(
            f"Starting vehicle import from {len(input_paths)} files with batch size {batch_size}."
        )

        for path in input_paths:
            self.stdout.write(f"Processing {path} ...")
            for raw_row in self._iter_rows(path):
                rows_seen += 1
                parsed_row = self._parse_row(raw_row)
                if parsed_row is None:
                    rows_skipped += 1
                    continue

                brand, created_brand, updated_brand = self._get_or_create_vehicle_brand(
                    parsed_row.make,
                    brand_cache,
                    known_slugs,
                )
                if created_brand:
                    brands_created += 1
                if updated_brand:
                    brands_updated += 1

                vehicle_key = (
                    parsed_row.vehicle_type,
                    brand.id,
                    parsed_row.model,
                    parsed_row.generation,
                    parsed_row.variant,
                    parsed_row.year_start,
                    parsed_row.year_end,
                    parsed_row.engine_code,
                    parsed_row.fuel_type,
                    parsed_row.displacement_cc,
                    parsed_row.power_kw,
                    parsed_row.power_hp,
                    parsed_row.notes,
                )
                if vehicle_key in existing_vehicle_keys:
                    duplicate_rows += 1
                    continue

                existing_vehicle_keys.add(vehicle_key)
                to_create.append(
                    Vehicle(
                        vehicle_type=parsed_row.vehicle_type,
                        brand=brand,
                        model=parsed_row.model,
                        generation=parsed_row.generation,
                        variant=parsed_row.variant,
                        year_start=parsed_row.year_start,
                        year_end=parsed_row.year_end,
                        engine_code=parsed_row.engine_code,
                        fuel_type=parsed_row.fuel_type,
                        displacement_cc=parsed_row.displacement_cc,
                        power_kw=parsed_row.power_kw,
                        power_hp=parsed_row.power_hp,
                        notes=parsed_row.notes,
                        is_active=True,
                    )
                )

                if len(to_create) >= batch_size:
                    Vehicle.objects.bulk_create(to_create, batch_size=batch_size)
                    created_vehicles += len(to_create)
                    to_create = []

        if to_create:
            Vehicle.objects.bulk_create(to_create, batch_size=batch_size)
            created_vehicles += len(to_create)

        self.stdout.write(self.style.SUCCESS("Vehicle import completed."))
        self.stdout.write(f"  Rows read: {rows_seen}")
        self.stdout.write(f"  Rows skipped (missing make/model): {rows_skipped}")
        self.stdout.write(f"  Rows skipped (duplicates): {duplicate_rows}")
        self.stdout.write(f"  Brands created: {brands_created}")
        self.stdout.write(f"  Brands updated to type=both: {brands_updated}")
        self.stdout.write(f"  Vehicles created: {created_vehicles}")

    def _resolve_input_paths(self, provided_paths: list[str]) -> list[Path]:
        paths = [Path(path) for path in provided_paths] if provided_paths else [
            Path(path) for path in DEFAULT_IMPORT_PATHS
        ]
        existing_paths = [path for path in paths if path.exists()]
        if not existing_paths:
            attempted = ", ".join(str(path) for path in paths)
            raise CommandError(f"No input files found. Attempted: {attempted}")
        return existing_paths

    def _iter_rows(self, path: Path) -> Iterator[dict[str, Any]]:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    yield row
            return

        if suffix == ".json":
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, list):
                raise CommandError(f"JSON file must contain a list of objects: {path}")
            for row in payload:
                if isinstance(row, dict):
                    yield row
            return

        raise CommandError(f"Unsupported file type for import: {path}")

    def _load_brand_cache(self) -> tuple[dict[str, Brand], set[str]]:
        brands = list(Brand.objects.all())
        cache: dict[str, Brand] = {}
        for brand in brands:
            cache[brand.name.casefold()] = brand
        known_slugs = {brand.slug for brand in brands}
        return cache, known_slugs

    def _get_or_create_vehicle_brand(
        self,
        make: str,
        brand_cache: dict[str, Brand],
        known_slugs: set[str],
    ) -> tuple[Brand, bool, bool]:
        cache_key = make.casefold()
        if cache_key in brand_cache:
            brand = brand_cache[cache_key]
            if brand.brand_type == Brand.BrandType.PARTS:
                brand.brand_type = Brand.BrandType.BOTH
                brand.save(update_fields=["brand_type", "updated_at"])
                return brand, False, True
            return brand, False, False

        slug = self._build_unique_brand_slug(make, known_slugs)
        brand = Brand.objects.create(
            name=make,
            slug=slug,
            brand_type=Brand.BrandType.VEHICLE,
            is_active=True,
        )
        brand_cache[cache_key] = brand
        known_slugs.add(slug)
        return brand, True, False

    def _build_unique_brand_slug(self, name: str, known_slugs: set[str]) -> str:
        max_len = Brand._meta.get_field("slug").max_length
        base_slug = slugify(name).strip("-")[:max_len].rstrip("-") or "brand"
        candidate = base_slug
        index = 2

        while candidate in known_slugs:
            suffix = f"-{index}"
            trimmed = base_slug[: max_len - len(suffix)].rstrip("-")
            candidate = f"{trimmed}{suffix}" if trimmed else f"brand{suffix}"
            index += 1

        return candidate

    def _parse_row(self, row: dict[str, Any]) -> ParsedVehicleRow | None:
        make = self._clean_text(row.get("make"), max_len=120)
        model = self._clean_text(row.get("model"), max_len=120)
        if not make or not model:
            return None

        variant = self._clean_text(row.get("vehicle_type"), max_len=120)
        generation = self._clean_text(row.get("body_type"), max_len=120)
        engine_code = self._clean_text(row.get("engine_code"), max_len=80)

        year_start = self._parse_year(row.get("year_from"))
        year_end = self._parse_year(row.get("year_to"))
        if year_start and year_end and year_end < year_start:
            year_start, year_end = year_end, year_start

        power_kw = self._parse_positive_int(row.get("power_kw"))
        power_hp = round(power_kw * 1.34102209) if power_kw else None
        displacement_cc = self._parse_positive_int(row.get("displacement_cc"))

        tecdoc = self._clean_text(row.get("tecdoc_type_number"), max_len=80)
        source_url = self._clean_text(row.get("source_url"), max_len=500)
        notes_parts: list[str] = []
        if tecdoc:
            notes_parts.append(f"tecdoc_type_number={tecdoc}")
        if source_url:
            notes_parts.append(f"source_url={source_url}")
        notes = " | ".join(notes_parts)

        inferred_vehicle_type = self._infer_vehicle_type(model, generation, variant)

        return ParsedVehicleRow(
            make=make,
            model=model,
            variant=variant,
            generation=generation,
            vehicle_type=inferred_vehicle_type,
            year_start=year_start,
            year_end=year_end,
            engine_code=engine_code,
            fuel_type=self._map_fuel_type(row.get("fuel_type")),
            displacement_cc=displacement_cc,
            power_kw=power_kw,
            power_hp=power_hp,
            notes=notes,
        )

    def _clean_text(self, value: Any, *, max_len: int | None = None) -> str:
        if value is None:
            return ""
        text = " ".join(str(value).strip().split())
        if not text:
            return ""
        if max_len is not None and len(text) > max_len:
            return text[:max_len].rstrip()
        return text

    def _parse_year(self, value: Any) -> int | None:
        year = self._parse_positive_int(value)
        if year is None:
            return None
        if 1886 <= year <= 2100:
            return year
        return None

    def _parse_positive_int(self, value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            number = float(str(value).strip().replace(",", "."))
        except ValueError:
            return None
        parsed = int(round(number))
        if parsed <= 0:
            return None
        return parsed

    def _map_fuel_type(self, raw_value: Any) -> str:
        raw = self._clean_text(raw_value).casefold()
        if not raw:
            return ""
        if "diesel" in raw:
            return Vehicle.FuelType.DIESEL
        if "hybrid" in raw:
            return Vehicle.FuelType.HYBRID
        if "electric" in raw:
            return Vehicle.FuelType.ELECTRIC
        if "lpg" in raw:
            return Vehicle.FuelType.LPG
        if "cng" in raw or "natural gas" in raw:
            return Vehicle.FuelType.CNG
        gasoline_terms = ("gasoline", "petrol", "benzin", "benzina")
        if any(term in raw for term in gasoline_terms):
            return Vehicle.FuelType.GASOLINE
        return ""

    def _infer_vehicle_type(self, model: str, generation: str, variant: str) -> str:
        combined = " ".join((model, generation, variant)).casefold()
        if any(token in combined for token in ("motorcycle", "scooter", "moto", "bike")):
            return Vehicle.VehicleType.MOTORCYCLE
        if any(
            token in combined
            for token in ("truck", "pickup", "pick-up", "lorry", "camion", "tractor")
        ):
            return Vehicle.VehicleType.TRUCK
        if any(token in combined for token in ("van", "minibus", "panel")):
            return Vehicle.VehicleType.VAN
        return Vehicle.VehicleType.CAR
