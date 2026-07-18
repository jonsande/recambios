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
    expired_payment_ids = _expired_payment_ids(expired_offer_ids)
    payment_offer_ids = _offer_ids_with_payments(expired_payment_ids)
    _send_offer_expired_notifications(
        [offer_id for offer_id in expired_offer_ids if offer_id not in payment_offer_ids]
    )
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
    expired_payment_ids = _expired_payment_ids(expired_offer_ids)
    if expired_payment_ids:
        _send_payment_expired_notifications(expired_payment_ids)
    else:
        _send_offer_expired_notifications(expired_offer_ids)
    return True


def expire_payment_if_due(payment: InquiryOfferPayment, *, now=None) -> bool:
    reference_now = now or timezone.now()
    expired_offer_ids = _expire_due_offers(reference_now, offer_ids=[payment.offer_id])
    if not expired_offer_ids:
        return False
    expired_payment_ids = _expired_payment_ids(expired_offer_ids)
    payment_offer_ids = _offer_ids_with_payments(expired_payment_ids)
    _send_offer_expired_notifications(
        [offer_id for offer_id in expired_offer_ids if offer_id not in payment_offer_ids]
    )
    _send_payment_expired_notifications(expired_payment_ids)
    return True


def _expire_due_offers(reference_now, *, offer_ids: list[int | None] | None = None) -> list[int]:
    queryset = (
        InquiryOffer.objects.select_related("inquiry")
        .select_for_update()
        .filter(
            status__in=[InquiryOffer.Status.SENT, InquiryOffer.Status.ACCEPTED],
            valid_until__isnull=False,
            valid_until__lte=reference_now,
        )
    )
    if offer_ids is not None:
        valid_offer_ids = [offer_id for offer_id in offer_ids if isinstance(offer_id, int)]
        if not valid_offer_ids:
            return []
        queryset = queryset.filter(pk__in=valid_offer_ids)

    expired_offer_ids: list[int] = []
    with transaction.atomic():
        for offer in queryset:
            payment = getattr(offer, "payment", None)
            if (
                offer.status == InquiryOffer.Status.ACCEPTED
                and payment is not None
                and payment.status == InquiryOfferPayment.Status.PENDING
                and payment.checkout_expires_at is not None
                and payment.checkout_expires_at > reference_now
            ):
                continue
            try:
                offer.mark_expired(save=True)
            except ValueError:
                continue
            expired_offer_ids.append(offer.pk)

    return expired_offer_ids


def _expired_payment_ids(expired_offer_ids: list[int]) -> list[int]:
    return list(
        InquiryOfferPayment.objects.filter(
            offer_id__in=expired_offer_ids,
            status=InquiryOfferPayment.Status.CANCELLED,
        ).values_list("id", flat=True)
    )


def _offer_ids_with_payments(payment_ids: list[int]) -> set[int]:
    return set(
        InquiryOfferPayment.objects.filter(pk__in=payment_ids).values_list(
            "offer_id", flat=True
        )
    )


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
