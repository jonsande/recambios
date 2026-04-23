from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.inquiries.deadlines import expire_due_inquiry_deadlines


class Command(BaseCommand):
    help = "Expire inquiry offer/payment deadlines and dispatch expiry notifications."

    def handle(self, *args, **options):
        summary = expire_due_inquiry_deadlines()
        self.stdout.write(
            self.style.SUCCESS(
                "Deadline expiration completed. "
                f"Offers expired: {summary['offers_expired']}. "
                f"Payments expired: {summary['payments_expired']}."
            )
        )
