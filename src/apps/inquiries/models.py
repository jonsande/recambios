from __future__ import annotations

import string

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.crypto import get_random_string


class Inquiry(models.Model):
    class Language(models.TextChoices):
        SPANISH = "es", "Spanish"
        ENGLISH = "en", "English"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        IN_REVIEW = "in_review", "In Review"
        SUPPLIER_PENDING = "supplier_pending", "Supplier Pending"
        RESPONDED = "responded", "Responded to Customer"
        ACCEPTED = "accepted", "Accepted by Customer"
        REJECTED = "rejected", "Rejected by Customer"
        CLOSED = "closed", "Closed"

    REFERENCE_PREFIX = "INQ"
    REFERENCE_RANDOM_LENGTH = 6
    REFERENCE_ALLOWED_CHARS = string.ascii_uppercase + string.digits
    STATUS_TRANSITIONS = {
        Status.DRAFT: (Status.SUBMITTED, Status.CLOSED),
        Status.SUBMITTED: (Status.IN_REVIEW, Status.CLOSED),
        Status.IN_REVIEW: (Status.SUPPLIER_PENDING, Status.RESPONDED, Status.CLOSED),
        Status.SUPPLIER_PENDING: (Status.IN_REVIEW, Status.RESPONDED, Status.CLOSED),
        Status.RESPONDED: (Status.ACCEPTED, Status.REJECTED, Status.CLOSED),
        Status.ACCEPTED: (Status.CLOSED,),
        Status.REJECTED: (Status.CLOSED,),
        Status.CLOSED: (),
    }

    reference_code = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inquiries",
    )
    guest_name = models.CharField(max_length=150, blank=True)
    guest_email = models.EmailField(blank=True)
    guest_phone = models.CharField(max_length=50, blank=True)
    company_name = models.CharField(max_length=180, blank=True)
    tax_id = models.CharField(max_length=64, blank=True)
    language = models.CharField(
        max_length=5,
        choices=Language.choices,
        default=Language.SPANISH,
    )
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.SUBMITTED,
        db_index=True,
    )
    notes_from_customer = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    response_due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    supplier_feedback_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(user__isnull=False)
                | (Q(guest_name__gt="") & Q(guest_email__gt="")),
                name="inq_user_or_guest_contact_ck",
            )
        ]
        indexes = [
            models.Index(fields=["status", "created_at"], name="inq_status_created_idx"),
            models.Index(fields=["status", "response_due_at"], name="inq_status_due_idx"),
            models.Index(fields=["user", "status"], name="inq_user_status_idx"),
            models.Index(fields=["guest_email"], name="inq_guest_email_idx"),
        ]

    def __str__(self) -> str:
        return self.reference_code

    @property
    def requester_display(self) -> str:
        if self.user_id:
            return self.user.get_username()
        if self.guest_name:
            return self.guest_name
        return self.guest_email

    @classmethod
    def allowed_next_statuses(cls, current_status: str) -> tuple[str, ...]:
        return cls.STATUS_TRANSITIONS.get(current_status, ())

    def can_transition_to(self, next_status: str) -> bool:
        return next_status in self.allowed_next_statuses(self.status)

    def transition_to(self, next_status: str) -> None:
        if next_status == self.status:
            return
        if not self.can_transition_to(next_status):
            raise ValueError(
                f"Status transition from '{self.status}' to '{next_status}' is not allowed."
            )
        self.status = next_status

    def clean(self) -> None:
        super().clean()

        errors = {}
        if not self.user_id:
            if not self.guest_name:
                errors["guest_name"] = "Guest name is required when no registered user is attached."
            if not self.guest_email:
                errors["guest_email"] = (
                    "Guest email is required when no registered user is attached."
                )

        if errors:
            raise ValidationError(errors)

    @classmethod
    def generate_reference_code(cls) -> str:
        date_part = timezone.localdate().strftime("%Y%m%d")
        for _ in range(50):
            suffix = get_random_string(
                cls.REFERENCE_RANDOM_LENGTH,
                allowed_chars=cls.REFERENCE_ALLOWED_CHARS,
            )
            reference_code = f"{cls.REFERENCE_PREFIX}-{date_part}-{suffix}"
            if not cls.objects.filter(reference_code=reference_code).exists():
                return reference_code
        raise RuntimeError("Unable to generate a unique inquiry reference code.")

    def save(self, *args, **kwargs) -> None:
        string_fields = ("guest_name", "guest_email", "guest_phone", "company_name", "tax_id")
        for field_name in string_fields:
            value = getattr(self, field_name)
            if isinstance(value, str):
                setattr(self, field_name, value.strip())

        if self.guest_email:
            self.guest_email = self.guest_email.lower()

        if not self.reference_code:
            self.reference_code = self.generate_reference_code()

        self.full_clean()
        super().save(*args, **kwargs)


class InquiryItem(models.Model):
    inquiry = models.ForeignKey(
        "inquiries.Inquiry",
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="inquiry_items",
    )
    requested_quantity = models.PositiveIntegerField(default=1)
    customer_note = models.TextField(blank=True)
    last_known_price_snapshot = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["inquiry_id", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(requested_quantity__gte=1),
                name="inq_item_quantity_gte_1_ck",
            ),
            models.UniqueConstraint(
                fields=["inquiry", "product"],
                name="inq_item_inquiry_product_uq",
            ),
        ]
        indexes = [
            models.Index(fields=["inquiry", "product"], name="inq_item_inquiry_product_idx"),
            models.Index(fields=["product", "created_at"], name="inq_item_product_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.inquiry.reference_code} · {self.product.sku}"

    def save(self, *args, **kwargs) -> None:
        if isinstance(self.customer_note, str):
            self.customer_note = self.customer_note.strip()

        if self._state.adding and self.last_known_price_snapshot is None and self.product_id:
            if hasattr(self, "product"):
                self.last_known_price_snapshot = self.product.last_known_price
            else:
                product = (
                    self._meta.get_field("product")
                    .related_model.objects.only("last_known_price")
                    .get(pk=self.product_id)
                )
                self.last_known_price_snapshot = product.last_known_price

        self.full_clean()
        super().save(*args, **kwargs)
