
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from apps.catalog.models import Brand
from apps.vehicles.models import Vehicle


class ImportVehicleTypesCommandTests(TestCase):
    def _write_csv(self, content: str) -> Path:
        temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
        temp_file.write(content)
        temp_file.flush()
        temp_file.close()
        return Path(temp_file.name)

    def test_imports_rows_and_is_idempotent(self):
        csv_content = (
            "make,model,vehicle_type,tecdoc_type_number,year_from,year_to,fuel_type,"
            "body_type,engine_code,power_kw,displacement_cc,source_url\n"
            "ABARTH,500,1.4,1052,2008,2010,Gasoline,Hatchback,312A1.000,99,1368,"
            "https://example.com/a\n"
            "ABARTH,500,1.4,1052,2008,2010,Gasoline,Hatchback,312A1.000,99,1368,"
            "https://example.com/a\n"
            "FORD,Transit,2.0 TDCi,2020,2015,2013,Diesel,Van,ABC123,77,1995,"
            "https://example.com/b\n"
        )
        file_path = self._write_csv(csv_content)
        self.addCleanup(lambda: file_path.unlink(missing_ok=True))

        call_command("import_vehicle_types", str(file_path))

        self.assertEqual(Brand.objects.filter(name__in=["ABARTH", "FORD"]).count(), 2)
        self.assertEqual(Vehicle.objects.count(), 2)

        first_vehicle = Vehicle.objects.get(brand__name="ABARTH", model="500")
        self.assertEqual(first_vehicle.variant, "1.4")
        self.assertEqual(first_vehicle.generation, "Hatchback")
        self.assertEqual(first_vehicle.year_start, 2008)
        self.assertEqual(first_vehicle.year_end, 2010)
        self.assertEqual(first_vehicle.fuel_type, Vehicle.FuelType.GASOLINE)
        self.assertIn("tecdoc_type_number=1052", first_vehicle.notes)

        second_vehicle = Vehicle.objects.get(brand__name="FORD", model="Transit")
        self.assertEqual(second_vehicle.vehicle_type, Vehicle.VehicleType.VAN)
        self.assertEqual(second_vehicle.year_start, 2013)
        self.assertEqual(second_vehicle.year_end, 2015)
        self.assertEqual(second_vehicle.fuel_type, Vehicle.FuelType.DIESEL)

        call_command("import_vehicle_types", str(file_path))
        self.assertEqual(Vehicle.objects.count(), 2)

    def test_existing_parts_brand_is_upgraded_to_both(self):
        Brand.objects.create(
            name="BMW",
            slug="bmw",
            brand_type=Brand.BrandType.PARTS,
            is_active=True,
        )
        csv_content = (
            "make,model,vehicle_type,tecdoc_type_number,year_from,year_to,fuel_type,"
            "body_type,engine_code,power_kw,displacement_cc,source_url\n"
            "BMW,320d,2.0,12345,2012,2018,Diesel,Sedan,N47,135,1995,https://example.com/c\n"
        )
        file_path = self._write_csv(csv_content)
        self.addCleanup(lambda: file_path.unlink(missing_ok=True))

        call_command("import_vehicle_types", str(file_path))

        brand = Brand.objects.get(name="BMW")
        self.assertEqual(brand.brand_type, Brand.BrandType.BOTH)
        self.assertEqual(Vehicle.objects.filter(brand=brand, model="320d").count(), 1)
