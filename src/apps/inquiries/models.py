from __future__ import annotations

import string
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField


def _normalize_destination(
    country: object,
    city: str,
    region: str,
    postal_code: str,
) -> tuple[str, str, str, str]:
    return (
        str(country or "").strip().upper(),
        city.strip(),
        region.strip(),
        postal_code.strip(),
    )


class InquirySubmissionGroup(models.Model):
    class Language(models.TextChoices):
        SPANISH = "es", _("Español")
        ENGLISH = "en", _("Inglés")

    REFERENCE_PREFIX = "REQ"
    REFERENCE_RANDOM_LENGTH = 6
    REFERENCE_ALLOWED_CHARS = string.ascii_uppercase + string.digits

    reference_code = models.CharField(
        _("código de referencia"),
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
        related_name="inquiry_submission_groups",
        verbose_name=_("usuario"),
    )
    guest_name = models.CharField(_("nombre del cliente"), max_length=150, blank=True)
    guest_email = models.EmailField(_("correo electrónico del cliente"), blank=True)
    guest_phone = models.CharField(_("teléfono del cliente"), max_length=50, blank=True)
    company_name = models.CharField(_("empresa"), max_length=180, blank=True)
    tax_id = models.CharField(_("NIF / VAT"), max_length=64, blank=True)
    language = models.CharField(
        _("idioma"),
        max_length=5,
        choices=Language.choices,
        default=Language.SPANISH,
    )
    notes_from_customer = models.TextField(_("notas del cliente"), blank=True)
    destination_country = CountryField(_("país de destino"), blank=True, null=True)
    destination_city = models.CharField(_("ciudad de destino"), max_length=120, blank=True)
    destination_region = models.CharField(_("provincia o región"), max_length=120, blank=True)
    destination_postal_code = models.CharField(
        _("código postal de destino"), max_length=32, blank=True
    )
    created_at = models.DateTimeField(_("creado el"), auto_now_add=True)
    updated_at = models.DateTimeField(_("actualizado el"), auto_now=True)

    class Meta:
        verbose_name = _("grupo de solicitudes")
        verbose_name_plural = _("grupos de solicitudes")
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(user__isnull=False)
                | (Q(guest_name__gt="") & Q(guest_email__gt="")),
                name="inq_group_user_or_guest_contact_ck",
            )
        ]
        indexes = [
            models.Index(fields=["user", "created_at"], name="inq_group_user_created_idx"),
            models.Index(fields=["guest_email"], name="inq_group_guest_email_idx"),
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
    def generate_reference_code(cls) -> str:
        date_part = timezone.localdate().strftime("%Y%m%d")
        for _attempt_index in range(50):
            suffix = get_random_string(
                cls.REFERENCE_RANDOM_LENGTH,
                allowed_chars=cls.REFERENCE_ALLOWED_CHARS,
            )
            reference_code = f"{cls.REFERENCE_PREFIX}-{date_part}-{suffix}"
            if not cls.objects.filter(reference_code=reference_code).exists():
                return reference_code
        raise RuntimeError("Unable to generate a unique submission group reference code.")

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

    def save(self, *args, **kwargs) -> None:
        for field_name in (
            "guest_name",
            "guest_email",
            "guest_phone",
            "company_name",
            "tax_id",
            "notes_from_customer",
            "destination_region",
            "destination_city",
            "destination_postal_code",
        ):
            value = getattr(self, field_name)
            if isinstance(value, str):
                setattr(self, field_name, value.strip())

        if self.guest_email:
            self.guest_email = self.guest_email.lower()
        self.destination_country = str(self.destination_country or "").strip().upper() or None
        if not self.reference_code:
            self.reference_code = self.generate_reference_code()

        self.full_clean()
        super().save(*args, **kwargs)


class Inquiry(models.Model):
    class Language(models.TextChoices):
        SPANISH = "es", _("Español")
        ENGLISH = "en", _("Inglés")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Borrador")
        SUBMITTED = "submitted", _("Enviada")
        IN_REVIEW = "in_review", _("En revisión")
        SUPPLIER_PENDING = "supplier_pending", _("Pendiente del proveedor")
        RESPONDED = "responded", _("Respondida al cliente")
        ACCEPTED = "accepted", _("Aceptada por el cliente")
        REJECTED = "rejected", _("Rechazada por el cliente")
        CLOSED = "closed", _("Cerrada")

    class NegativeResolutionReason(models.TextChoices):
        UNAVAILABLE = "unavailable", _("No disponible")
        SUPPLIER_CANNOT_CONFIRM = "supplier_cannot_confirm", _("El proveedor no puede confirmar")
        LOGISTICS_NOT_POSSIBLE = "logistics_not_possible", _("Logística no viable")
        OTHER = "other", _("Otro motivo")

    REFERENCE_PREFIX = "INQ"
    REFERENCE_RANDOM_LENGTH = 6
    REFERENCE_ALLOWED_CHARS = string.ascii_uppercase + string.digits
    STATUS_TRANSITIONS = {
        Status.DRAFT: (Status.SUBMITTED, Status.CLOSED),
        Status.SUBMITTED: (Status.IN_REVIEW, Status.SUPPLIER_PENDING, Status.CLOSED),
        Status.IN_REVIEW: (Status.SUPPLIER_PENDING, Status.RESPONDED, Status.CLOSED),
        Status.SUPPLIER_PENDING: (Status.IN_REVIEW, Status.RESPONDED, Status.CLOSED),
        Status.RESPONDED: (Status.ACCEPTED, Status.REJECTED, Status.CLOSED),
        Status.ACCEPTED: (Status.REJECTED, Status.CLOSED),
        Status.REJECTED: (Status.CLOSED,),
        Status.CLOSED: (),
    }

    reference_code = models.CharField(
        _("código de referencia"),
        max_length=32,
        unique=True,
        db_index=True,
        editable=False,
    )
    submission_group = models.ForeignKey(
        "inquiries.InquirySubmissionGroup",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="inquiries",
        verbose_name=_("grupo de solicitudes"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inquiries",
        verbose_name=_("usuario"),
    )
    guest_name = models.CharField(_("nombre del cliente"), max_length=150, blank=True)
    guest_email = models.EmailField(_("correo electrónico del cliente"), blank=True)
    guest_phone = models.CharField(_("teléfono del cliente"), max_length=50, blank=True)
    company_name = models.CharField(_("empresa"), max_length=180, blank=True)
    tax_id = models.CharField(_("NIF / VAT"), max_length=64, blank=True)
    language = models.CharField(
        _("idioma"),
        max_length=5,
        choices=Language.choices,
        default=Language.SPANISH,
    )
    status = models.CharField(
        _("estado"),
        max_length=24,
        choices=Status.choices,
        default=Status.SUBMITTED,
        db_index=True,
    )
    notes_from_customer = models.TextField(_("notas del cliente"), blank=True)
    internal_notes = models.TextField(_("notas internas"), blank=True)
    destination_country = CountryField(_("país de destino"), blank=True, null=True)
    destination_city = models.CharField(_("ciudad de destino"), max_length=120, blank=True)
    destination_region = models.CharField(_("provincia o región"), max_length=120, blank=True)
    destination_postal_code = models.CharField(
        _("código postal de destino"), max_length=32, blank=True
    )
    negative_resolution_reason = models.CharField(
        _("motivo de resolución no ofertable"),
        max_length=40,
        choices=NegativeResolutionReason.choices,
        blank=True,
        db_index=True,
    )
    negative_resolution_internal_notes = models.TextField(
        _("notas internas de la resolución"), blank=True
    )
    negative_resolution_customer_message = models.TextField(
        _("mensaje de resolución para el cliente"), blank=True
    )
    negative_resolved_at = models.DateTimeField(
        _("resuelta como no ofertable el"), null=True, blank=True, db_index=True
    )
    response_due_at = models.DateTimeField(
        _("fecha límite de respuesta"), null=True, blank=True, db_index=True
    )
    supplier_feedback_at = models.DateTimeField(
        _("respuesta del proveedor recibida el"), null=True, blank=True, db_index=True
    )
    created_at = models.DateTimeField(_("creada el"), auto_now_add=True)
    updated_at = models.DateTimeField(_("actualizada el"), auto_now=True)

    class Meta:
        verbose_name = _("solicitud")
        verbose_name_plural = _("solicitudes")
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
                _("No puede finalizarse la resolución no ofertable porque la solicitud "
                  "ya tiene una oferta.")
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
                    _("Debe indicar el motivo de resolución no ofertable.")
                )
            if self.status != self.Status.CLOSED:
                errors["status"] = (
                    _("La resolución no ofertable requiere que la solicitud esté cerrada.")
                )
            if self.pk and InquiryOffer.objects.filter(inquiry_id=self.pk).exists():
                errors["negative_resolved_at"] = (
                    _("No puede guardarse una resolución no ofertable si ya existe una oferta.")
                )

        if errors:
            raise ValidationError(errors)

    @classmethod
    def generate_reference_code(cls) -> str:
        date_part = timezone.localdate().strftime("%Y%m%d")
        for _attempt_index in range(50):
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
            "destination_region",
            "destination_city",
            "destination_postal_code",
        )
        for field_name in string_fields:
            value = getattr(self, field_name)
            if isinstance(value, str):
                setattr(self, field_name, value.strip())

        if self.guest_email:
            self.guest_email = self.guest_email.lower()
        self.destination_country = str(self.destination_country or "").strip().upper() or None

        if not self.reference_code:
            self.reference_code = self.generate_reference_code()

        self.full_clean()
        super().save(*args, **kwargs)


class InquiryOffer(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Borrador")
        SENT = "sent", _("Enviada al cliente")
        ACCEPTED = "accepted", _("Aceptada por el cliente")
        REJECTED = "rejected", _("Rechazada por el cliente")
        EXPIRED = "expired", _("Caducada")

    REFERENCE_PREFIX = "OFF"
    REFERENCE_RANDOM_LENGTH = 6
    REFERENCE_ALLOWED_CHARS = string.ascii_uppercase + string.digits
    DEFAULT_OFFER_VALIDITY_HOURS = 24
    STATUS_TRANSITIONS = {
        Status.DRAFT: (Status.SENT,),
        Status.SENT: (Status.ACCEPTED, Status.REJECTED, Status.EXPIRED),
        Status.ACCEPTED: (Status.EXPIRED,),
        Status.REJECTED: (),
        Status.EXPIRED: (),
    }

    inquiry = models.OneToOneField(
        "inquiries.Inquiry",
        on_delete=models.CASCADE,
        related_name="offer",
        verbose_name=_("solicitud"),
    )
    reference_code = models.CharField(
        _("código de referencia"),
        max_length=32,
        unique=True,
        db_index=True,
        editable=False,
    )
    status = models.CharField(
        _("estado"),
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    confirmed_total = models.DecimalField(
        _("total confirmado"),
        max_digits=12,
        decimal_places=2,
        help_text=(
            _("Importe comercial final confirmado de la oferta. Es la referencia para "
              "preparar el pago y debe incluir el envío calculado para el destino "
              "cotizado cuando corresponda.")
        ),
    )
    quoted_destination_country = CountryField(_("país cotizado"), blank=True, null=True)
    quoted_destination_city = models.CharField(_("ciudad cotizada"), max_length=120, blank=True)
    quoted_destination_region = models.CharField(
        _("provincia o región cotizada"), max_length=120, blank=True
    )
    quoted_destination_postal_code = models.CharField(
        _("código postal cotizado"), max_length=32, blank=True
    )
    currency = models.CharField(
        _("moneda"),
        max_length=3,
        default="EUR",
        help_text=_("Código ISO 4217 de la moneda del total confirmado."),
    )
    lead_time_text = models.CharField(_("plazo estimado"), max_length=255, blank=True)
    internal_notes = models.TextField(_("notas internas"), blank=True)
    customer_message = models.TextField(_("mensaje para el cliente"), blank=True)
    access_token = models.UUIDField(
        _("token de acceso"), default=uuid.uuid4, unique=True, editable=False, db_index=True
    )
    sent_at = models.DateTimeField(_("enviada el"), null=True, blank=True, db_index=True)
    valid_until = models.DateTimeField(
        _("fecha límite de vigencia"), null=True, blank=True, db_index=True
    )
    validity_hours_snapshot = models.PositiveIntegerField(
        _("horas de vigencia aplicadas"), null=True, blank=True
    )
    accepted_at = models.DateTimeField(_("aceptada el"), null=True, blank=True, db_index=True)
    rejected_at = models.DateTimeField(_("rechazada el"), null=True, blank=True, db_index=True)
    expired_at = models.DateTimeField(_("caducada el"), null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(_("creada el"), auto_now_add=True)
    updated_at = models.DateTimeField(_("actualizada el"), auto_now=True)

    class Meta:
        verbose_name = _("oferta")
        verbose_name_plural = _("ofertas")
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
                fields=["status", "valid_until"],
                name="inq_offer_status_valid_idx",
            ),
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
    def has_complete_quoted_destination(self) -> bool:
        return bool(
            self.quoted_destination_country
            and self.quoted_destination_city
            and self.quoted_destination_region
            and self.quoted_destination_postal_code
        )

    @property
    def quoted_destination_summary(self) -> str:
        if not self.has_complete_quoted_destination:
            return ""
        return ", ".join(
            (
                self.quoted_destination_postal_code,
                self.quoted_destination_city,
                self.quoted_destination_region,
                self.quoted_destination_country.name,
            )
        )

    @property
    def has_payment_record(self) -> bool:
        if not self.pk:
            return False
        return InquiryOfferPayment.objects.filter(offer_id=self.pk).exists()

    @property
    def is_validity_expired(self) -> bool:
        if self.status not in {self.Status.SENT, self.Status.ACCEPTED}:
            return False
        if self.valid_until is None:
            return False
        return timezone.now() >= self.valid_until

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
        for _attempt_index in range(50):
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

    @classmethod
    def resolve_validity_hours_for_inquiry(cls, inquiry: Inquiry) -> int:
        candidates = [
            hours
            for hours in inquiry.items.values_list(
                "product__supplier__offer_validity_hours", flat=True
            ).distinct()
            if isinstance(hours, int) and hours > 0
        ]
        return min(candidates) if candidates else cls.DEFAULT_OFFER_VALIDITY_HOURS

    def mark_sent(self, *, save: bool = True) -> None:
        if not self.can_transition_to(self.Status.SENT):
            raise ValueError("Only draft offers can be sent to the customer.")
        errors = self._build_send_validation_errors()
        if errors:
            raise ValidationError(errors)

        destination = _normalize_destination(
            self.inquiry.destination_country,
            self.inquiry.destination_city,
            self.inquiry.destination_region,
            self.inquiry.destination_postal_code,
        )
        if not all(destination):
            raise ValidationError(
                {"inquiry": "A complete quotation destination is required before sending."}
            )
        self.quoted_destination_country = destination[0]
        self.quoted_destination_city = destination[1]
        self.quoted_destination_region = destination[2]
        self.quoted_destination_postal_code = destination[3]
        now = timezone.now()
        validity_hours_snapshot = self.resolve_validity_hours_for_inquiry(self.inquiry)
        self.status = self.Status.SENT
        self.sent_at = now
        self.valid_until = now + timedelta(hours=validity_hours_snapshot)
        self.validity_hours_snapshot = validity_hours_snapshot
        self.accepted_at = None
        self.rejected_at = None
        self.expired_at = None

        if save:
            with transaction.atomic():
                self.save()
                self._sync_inquiry_status(Inquiry.Status.RESPONDED)

    def mark_accepted(self, *, save: bool = True) -> None:
        if not self.can_transition_to(self.Status.ACCEPTED):
            raise ValueError("Only sent offers can be accepted by the customer.")
        if self.is_validity_expired:
            raise ValueError("Offer validity has expired.")

        now = timezone.now()
        if not self.validity_hours_snapshot:
            validity_hours_snapshot = self.resolve_validity_hours_for_inquiry(self.inquiry)
            self.validity_hours_snapshot = validity_hours_snapshot
            if self.valid_until is None:
                sent_anchor = self.sent_at or now
                self.valid_until = sent_anchor + timedelta(hours=validity_hours_snapshot)

        self.status = self.Status.ACCEPTED
        self.sent_at = self.sent_at or now
        self.accepted_at = now
        self.rejected_at = None
        self.expired_at = None

        if save:
            with transaction.atomic():
                self.save()
                self._sync_inquiry_status(Inquiry.Status.ACCEPTED)
                InquiryOfferPayment.ensure_pending_from_offer(self, save=True)

    def mark_rejected(self, *, save: bool = True) -> None:
        if not self.can_transition_to(self.Status.REJECTED):
            raise ValueError("Only sent offers can be rejected by the customer.")
        if self.is_validity_expired:
            raise ValueError("Offer validity has expired.")

        now = timezone.now()
        if not self.validity_hours_snapshot:
            validity_hours_snapshot = self.resolve_validity_hours_for_inquiry(self.inquiry)
            self.validity_hours_snapshot = validity_hours_snapshot
            if self.valid_until is None:
                sent_anchor = self.sent_at or now
                self.valid_until = sent_anchor + timedelta(hours=validity_hours_snapshot)

        self.status = self.Status.REJECTED
        self.sent_at = self.sent_at or now
        self.rejected_at = now
        self.accepted_at = None
        self.expired_at = None

        if save:
            with transaction.atomic():
                self.save()
                self._sync_inquiry_status(Inquiry.Status.REJECTED)

    def mark_expired(self, *, save: bool = True) -> None:
        if not self.can_transition_to(self.Status.EXPIRED):
            raise ValueError("Only sent or accepted offers can be expired.")

        now = timezone.now()
        was_accepted = self.status == self.Status.ACCEPTED
        if not self.validity_hours_snapshot:
            self.validity_hours_snapshot = self.resolve_validity_hours_for_inquiry(self.inquiry)
        self.status = self.Status.EXPIRED
        self.sent_at = self.sent_at or now
        if self.valid_until is None:
            self.valid_until = self.sent_at + timedelta(hours=self.validity_hours_snapshot)
        self.expired_at = now
        if not was_accepted:
            self.accepted_at = None
        self.rejected_at = None

        if save:
            with transaction.atomic():
                payment = InquiryOfferPayment.objects.filter(offer_id=self.pk).first()
                if payment is not None and payment.status == InquiryOfferPayment.Status.PENDING:
                    payment.mark_cancelled(save=True)
                self.save()
                self._sync_inquiry_status(Inquiry.Status.REJECTED)

    def clean(self) -> None:
        super().clean()
        errors = {}

        if self.inquiry_id and self.inquiry.is_negatively_resolved:
            errors["inquiry"] = (
                "Offers cannot be created or updated for an inquiry resolved as not offerable."
            )

        quoted_destination = _normalize_destination(
            self.quoted_destination_country,
            self.quoted_destination_city,
            self.quoted_destination_region,
            self.quoted_destination_postal_code,
        )
        if any(quoted_destination) and not all(quoted_destination):
            errors["quoted_destination_country"] = (
                "Quoted destination country, city, region and postal code must be "
                "completed together."
            )
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).first()
            if previous and previous.has_complete_quoted_destination:
                previous_destination = _normalize_destination(
                    previous.quoted_destination_country,
                    previous.quoted_destination_city,
                    previous.quoted_destination_region,
                    previous.quoted_destination_postal_code,
                )
                if quoted_destination != previous_destination:
                    errors["quoted_destination_country"] = (
                        "The quoted destination snapshot cannot be changed once established."
                    )

        if not self.currency:
            errors["currency"] = "Currency is required."
        elif len(self.currency) != 3:
            errors["currency"] = "Currency must be a 3-letter code."

        if (
            self.pk
            and self.status not in {self.Status.ACCEPTED, self.Status.EXPIRED}
            and InquiryOfferPayment.objects.filter(offer_id=self.pk).exists()
        ):
            errors["status"] = (
                "Offers with an initiated payment record must stay accepted or expired."
            )

        if self.status == self.Status.DRAFT:
            if self.sent_at is not None:
                errors["sent_at"] = "Draft offers cannot have sent_at."
            if self.valid_until is not None:
                errors["valid_until"] = (
                    "Draft offers cannot define valid_until."
                )
            if self.validity_hours_snapshot is not None:
                errors["validity_hours_snapshot"] = (
                    "Draft offers cannot define validity_hours_snapshot."
                )
            if self.accepted_at is not None:
                errors["accepted_at"] = "Draft offers cannot have accepted_at."
            if self.rejected_at is not None:
                errors["rejected_at"] = "Draft offers cannot have rejected_at."
            if self.expired_at is not None:
                errors["expired_at"] = "Draft offers cannot have expired_at."
        elif self.status == self.Status.SENT:
            if self.sent_at is None:
                errors["sent_at"] = "Sent offers must define sent_at."
            if self.valid_until is None:
                errors["valid_until"] = "Sent offers must define valid_until."
            if self.validity_hours_snapshot is None:
                errors["validity_hours_snapshot"] = (
                    "Sent offers must define validity_hours_snapshot."
                )
            if self.accepted_at is not None:
                errors["accepted_at"] = "Sent offers cannot have accepted_at."
            if self.rejected_at is not None:
                errors["rejected_at"] = "Sent offers cannot have rejected_at."
            if self.expired_at is not None:
                errors["expired_at"] = "Sent offers cannot have expired_at."
        elif self.status == self.Status.ACCEPTED:
            if self.sent_at is None:
                errors["sent_at"] = "Accepted offers must define sent_at."
            if self.valid_until is None:
                errors["valid_until"] = "Accepted offers must define valid_until."
            if self.validity_hours_snapshot is None:
                errors["validity_hours_snapshot"] = (
                    "Accepted offers must define validity_hours_snapshot."
                )
            if self.accepted_at is None:
                errors["accepted_at"] = "Accepted offers must define accepted_at."
            if self.rejected_at is not None:
                errors["rejected_at"] = "Accepted offers cannot have rejected_at."
            if self.expired_at is not None:
                errors["expired_at"] = "Accepted offers cannot have expired_at."
        elif self.status == self.Status.REJECTED:
            if self.sent_at is None:
                errors["sent_at"] = "Rejected offers must define sent_at."
            if self.valid_until is None:
                errors["valid_until"] = "Rejected offers must define valid_until."
            if self.validity_hours_snapshot is None:
                errors["validity_hours_snapshot"] = (
                    "Rejected offers must define validity_hours_snapshot."
                )
            if self.rejected_at is None:
                errors["rejected_at"] = "Rejected offers must define rejected_at."
            if self.accepted_at is not None:
                errors["accepted_at"] = "Rejected offers cannot have accepted_at."
            if self.expired_at is not None:
                errors["expired_at"] = "Rejected offers cannot have expired_at."
        elif self.status == self.Status.EXPIRED:
            if self.sent_at is None:
                errors["sent_at"] = "Expired offers must define sent_at."
            if self.valid_until is None:
                errors["valid_until"] = "Expired offers must define valid_until."
            if self.validity_hours_snapshot is None:
                errors["validity_hours_snapshot"] = (
                    "Expired offers must define validity_hours_snapshot."
                )
            if self.expired_at is None:
                errors["expired_at"] = "Expired offers must define expired_at."
            if self.rejected_at is not None:
                errors["rejected_at"] = "Expired offers cannot have rejected_at."

        if (
            self.validity_hours_snapshot is not None
            and self.validity_hours_snapshot < 1
        ):
            errors["validity_hours_snapshot"] = (
                _("La vigencia aplicada debe ser de al menos una hora.")
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        if isinstance(self.currency, str):
            self.currency = self.currency.strip().upper()

        for field_name in ("lead_time_text", "internal_notes", "customer_message"):
            value = getattr(self, field_name)
            if isinstance(value, str):
                setattr(self, field_name, value.strip())
        self.quoted_destination_country = (
            str(self.quoted_destination_country or "").strip().upper() or None
        )
        self.quoted_destination_region = self.quoted_destination_region.strip()
        self.quoted_destination_city = self.quoted_destination_city.strip()
        self.quoted_destination_postal_code = self.quoted_destination_postal_code.strip()

        if not self.reference_code:
            self.reference_code = self.generate_reference_code()

        self.full_clean()
        super().save(*args, **kwargs)


class InquiryOfferPayment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pendiente")
        PAID = "paid", _("Pagado")
        FAILED = "failed", _("Fallido")
        CANCELLED = "cancelled", _("Cancelado")

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
        verbose_name=_("oferta"),
    )
    reference_code = models.CharField(
        _("código de referencia"),
        max_length=32,
        unique=True,
        db_index=True,
        editable=False,
    )
    payable_amount = models.DecimalField(_("importe a pagar"), max_digits=12, decimal_places=2)
    currency = models.CharField(_("moneda"), max_length=3, default="EUR")
    status = models.CharField(
        _("estado"),
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    provider = models.CharField(_("proveedor de pago"), max_length=24, default="manual")
    provider_reference = models.CharField(_("referencia del proveedor"), max_length=128, blank=True)
    internal_notes = models.TextField(_("notas internas"), blank=True)
    initiated_at = models.DateTimeField(_("iniciado el"), null=True, blank=True, db_index=True)
    paid_at = models.DateTimeField(_("pagado el"), null=True, blank=True, db_index=True)
    failed_at = models.DateTimeField(_("fallido el"), null=True, blank=True, db_index=True)
    cancelled_at = models.DateTimeField(_("cancelado el"), null=True, blank=True, db_index=True)
    checkout_expires_at = models.DateTimeField(
        _("vencimiento de la sesión de pago"), null=True, blank=True, db_index=True
    )
    created_at = models.DateTimeField(_("creado el"), auto_now_add=True)
    updated_at = models.DateTimeField(_("actualizado el"), auto_now=True)

    class Meta:
        verbose_name = _("pago")
        verbose_name_plural = _("pagos")
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
            models.Index(
                fields=["status", "checkout_expires_at"],
                name="inq_pay_status_checkout_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.reference_code

    @classmethod
    def allowed_next_statuses(cls, current_status: str) -> tuple[str, ...]:
        return cls.STATUS_TRANSITIONS.get(current_status, ())

    def can_transition_to(self, next_status: str) -> bool:
        return next_status in self.allowed_next_statuses(self.status)

    @property
    def is_checkout_expired(self) -> bool:
        if self.status != self.Status.PENDING:
            return False
        if self.checkout_expires_at is None:
            return False
        return timezone.now() >= self.checkout_expires_at

    @classmethod
    def generate_reference_code(cls) -> str:
        date_part = timezone.localdate().strftime("%Y%m%d")
        for _attempt_index in range(50):
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
            checkout_expires_at=None,
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
            checkout_expires_at=None,
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

        if self.offer_id and self.offer.status not in {
            InquiryOffer.Status.ACCEPTED,
            InquiryOffer.Status.EXPIRED,
        }:
            errors["offer"] = "Payment records can only belong to accepted or expired offers."

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


class InquiryOfferPaymentDetails(models.Model):
    class BillingCustomerType(models.TextChoices):
        PRIVATE = "private", _("Particular")
        COMPANY = "company", _("Empresa o profesional")

    payment = models.OneToOneField(
        "inquiries.InquiryOfferPayment",
        on_delete=models.CASCADE,
        related_name="checkout_details",
        verbose_name=_("pago"),
    )
    shipping_recipient_name = models.CharField(_("destinatario del envío"), max_length=180)
    shipping_phone = models.CharField(_("teléfono de envío"), max_length=50)
    shipping_address_line_1 = models.CharField(_("dirección de envío"), max_length=255)
    shipping_address_line_2 = models.CharField(
        _("información adicional de envío"), max_length=255, blank=True
    )
    shipping_city = models.CharField(_("ciudad de envío"), max_length=120)
    shipping_region = models.CharField(_("provincia o región de envío"), max_length=120)
    shipping_postal_code = models.CharField(_("código postal de envío"), max_length=32)
    shipping_country = CountryField(_("país de envío"))
    billing_customer_type = models.CharField(
        _("tipo de cliente de facturación"),
        max_length=16,
        choices=BillingCustomerType.choices,
        default=BillingCustomerType.PRIVATE,
    )
    billing_same_as_shipping = models.BooleanField(
        _("facturación igual que envío"), default=True
    )
    billing_name = models.CharField(_("nombre o razón social de facturación"), max_length=180)
    billing_tax_id = models.CharField(_("NIF / VAT de facturación"), max_length=64)
    billing_address_line_1 = models.CharField(_("dirección de facturación"), max_length=255)
    billing_address_line_2 = models.CharField(
        _("información adicional de facturación"), max_length=255, blank=True
    )
    billing_city = models.CharField(_("ciudad de facturación"), max_length=120)
    billing_region = models.CharField(
        _("provincia o región de facturación"), max_length=120
    )
    billing_postal_code = models.CharField(_("código postal de facturación"), max_length=32)
    billing_country = CountryField(_("país de facturación"))
    completed_at = models.DateTimeField(_("completado el"), null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(_("creado el"), auto_now_add=True)
    updated_at = models.DateTimeField(_("actualizado el"), auto_now=True)

    class Meta:
        verbose_name = _("datos de envío y facturación")
        verbose_name_plural = _("datos de envío y facturación")

    def __str__(self) -> str:
        return f"Checkout details for {self.payment.reference_code}"

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None

    @property
    def matches_quoted_destination(self) -> bool:
        offer = self.payment.offer
        return offer.has_complete_quoted_destination and _normalize_destination(
            self.shipping_country,
            self.shipping_city,
            self.shipping_region,
            self.shipping_postal_code,
        ) == _normalize_destination(
            offer.quoted_destination_country,
            offer.quoted_destination_city,
            offer.quoted_destination_region,
            offer.quoted_destination_postal_code,
        )

    @property
    def delivery_destination_summary(self) -> str:
        return ", ".join(
            value
            for value in (
                self.shipping_city,
                self.shipping_postal_code,
                self.shipping_region,
                self.shipping_country.name,
            )
            if value
        )

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        required_shipping = (
            "shipping_recipient_name",
            "shipping_phone",
            "shipping_address_line_1",
            "shipping_city",
            "shipping_region",
            "shipping_postal_code",
            "shipping_country",
        )
        for field_name in required_shipping:
            if not getattr(self, field_name):
                errors[field_name] = "This shipping field is required."
        if not self.billing_name:
            errors["billing_name"] = "Billing name is required."
        if not self.billing_tax_id:
            errors["billing_tax_id"] = "Tax/VAT identifier is required for billing."
        for field_name in (
            "billing_address_line_1",
            "billing_city",
            "billing_region",
            "billing_postal_code",
            "billing_country",
        ):
            if not getattr(self, field_name):
                errors[field_name] = "This billing field is required."
        if self.payment_id and not self.matches_quoted_destination:
            errors["shipping_country"] = (
                "Shipping country, region and postal code must match the quoted destination."
            )
        if self.pk:
            previous = type(self).objects.select_related("payment").get(pk=self.pk)
            if previous.payment.status == InquiryOfferPayment.Status.PAID:
                for field in self._meta.concrete_fields:
                    if field.name not in {"id", "created_at", "updated_at"} and (
                        getattr(previous, field.name) != getattr(self, field.name)
                    ):
                        errors["__all__"] = "Paid checkout details are an immutable snapshot."
                        break
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        string_fields = (
            "shipping_recipient_name",
            "shipping_phone",
            "shipping_address_line_1",
            "shipping_address_line_2",
            "shipping_city",
            "shipping_region",
            "shipping_postal_code",
            "billing_name",
            "billing_tax_id",
            "billing_address_line_1",
            "billing_address_line_2",
            "billing_city",
            "billing_region",
            "billing_postal_code",
        )
        for field_name in string_fields:
            setattr(self, field_name, (getattr(self, field_name) or "").strip())
        self.shipping_country = str(self.shipping_country or "").strip().upper()
        self.billing_country = str(self.billing_country or "").strip().upper()
        if self.billing_same_as_shipping:
            self.billing_address_line_1 = self.shipping_address_line_1
            self.billing_address_line_2 = self.shipping_address_line_2
            self.billing_city = self.shipping_city
            self.billing_region = self.shipping_region
            self.billing_postal_code = self.shipping_postal_code
            self.billing_country = self.shipping_country
        self.full_clean()
        super().save(*args, **kwargs)


class InquiryItem(models.Model):
    inquiry = models.ForeignKey(
        "inquiries.Inquiry",
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("solicitud"),
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="inquiry_items",
        verbose_name=_("producto"),
    )
    requested_quantity = models.PositiveIntegerField(_("cantidad solicitada"), default=1)
    customer_note = models.TextField(_("nota del cliente"), blank=True)
    last_known_price_snapshot = models.DecimalField(
        _("último precio conocido al solicitar"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(_("creado el"), auto_now_add=True)
    updated_at = models.DateTimeField(_("actualizado el"), auto_now=True)

    class Meta:
        verbose_name = _("artículo solicitado")
        verbose_name_plural = _("artículos solicitados")
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
