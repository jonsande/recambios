from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from .emails import (
    send_customer_offer_expired_email,
    send_customer_payment_expired_email,
    send_internal_offer_expired_notification_email,
    send_internal_payment_expired_notification_email,
    send_supplier_offer_expired_notifications,
    send_supplier_payment_expired_notifications,
)
from .models import InquiryOffer, InquiryOfferPayment

logger = logging.getLogger(__name__)


def expire_due_inquiry_deadlines(*, now=None) -> dict[str, int]:
    reference_now = now or timezone.now()
    expired_offer_ids = _expire_due_offers(reference_now)
    expired_payment_ids = _expire_due_payments(reference_now)
    _send_offer_expired_notifications(expired_offer_ids)
    _send_payment_expired_notifications(expired_payment_ids)
    return {
        "offers_expired": len(expired_offer_ids),
        "payments_expired": len(expired_payment_ids),
    }


def expire_offer_if_due(offer: InquiryOffer, *, now=None) -> bool:
    reference_now = now or timezone.now()
    expired_offer_ids = _expire_due_offers(reference_now, offer_ids=[offer.pk])
    if not expired_offer_ids:
        return False
    _send_offer_expired_notifications(expired_offer_ids)
    return True


def expire_payment_if_due(payment: InquiryOfferPayment, *, now=None) -> bool:
    reference_now = now or timezone.now()
    expired_payment_ids = _expire_due_payments(reference_now, payment_ids=[payment.pk])
    if not expired_payment_ids:
        return False
    _send_payment_expired_notifications(expired_payment_ids)
    return True


def _expire_due_offers(reference_now, *, offer_ids: list[int | None] | None = None) -> list[int]:
    queryset = InquiryOffer.objects.select_related("inquiry").select_for_update().filter(
        status=InquiryOffer.Status.SENT,
        offer_response_deadline_at__isnull=False,
        offer_response_deadline_at__lte=reference_now,
    )
    if offer_ids is not None:
        valid_offer_ids = [offer_id for offer_id in offer_ids if isinstance(offer_id, int)]
        if not valid_offer_ids:
            return []
        queryset = queryset.filter(pk__in=valid_offer_ids)

    expired_offer_ids: list[int] = []
    with transaction.atomic():
        for offer in queryset:
            try:
                offer.mark_expired(save=True)
            except ValueError:
                continue
            expired_offer_ids.append(offer.pk)

    return expired_offer_ids


def _expire_due_payments(
    reference_now,
    *,
    payment_ids: list[int | None] | None = None,
) -> list[int]:
    queryset = (
        InquiryOfferPayment.objects.select_related("offer", "offer__inquiry")
        .select_for_update()
        .filter(
            status=InquiryOfferPayment.Status.PENDING,
            payment_deadline_at__isnull=False,
            payment_deadline_at__lte=reference_now,
        )
    )
    if payment_ids is not None:
        valid_payment_ids = [
            payment_id for payment_id in payment_ids if isinstance(payment_id, int)
        ]
        if not valid_payment_ids:
            return []
        queryset = queryset.filter(pk__in=valid_payment_ids)

    expired_payment_ids: list[int] = []
    with transaction.atomic():
        for payment in queryset:
            try:
                payment.mark_cancelled(save=True)
            except ValueError:
                continue
            expired_payment_ids.append(payment.pk)

    return expired_payment_ids


def _send_offer_expired_notifications(expired_offer_ids: list[int]) -> None:
    if not expired_offer_ids:
        return
    offers = (
        InquiryOffer.objects.select_related("inquiry", "inquiry__user")
        .filter(pk__in=expired_offer_ids)
        .order_by("id")
    )
    for offer in offers:
        supplier_notifications: list[dict] = []
        try:
            supplier_notifications = send_supplier_offer_expired_notifications(offer)
        except Exception:
            logger.exception(
                (
                    "Failed to process supplier offer-expired notifications "
                    "(offer=%s inquiry=%s)."
                ),
                offer.reference_code,
                offer.inquiry.reference_code,
            )

        try:
            send_internal_offer_expired_notification_email(
                offer,
                supplier_notifications=supplier_notifications,
            )
        except Exception:
            logger.exception(
                (
                    "Failed to send internal offer-expired notification email "
                    "(offer=%s inquiry=%s)."
                ),
                offer.reference_code,
                offer.inquiry.reference_code,
            )

        try:
            send_customer_offer_expired_email(offer)
        except Exception:
            logger.exception(
                (
                    "Failed to send customer offer-expired notification email "
                    "(offer=%s inquiry=%s)."
                ),
                offer.reference_code,
                offer.inquiry.reference_code,
            )


def _send_payment_expired_notifications(expired_payment_ids: list[int]) -> None:
    if not expired_payment_ids:
        return
    payments = (
        InquiryOfferPayment.objects.select_related(
            "offer",
            "offer__inquiry",
            "offer__inquiry__user",
        )
        .filter(pk__in=expired_payment_ids)
        .order_by("id")
    )
    for payment in payments:
        supplier_notifications: list[dict] = []
        try:
            supplier_notifications = send_supplier_payment_expired_notifications(payment)
        except Exception:
            logger.exception(
                (
                    "Failed to process supplier payment-expired notifications "
                    "(payment=%s offer=%s inquiry=%s)."
                ),
                payment.reference_code,
                payment.offer.reference_code,
                payment.offer.inquiry.reference_code,
            )

        try:
            send_internal_payment_expired_notification_email(
                payment,
                supplier_notifications=supplier_notifications,
            )
        except Exception:
            logger.exception(
                (
                    "Failed to send internal payment-expired notification email "
                    "(payment=%s offer=%s inquiry=%s)."
                ),
                payment.reference_code,
                payment.offer.reference_code,
                payment.offer.inquiry.reference_code,
            )

        try:
            send_customer_payment_expired_email(payment)
        except Exception:
            logger.exception(
                (
                    "Failed to send customer payment-expired notification email "
                    "(payment=%s offer=%s inquiry=%s)."
                ),
                payment.reference_code,
                payment.offer.reference_code,
                payment.offer.inquiry.reference_code,
            )
