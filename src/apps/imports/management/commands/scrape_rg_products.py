from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand

from apps.imports.rg_pipeline import (
    CLEAN_DATASET_FILENAME,
    REPORT_FILENAME,
    scrape_rg_products_sample,
)


class Command(BaseCommand):
    help = "Scrape RG GmbH English catalog and build a cleaned staging dataset."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=30,
            help="Number of products to stage (default: 30)",
        )
        parser.add_argument(
            "--output-dir",
            default="data/rg",
            help="Output directory for raw HTML, clean JSON and report (default: data/rg)",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.05,
            help="Delay in seconds between HTTP requests (default: 0.05)",
        )
        parser.add_argument(
            "--top-categories",
            type=int,
            default=6,
            help="How many top categories by volume to prioritize (default: 6)",
        )

    def handle(self, *args, **options):
        output_dir = Path(options["output_dir"])
        self.stdout.write(
            "Scraping RG catalog in English "
            f"(limit={options['limit']}, output_dir={output_dir})..."
        )

        report = scrape_rg_products_sample(
            limit=max(1, int(options["limit"])),
            output_dir=output_dir,
            delay_seconds=max(0.0, float(options["delay"])),
            top_categories=max(1, int(options["top_categories"])),
        )

        products = report.get("products", {})
        cleaning = report.get("cleaning", {})
        part_numbers = cleaning.get("part_numbers", {})
        fitments = cleaning.get("fitments", {})

        self.stdout.write(self.style.SUCCESS("RG scraping completed."))
        self.stdout.write(f"  Selected product URLs: {products.get('collected_urls', 0)}")
        self.stdout.write(f"  Clean records: {products.get('clean_records', 0)}")
        self.stdout.write(
            "  Part numbers: "
            f"EAN={part_numbers.get('EAN', 0)}, "
            f"XREF={part_numbers.get('XREF', 0)}, "
            f"UNK={part_numbers.get('UNK', 0)}"
        )
        self.stdout.write(
            "  Fitments: "
            f"confident={fitments.get('confident', 0)}, "
            f"unparsed={fitments.get('unparsed', 0)}"
        )
        self.stdout.write(f"  Clean dataset: {output_dir / CLEAN_DATASET_FILENAME}")
        self.stdout.write(f"  Report: {output_dir / REPORT_FILENAME}")

        if report.get("errors"):
            self.stdout.write(self.style.WARNING(f"  Non-blocking errors: {len(report['errors'])}"))
