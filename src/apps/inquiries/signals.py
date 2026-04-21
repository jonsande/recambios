from __future__ import annotations

import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .emails import (
    send_customer_negative_resolution_email,
    send_customer_offer_sent_email,
    send_inquiry_submitted_emails,
    send_internal_offer_response_notification_email,
    send_internal_payment_paid_notification_email,
    send_supplier_offer_sent_notifications,
)
from .models import Inquiry, InquiryOffer, InquiryOfferPayment

STATUS_BEFORE_SAVE_ATTR = "_status_before_save"
NEGATIVE_RESOLVED_AT_BEFORE_SAVE_ATTR = "_negative_resolved_at_before_save"
OFFER_STATUS_BEFORE_SAVE_ATTR = "_offer_status_before_save"
PAYMENT_STATUS_BEFORE_SAVE_ATTR = "_payment_status_before_save"
logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Inquiry)
def cache_inquiry_status_before_save(sender, instance: Inquiry, **kwargs) -> None:
    if instance._state.adding or not instance.pk:
        setattr(instance, STATUS_BEFORE_SAVE_ATTR, None)
        setattr(instance, NEGATIVE_RESOLVED_AT_BEFORE_SAVE_ATTR, None)
        return

    previous_state = (
        sender.objects.filter(pk=instance.pk)
        .values_list("status", "negative_resolved_at")
        .first()
    )
    if previous_state is None:
        previous_status = None
        previous_negative_resolved_at = None
    else:
        previous_status, previous_negative_resolved_at = previous_state
    setattr(instance, STATUS_BEFORE_SAVE_ATTR, previous_status)
    setattr(
        instance,
        NEGATIVE_RESOLVED_AT_BEFORE_SAVE_ATTR,
        previous_negative_resolved_at,
    )


@receiver(post_save, sender=Inquiry)
def send_submission_emails_on_status_entry(
    sender,
    instance: Inquiry,
    created: bool,
    **kwargs,
) -> None:
    previous_status = getattr(instance, STATUS_BEFORE_SAVE_ATTR, None)
    entered_submitted = instance.status == Inquiry.Status.SUBMITTED and (
        created or previous_status != Inquiry.Status.SUBMITTED
    )
    if not entered_submitted:
        return

    inquiry_id = instance.pk

    def _send_after_commit() -> None:
        if inquiry_id is None:
            return

        inquiry = (
            Inquiry.objects.select_related("user")
            .prefetch_related("items__product")
            .filter(pk=inquiry_id)
            .first()
        )
        if inquiry is None:
            return
        send_inquiry_submitted_emails(inquiry)

    transaction.on_commit(_send_after_commit)


@receiver(post_save, sender=Inquiry)
def send_negative_resolution_email_on_true_finalization(
    sender,
    instance: Inquiry,
    created: bool,
    **kwargs,
) -> None:
    previous_negative_resolved_at = getattr(instance, NEGATIVE_RESOLVED_AT_BEFORE_SAVE_ATTR, None)
    entered_negative_resolution = instance.negative_resolved_at is not None and (
        created or previous_negative_resolved_at is None
    )
    if not entered_negative_resolution:
        return

    inquiry_id = instance.pk

    def _send_after_commit() -> None:
        if inquiry_id is None:
            return

        inquiry = Inquiry.objects.select_related("user").filter(pk=inquiry_id).first()
        if inquiry is None:
            return

        try:
            send_customer_negative_resolution_email(inquiry)
        except Exception:
            logger.exception(
                "Failed to send customer negative-resolution email (inquiry=%s).",
                inquiry.reference_code,
            )

    transaction.on_commit(_send_after_commit, robust=True)


@receiver(pre_save, sender=InquiryOffer)
def cache_offer_status_before_save(sender, instance: InquiryOffer, **kwargs) -> None:
    if instance._state.adding or not instance.pk:
        setattr(instance, OFFER_STATUS_BEFORE_SAVE_ATTR, None)
        return

    previous_status = sender.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
    setattr(instance, OFFER_STATUS_BEFORE_SAVE_ATTR, previous_status)


@receiver(post_save, sender=InquiryOffer)
def send_customer_offer_email_on_status_entry(
    sender,
    instance: InquiryOffer,
    created: bool,
    **kwargs,
) -> None:
    previous_status = getattr(instance, OFFER_STATUS_BEFORE_SAVE_ATTR, None)
    entered_sent = instance.status == InquiryOffer.Status.SENT and (
        created or previous_status != InquiryOffer.Status.SENT
    )
    if not entered_sent:
        return

    offer_id = instance.pk

    def _send_after_commit() -> None:
        if offer_id is None:
            return

        offer = (
            InquiryOffer.objects.select_related("inquiry", "inquiry__user")
            .filter(pk=offer_id)
            .first()
        )
        if offer is None:
            return

        try:
            send_customer_offer_sent_email(offer)
        except Exception:
            logger.exception(
                "Failed to send customer offer email (offer=%s inquiry=%s).",
                offer.reference_code,
                offer.inquiry.reference_code,
            )

        try:
            send_supplier_offer_sent_notifications(offer)
        except Exception:
            logger.exception(
                (
                    "Failed to process supplier offer notifications "
                    "(offer=%s inquiry=%s)."
                ),
                offer.reference_code,
                offer.inquiry.reference_code,
            )

    transaction.on_commit(_send_after_commit, robust=True)


@receiver(post_save, sender=InquiryOffer)
def send_internal_offer_response_email_on_status_entry(
    sender,
    instance: InquiryOffer,
    created: bool,
    **kwargs,
) -> None:
    previous_status = getattr(instance, OFFER_STATUS_BEFORE_SAVE_ATTR, None)
    entered_response_status = instance.status in {
        InquiryOffer.Status.ACCEPTED,
        InquiryOffer.Status.REJECTED,
    } and (created or previous_status != instance.status)
    if not entered_response_status:
        return

    offer_id = instance.pk
    response_status = instance.status

    def _send_after_commit() -> None:
        if offer_id is None:
            return

        offer = (
            InquiryOffer.objects.select_related("inquiry", "inquiry__user")
            .filter(pk=offer_id)
            .first()
        )
        if offer is None:
            return

        try:
            send_internal_offer_response_notification_email(
                offer,
                response_status=response_status,
            )
        except Exception:
            logger.exception(
                (
                    "Failed to send internal offer-response notification email "
                    "(offer=%s inquiry=%s status=%s)."
                ),
                offer.reference_code,
                offer.inquiry.reference_code,
                response_status,
            )

    transaction.on_commit(_send_after_commit, robust=True)


@receiver(pre_save, sender=InquiryOfferPayment)
def cache_payment_status_before_save(
    sender,
    instance: InquiryOfferPayment,
    **kwargs,
) -> None:
    if instance._state.adding or not instance.pk:
        setattr(instance, PAYMENT_STATUS_BEFORE_SAVE_ATTR, None)
        return

    previous_status = sender.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
    setattr(instance, PAYMENT_STATUS_BEFORE_SAVE_ATTR, previous_status)


@receiver(post_save, sender=InquiryOfferPayment)
def send_internal_payment_paid_email_on_status_entry(
    sender,
    instance: InquiryOfferPayment,
    created: bool,
    **kwargs,
) -> None:
    previous_status = getattr(instance, PAYMENT_STATUS_BEFORE_SAVE_ATTR, None)
    entered_paid = instance.status == InquiryOfferPayment.Status.PAID and (
        created or previous_status != InquiryOfferPayment.Status.PAID
    )
    if not entered_paid:
        return

    payment_id = instance.pk

    def _send_after_commit() -> None:
        if payment_id is None:
            return

        payment = (
            InquiryOfferPayment.objects.select_related(
                "offer",
                "offer__inquiry",
                "offer__inquiry__user",
            )
            .filter(pk=payment_id)
            .first()
        )
        if payment is None:
            return

        try:
            send_internal_payment_paid_notification_email(payment)
        except Exception:
            logger.exception(
                (
                    "Failed to send internal paid-payment notification email "
                    "(payment=%s offer=%s inquiry=%s)."
                ),
                payment.reference_code,
                payment.offer.reference_code,
                payment.offer.inquiry.reference_code,
            )

    transaction.on_commit(_send_after_commit, robust=True)
