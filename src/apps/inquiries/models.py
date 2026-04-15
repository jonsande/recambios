from __future__ import annotations

import string
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
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

    class NegativeResolutionReason(models.TextChoices):
        UNAVAILABLE = "unavailable", "Unavailable"
        SUPPLIER_CANNOT_CONFIRM = "supplier_cannot_confirm", "Supplier Cannot Confirm"
        LOGISTICS_NOT_POSSIBLE = "logistics_not_possible", "Logistics Not Possible"
        OTHER = "other", "Other"

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
    negative_resolution_reason = models.CharField(
        max_length=40,
        choices=NegativeResolutionReason.choices,
        blank=True,
        db_index=True,
    )
    negative_resolution_internal_notes = models.TextField(blank=True)
    negative_resolution_customer_message = models.TextField(blank=True)
    negative_resolved_at = models.DateTimeField(null=True, blank=True, db_index=True)
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

    @property
    def is_negatively_resolved(self) -> bool:
        return self.negative_resolved_at is not None

    def finalize_negative_resolution(self, *, save: bool = True) -> None:
        errors = {}
        if not self.negative_resolution_reason:
            errors["negative_resolution_reason"] = (
                "A negative resolution reason is required before finalizing."
            )

        if self.pk and InquiryOffer.objects.filter(inquiry_id=self.pk).exists():
            errors["__all__"] = (
                "Negative resolution cannot be finalized because this inquiry already has an offer."
            )

        if errors:
            raise ValidationError(errors)

        self.negative_resolved_at = timezone.now()
        if self.status != self.Status.CLOSED:
            if not self.can_transition_to(self.Status.CLOSED):
                raise ValueError(
                    "Status transition from "
                    f"'{self.status}' to '{self.Status.CLOSED}' is not allowed."
                )
            self.transition_to(self.Status.CLOSED)

        if save:
            self.save()

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

        if self.negative_resolved_at is not None:
            if not self.negative_resolution_reason:
                errors["negative_resolution_reason"] = (
                    "Negative resolution reason is required when negative_resolved_at is set."
                )
            if self.status != self.Status.CLOSED:
                errors["status"] = (
                    "Negative resolution requires inquiry status to be 'closed'."
                )
            if self.pk and InquiryOffer.objects.filter(inquiry_id=self.pk).exists():
                errors["negative_resolved_at"] = (
                    "Negative resolution cannot be stored when an offer already exists."
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
        string_fields = (
            "guest_name",
            "guest_email",
            "guest_phone",
            "company_name",
            "tax_id",
            "negative_resolution_internal_notes",
            "negative_resolution_customer_message",
        )
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


class InquiryOffer(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent to Customer"
        ACCEPTED = "accepted", "Accepted by Customer"
        REJECTED = "rejected", "Rejected by Customer"

    REFERENCE_PREFIX = "OFF"
    REFERENCE_RANDOM_LENGTH = 6
    REFERENCE_ALLOWED_CHARS = string.ascii_uppercase + string.digits
    STATUS_TRANSITIONS = {
        Status.DRAFT: (Status.SENT,),
        Status.SENT: (Status.ACCEPTED, Status.REJECTED),
        Status.ACCEPTED: (),
        Status.REJECTED: (),
    }

    inquiry = models.OneToOneField(
        "inquiries.Inquiry",
        on_delete=models.CASCADE,
        related_name="offer",
    )
    reference_code = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        editable=False,
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    confirmed_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text=(
            "Final confirmed commercial total for this offer. "
            "This is the source of truth for later payment preparation."
        ),
    )
    currency = models.CharField(
        max_length=3,
        default="EUR",
        help_text="ISO 4217 currency code for the confirmed total amount.",
    )
    lead_time_text = models.CharField(max_length=255, blank=True)
    internal_notes = models.TextField(blank=True)
    customer_message = models.TextField(blank=True)
    access_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True, db_index=True)
    accepted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    rejected_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(confirmed_total__gte=0),
                name="inq_offer_total_gte_0_ck",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "sent_at"], name="inq_offer_status_sent_idx"),
            models.Index(
                fields=["status", "created_at"],
                name="inq_offer_status_created_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.reference_code

    @property
    def is_ready_for_payment(self) -> bool:
        # Semantic alias kept intentionally for the future payment phase bridge.
        return self.status == self.Status.ACCEPTED

    @property
    def has_payment_record(self) -> bool:
        if not self.pk:
            return False
        return InquiryOfferPayment.objects.filter(offer_id=self.pk).exists()

    def _build_send_readiness_errors(self) -> dict[str, str]:
        errors: dict[str, str] = {}
        confirmed_total = self.confirmed_total
        if confirmed_total is None:
            errors["confirmed_total"] = "A confirmed total amount is required before sending."
        elif confirmed_total <= 0:
            errors["confirmed_total"] = (
                "Confirmed total amount must be greater than zero before sending."
            )

        currency = (self.currency or "").strip().upper()
        if not currency:
            errors["currency"] = "Currency is required before sending."
        elif len(currency) != 3:
            errors["currency"] = "Currency must be a 3-letter code before sending."

        if not (self.lead_time_text or "").strip():
            errors["lead_time_text"] = (
                "Lead time estimate is required before sending the offer to the customer."
            )

        return errors

    def _build_send_validation_errors(self) -> dict[str, str]:
        errors = self._build_send_readiness_errors()
        inquiry_ready = self.inquiry.status == Inquiry.Status.RESPONDED
        if not inquiry_ready:
            inquiry_ready = self.inquiry.can_transition_to(Inquiry.Status.RESPONDED)
        if not inquiry_ready:
            errors["inquiry"] = (
                "Inquiry must be in review or supplier pending before sending the offer."
            )
        return errors

    def ensure_ready_to_send(self) -> None:
        errors = self._build_send_readiness_errors()
        if errors:
            raise ValidationError(errors)

    @classmethod
    def allowed_next_statuses(cls, current_status: str) -> tuple[str, ...]:
        return cls.STATUS_TRANSITIONS.get(current_status, ())

    def can_transition_to(self, next_status: str) -> bool:
        return next_status in self.allowed_next_statuses(self.status)

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
        raise RuntimeError("Unable to generate a unique inquiry offer reference code.")

    def _sync_inquiry_status(self, target_status: str) -> None:
        if self.inquiry.status == target_status:
            return
        if not self.inquiry.can_transition_to(target_status):
            return
        self.inquiry.transition_to(target_status)
        self.inquiry.save(update_fields=["status", "updated_at"])

    def mark_sent(self, *, save: bool = True) -> None:
        if not self.can_transition_to(self.Status.SENT):
            raise ValueError("Only draft offers can be sent to the customer.")
        errors = self._build_send_validation_errors()
        if errors:
            raise ValidationError(errors)

        self.status = self.Status.SENT
        self.sent_at = timezone.now()
        self.accepted_at = None
        self.rejected_at = None

        if save:
            with transaction.atomic():
                self.save()
                self._sync_inquiry_status(Inquiry.Status.RESPONDED)

    def mark_accepted(self, *, save: bool = True) -> None:
        if not self.can_transition_to(self.Status.ACCEPTED):
            raise ValueError("Only sent offers can be accepted by the customer.")

        now = timezone.now()
        self.status = self.Status.ACCEPTED
        self.sent_at = self.sent_at or now
        self.accepted_at = now
        self.rejected_at = None

        if save:
            with transaction.atomic():
                self.save()
                self._sync_inquiry_status(Inquiry.Status.ACCEPTED)

    def mark_rejected(self, *, save: bool = True) -> None:
        if not self.can_transition_to(self.Status.REJECTED):
            raise ValueError("Only sent offers can be rejected by the customer.")

        now = timezone.now()
        self.status = self.Status.REJECTED
        self.sent_at = self.sent_at or now
        self.rejected_at = now
        self.accepted_at = None

        if save:
            with transaction.atomic():
                self.save()
                self._sync_inquiry_status(Inquiry.Status.REJECTED)

    def clean(self) -> None:
        super().clean()
        errors = {}

        if self.inquiry_id and self.inquiry.is_negatively_resolved:
            errors["inquiry"] = (
                "Offers cannot be created or updated for an inquiry resolved as not offerable."
            )

        if not self.currency:
            errors["currency"] = "Currency is required."
        elif len(self.currency) != 3:
            errors["currency"] = "Currency must be a 3-letter code."

        if (
            self.pk
            and self.status != self.Status.ACCEPTED
            and InquiryOfferPayment.objects.filter(offer_id=self.pk).exists()
        ):
            errors["status"] = (
                "Offers with an initiated payment record must stay in accepted status."
            )

        if self.status == self.Status.DRAFT:
            if self.sent_at is not None:
                errors["sent_at"] = "Draft offers cannot have sent_at."
            if self.accepted_at is not None:
                errors["accepted_at"] = "Draft offers cannot have accepted_at."
            if self.rejected_at is not None:
                errors["rejected_at"] = "Draft offers cannot have rejected_at."
        elif self.status == self.Status.SENT:
            if self.sent_at is None:
                errors["sent_at"] = "Sent offers must define sent_at."
            if self.accepted_at is not None:
                errors["accepted_at"] = "Sent offers cannot have accepted_at."
            if self.rejected_at is not None:
                errors["rejected_at"] = "Sent offers cannot have rejected_at."
        elif self.status == self.Status.ACCEPTED:
            if self.sent_at is None:
                errors["sent_at"] = "Accepted offers must define sent_at."
            if self.accepted_at is None:
                errors["accepted_at"] = "Accepted offers must define accepted_at."
            if self.rejected_at is not None:
                errors["rejected_at"] = "Accepted offers cannot have rejected_at."
        elif self.status == self.Status.REJECTED:
            if self.sent_at is None:
                errors["sent_at"] = "Rejected offers must define sent_at."
            if self.rejected_at is None:
                errors["rejected_at"] = "Rejected offers must define rejected_at."
            if self.accepted_at is not None:
                errors["accepted_at"] = "Rejected offers cannot have accepted_at."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        if isinstance(self.currency, str):
            self.currency = self.currency.strip().upper()

        for field_name in ("lead_time_text", "internal_notes", "customer_message"):
            value = getattr(self, field_name)
            if isinstance(value, str):
                setattr(self, field_name, value.strip())

        if not self.reference_code:
            self.reference_code = self.generate_reference_code()

        self.full_clean()
        super().save(*args, **kwargs)


class InquiryOfferPayment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    REFERENCE_PREFIX = "PAY"
    REFERENCE_RANDOM_LENGTH = 6
    REFERENCE_ALLOWED_CHARS = string.ascii_uppercase + string.digits
    STATUS_TRANSITIONS = {
        Status.PENDING: (Status.PAID, Status.FAILED, Status.CANCELLED),
        Status.PAID: (),
        Status.FAILED: (),
        Status.CANCELLED: (),
    }

    offer = models.OneToOneField(
        "inquiries.InquiryOffer",
        on_delete=models.CASCADE,
        related_name="payment",
    )
    reference_code = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        editable=False,
    )
    payable_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    provider = models.CharField(max_length=24, default="manual")
    provider_reference = models.CharField(max_length=128, blank=True)
    internal_notes = models.TextField(blank=True)
    initiated_at = models.DateTimeField(null=True, blank=True, db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True, db_index=True)
    failed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    cancelled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(payable_amount__gt=0),
                name="inq_offer_payment_amount_gt_0_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=["status", "initiated_at"],
                name="inq_pay_status_init_idx",
            ),
            models.Index(
                fields=["status", "created_at"],
                name="inq_pay_status_created_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.reference_code

    @classmethod
    def allowed_next_statuses(cls, current_status: str) -> tuple[str, ...]:
        return cls.STATUS_TRANSITIONS.get(current_status, ())

    def can_transition_to(self, next_status: str) -> bool:
        return next_status in self.allowed_next_statuses(self.status)

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
        raise RuntimeError("Unable to generate a unique inquiry offer payment reference code.")

    @classmethod
    def initiate_from_offer(
        cls,
        offer: InquiryOffer,
        *,
        provider: str = "manual",
        provider_reference: str = "",
        internal_notes: str = "",
        save: bool = True,
    ) -> InquiryOfferPayment:
        if offer.status != InquiryOffer.Status.ACCEPTED:
            raise ValueError("Payment can only be initiated for accepted offers.")

        if cls.objects.filter(offer_id=offer.pk).exists():
            raise ValidationError(
                {"offer": "A payment record already exists for this offer."}
            )

        payment = cls(
            offer=offer,
            payable_amount=offer.confirmed_total,
            currency=offer.currency,
            status=cls.Status.PENDING,
            provider=provider,
            provider_reference=provider_reference,
            internal_notes=internal_notes,
            initiated_at=timezone.now(),
        )
        if save:
            with transaction.atomic():
                payment.save()
        else:
            payment.full_clean()
        return payment

    @classmethod
    def ensure_pending_from_offer(
        cls,
        offer: InquiryOffer,
        *,
        provider: str = "manual",
        provider_reference: str = "",
        internal_notes: str = "",
        save: bool = True,
    ) -> InquiryOfferPayment:
        if offer.status != InquiryOffer.Status.ACCEPTED:
            raise ValueError("Payment can only be initiated for accepted offers.")

        if offer.pk is None:
            raise ValueError("Accepted offer must be persisted before preparing payment.")

        existing_payment = cls.objects.filter(offer_id=offer.pk).first()
        if existing_payment is not None:
            return existing_payment

        payment = cls(
            offer=offer,
            payable_amount=offer.confirmed_total,
            currency=offer.currency,
            status=cls.Status.PENDING,
            provider=provider,
            provider_reference=provider_reference,
            internal_notes=internal_notes,
            initiated_at=timezone.now(),
        )
        if not save:
            payment.full_clean()
            return payment

        with transaction.atomic():
            existing_payment = cls.objects.select_for_update().filter(offer_id=offer.pk).first()
            if existing_payment is not None:
                return existing_payment

            try:
                payment.save()
            except IntegrityError:
                return cls.objects.get(offer_id=offer.pk)
        return payment

    def mark_paid(self, *, save: bool = True) -> None:
        if not self.can_transition_to(self.Status.PAID):
            raise ValueError("Only pending payments can transition to paid.")

        now = timezone.now()
        self.status = self.Status.PAID
        self.initiated_at = self.initiated_at or now
        self.paid_at = now
        self.failed_at = None
        self.cancelled_at = None

        if save:
            with transaction.atomic():
                self.save()

    def mark_failed(self, *, save: bool = True) -> None:
        if not self.can_transition_to(self.Status.FAILED):
            raise ValueError("Only pending payments can transition to failed.")

        now = timezone.now()
        self.status = self.Status.FAILED
        self.initiated_at = self.initiated_at or now
        self.failed_at = now
        self.paid_at = None
        self.cancelled_at = None

        if save:
            with transaction.atomic():
                self.save()

    def mark_cancelled(self, *, save: bool = True) -> None:
        if not self.can_transition_to(self.Status.CANCELLED):
            raise ValueError("Only pending payments can transition to cancelled.")

        now = timezone.now()
        self.status = self.Status.CANCELLED
        self.initiated_at = self.initiated_at or now
        self.cancelled_at = now
        self.paid_at = None
        self.failed_at = None

        if save:
            with transaction.atomic():
                self.save()

    def clean(self) -> None:
        super().clean()
        errors = {}

        if self.offer_id and self.offer.status != InquiryOffer.Status.ACCEPTED:
            errors["offer"] = "Payment records can only be created from accepted offers."

        if not self.currency:
            errors["currency"] = "Currency is required."
        elif len(self.currency) != 3:
            errors["currency"] = "Currency must be a 3-letter code."

        if self.status == self.Status.PENDING:
            if self.initiated_at is None:
                errors["initiated_at"] = "Pending payments must define initiated_at."
            if self.paid_at is not None:
                errors["paid_at"] = "Pending payments cannot define paid_at."
            if self.failed_at is not None:
                errors["failed_at"] = "Pending payments cannot define failed_at."
            if self.cancelled_at is not None:
                errors["cancelled_at"] = "Pending payments cannot define cancelled_at."
        elif self.status == self.Status.PAID:
            if self.initiated_at is None:
                errors["initiated_at"] = "Paid payments must define initiated_at."
            if self.paid_at is None:
                errors["paid_at"] = "Paid payments must define paid_at."
            if self.failed_at is not None:
                errors["failed_at"] = "Paid payments cannot define failed_at."
            if self.cancelled_at is not None:
                errors["cancelled_at"] = "Paid payments cannot define cancelled_at."
        elif self.status == self.Status.FAILED:
            if self.initiated_at is None:
                errors["initiated_at"] = "Failed payments must define initiated_at."
            if self.failed_at is None:
                errors["failed_at"] = "Failed payments must define failed_at."
            if self.paid_at is not None:
                errors["paid_at"] = "Failed payments cannot define paid_at."
            if self.cancelled_at is not None:
                errors["cancelled_at"] = "Failed payments cannot define cancelled_at."
        elif self.status == self.Status.CANCELLED:
            if self.initiated_at is None:
                errors["initiated_at"] = "Cancelled payments must define initiated_at."
            if self.cancelled_at is None:
                errors["cancelled_at"] = "Cancelled payments must define cancelled_at."
            if self.paid_at is not None:
                errors["paid_at"] = "Cancelled payments cannot define paid_at."
            if self.failed_at is not None:
                errors["failed_at"] = "Cancelled payments cannot define failed_at."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        if isinstance(self.currency, str):
            self.currency = self.currency.strip().upper()

        for field_name in ("provider", "provider_reference", "internal_notes"):
            value = getattr(self, field_name)
            if isinstance(value, str):
                setattr(self, field_name, value.strip())

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
