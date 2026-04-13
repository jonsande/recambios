from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.imports.rg_pipeline import import_rg_clean_dataset


class Command(BaseCommand):
    help = "Import cleaned RG staging dataset into the local catalog database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--input-file",
            default="data/rg/rg_products_clean.json",
            help="Path to cleaned RG dataset JSON (default: data/rg/rg_products_clean.json)",
        )
        parser.add_argument(
            "--report-file",
            default="data/rg/rg_import_report.json",
            help=(
                "Path to RG report JSON to append import stats "
                "(default: data/rg/rg_import_report.json)"
            ),
        )

    def handle(self, *args, **options):
        input_file = Path(options["input_file"])
        report_file = Path(options["report_file"])

        if not input_file.exists():
            raise CommandError(f"Input file not found: {input_file}")

        self.stdout.write(f"Importing RG clean dataset from {input_file}...")

        summary = import_rg_clean_dataset(
            input_file=input_file,
            report_file=report_file,
        )

        self.stdout.write(self.style.SUCCESS("RG import completed."))
        self.stdout.write(f"  Processed rows: {summary['processed']}")
        self.stdout.write(f"  Created products: {summary['created_products']}")
        self.stdout.write(f"  Updated products: {summary['updated_products']}")
        self.stdout.write(f"  Skipped rows: {summary['skipped']}")
        self.stdout.write(f"  Created part numbers: {summary['created_part_numbers']}")
        self.stdout.write(f"  Created fitments: {summary['created_fitments']}")
        self.stdout.write(f"  Report updated at: {report_file}")

        if summary.get("errors"):
            self.stdout.write(self.style.WARNING(f"  Row-level warnings: {len(summary['errors'])}"))
