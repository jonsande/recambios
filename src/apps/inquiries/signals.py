from __future__ import annotations

import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .emails import send_customer_offer_sent_email, send_inquiry_submitted_emails
from .models import Inquiry, InquiryOffer

STATUS_BEFORE_SAVE_ATTR = "_status_before_save"
OFFER_STATUS_BEFORE_SAVE_ATTR = "_offer_status_before_save"
logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Inquiry)
def cache_inquiry_status_before_save(sender, instance: Inquiry, **kwargs) -> None:
    if instance._state.adding or not instance.pk:
        setattr(instance, STATUS_BEFORE_SAVE_ATTR, None)
        return

    previous_status = sender.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
    setattr(instance, STATUS_BEFORE_SAVE_ATTR, previous_status)


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

    transaction.on_commit(_send_after_commit, robust=True)
