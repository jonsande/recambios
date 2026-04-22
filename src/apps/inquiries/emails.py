from __future__ import annotations

import logging
from urllib.parse import urljoin

from django.conf import settings
from django.core.mail import EmailMessage
from django.template import Context, Template, TemplateSyntaxError
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation

from apps.suppliers.models import Supplier

from .models import Inquiry, InquiryOffer, InquiryOfferPayment

SUPPORTED_INQUIRY_LANGUAGES = {choice for choice, _label in Inquiry.Language.choices}
SUPPLIER_NOTIFICATION_LANGUAGE = "en"
logger = logging.getLogger(__name__)


def send_inquiry_submitted_emails(inquiry: Inquiry) -> None:
    context = _build_inquiry_email_context(inquiry)
    send_internal_submission_notification_email(inquiry, context=context)
    send_customer_submission_confirmation_email(inquiry, context=context)
    send_supplier_inquiry_submitted_notifications(inquiry)


def send_internal_submission_notification_email(
    inquiry: Inquiry,
    *,
    context: dict | None = None,
) -> None:
    recipients = _resolve_internal_notification_recipients()
    if not recipients:
        return

    rendered_context = context or _build_inquiry_email_context(inquiry)
    language = _resolve_language(inquiry.language)
    subject = _render_subject(
        "inquiries/emails/internal_submission_subject.txt",
        rendered_context,
        language,
    )
    body = _render_body(
        "inquiries/emails/internal_submission_body.txt",
        rendered_context,
        language,
    )
    customer_email = rendered_context.get("requester_email")

    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.SERVER_EMAIL,
        to=recipients,
        reply_to=[customer_email] if customer_email else None,
    )
    email.send(fail_silently=False)


def send_customer_submission_confirmation_email(
    inquiry: Inquiry,
    *,
    context: dict | None = None,
) -> None:
    rendered_context = context or _build_inquiry_email_context(inquiry)
    customer_email = rendered_context.get("requester_email")
    if not customer_email:
        return

    language = _resolve_language(inquiry.language)
    subject = _render_subject(
        "inquiries/emails/customer_submission_subject.txt",
        rendered_context,
        language,
    )
    body = _render_body(
        "inquiries/emails/customer_submission_body.txt",
        rendered_context,
        language,
    )
    reply_to_emails = _resolve_customer_reply_to_emails()
    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[customer_email],
        reply_to=reply_to_emails or None,
    )
    email.send(fail_silently=False)


def send_customer_offer_sent_email(offer: InquiryOffer) -> bool:
    context = _build_offer_sent_email_context(offer)
    customer_email = context.get("requester_email")
    if not customer_email:
        logger.warning(
            "Customer offer email skipped due to missing recipient email (offer=%s inquiry=%s).",
            offer.reference_code,
            offer.inquiry.reference_code,
        )
        return False

    language = _resolve_language(offer.inquiry.language)
    subject = _render_subject(
        "inquiries/emails/customer_offer_sent_subject.txt",
        context,
        language,
    )
    body = _render_body(
        "inquiries/emails/customer_offer_sent_body.txt",
        context,
        language,
    )
    reply_to_emails = _resolve_customer_reply_to_emails()
    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[customer_email],
        reply_to=reply_to_emails or None,
    )
    email.send(fail_silently=False)
    return True


def send_supplier_inquiry_submitted_notifications(inquiry: Inquiry) -> None:
    supplier_groups = _build_supplier_item_groups_for_inquiry(inquiry)
    if not supplier_groups:
        logger.warning(
            (
                "Supplier inquiry notification skipped because no supplier-linked "
                "inquiry items were found (inquiry=%s)."
            ),
            inquiry.reference_code,
        )
        return

    for supplier_group in supplier_groups:
        supplier = supplier_group["supplier"]
        if not supplier.auto_send_inquiry_submitted_notification:
            logger.info(
                (
                    "Supplier inquiry notification skipped because automatic notifications "
                    "are disabled for supplier (inquiry=%s supplier=%s)."
                ),
                inquiry.reference_code,
                supplier.code,
            )
            continue

        supplier_email = (supplier.orders_email or "").strip().lower()
        if not supplier_email:
            logger.warning(
                (
                    "Supplier inquiry notification skipped due to missing orders_email "
                    "(inquiry=%s supplier=%s)."
                ),
                inquiry.reference_code,
                supplier.code,
            )
            _notify_internal_supplier_inquiry_notification_failure(
                inquiry=inquiry,
                supplier=supplier,
                supplier_items=supplier_group["items"],
                failure_reason_code="missing_orders_email",
            )
            continue

        context = _build_supplier_inquiry_submitted_email_context(
            inquiry=inquiry,
            supplier=supplier,
            supplier_items=supplier_group["items"],
        )
        subject = _render_supplier_notification_subject(
            supplier=supplier,
            custom_template=supplier.inquiry_submitted_email_subject_template,
            default_template_name="inquiries/emails/supplier_inquiry_submitted_subject.txt",
            context=context,
            custom_template_field="inquiry_submitted_email_subject_template",
        )
        body = _render_supplier_notification_body(
            supplier=supplier,
            custom_template=supplier.inquiry_submitted_email_body_template,
            default_template_name="inquiries/emails/supplier_inquiry_submitted_body.txt",
            context=context,
            custom_template_field="inquiry_submitted_email_body_template",
        )
        reply_to_emails = _resolve_customer_reply_to_emails()
        internal_copy_recipients = _resolve_supplier_internal_copy_recipients()

        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[supplier_email],
            reply_to=reply_to_emails or None,
            bcc=internal_copy_recipients or None,
        )

        try:
            email.send(fail_silently=False)
        except Exception as error:
            logger.exception(
                (
                    "Failed to send supplier inquiry notification email "
                    "(inquiry=%s supplier=%s)."
                ),
                inquiry.reference_code,
                supplier.code,
            )
            _notify_internal_supplier_inquiry_notification_failure(
                inquiry=inquiry,
                supplier=supplier,
                supplier_items=supplier_group["items"],
                failure_reason_code="send_failure",
                failure_detail=str(error),
            )


def send_supplier_offer_sent_notifications(offer: InquiryOffer) -> None:
    supplier_groups = _build_supplier_item_groups_for_offer(offer)
    if not supplier_groups:
        logger.warning(
            (
                "Supplier offer notification skipped because no supplier-linked "
                "inquiry items were found (offer=%s inquiry=%s)."
            ),
            offer.reference_code,
            offer.inquiry.reference_code,
        )
        return

    for supplier_group in supplier_groups:
        supplier = supplier_group["supplier"]
        if not supplier.auto_send_offer_sent_notification:
            logger.info(
                (
                    "Supplier offer notification skipped because automatic notifications "
                    "are disabled for supplier (offer=%s inquiry=%s supplier=%s)."
                ),
                offer.reference_code,
                offer.inquiry.reference_code,
                supplier.code,
            )
            continue

        supplier_email = (supplier.orders_email or "").strip().lower()

        if not supplier_email:
            logger.warning(
                (
                    "Supplier offer notification skipped due to missing orders_email "
                    "(offer=%s inquiry=%s supplier=%s)."
                ),
                offer.reference_code,
                offer.inquiry.reference_code,
                supplier.code,
            )
            _notify_internal_supplier_notification_failure(
                offer=offer,
                supplier=supplier,
                supplier_items=supplier_group["items"],
                failure_reason_code="missing_orders_email",
            )
            continue

        context = _build_supplier_offer_sent_email_context(
            offer=offer,
            supplier=supplier,
            supplier_items=supplier_group["items"],
        )
        subject = _render_supplier_notification_subject(
            supplier=supplier,
            custom_template=supplier.offer_sent_email_subject_template,
            default_template_name="inquiries/emails/supplier_offer_sent_subject.txt",
            context=context,
            custom_template_field="offer_sent_email_subject_template",
        )
        body = _render_supplier_notification_body(
            supplier=supplier,
            custom_template=supplier.offer_sent_email_body_template,
            default_template_name="inquiries/emails/supplier_offer_sent_body.txt",
            context=context,
            custom_template_field="offer_sent_email_body_template",
        )
        reply_to_emails = _resolve_customer_reply_to_emails()
        internal_copy_recipients = _resolve_supplier_internal_copy_recipients()

        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[supplier_email],
            reply_to=reply_to_emails or None,
            bcc=internal_copy_recipients or None,
        )

        try:
            email.send(fail_silently=False)
        except Exception as error:
            logger.exception(
                (
                    "Failed to send supplier offer notification email "
                    "(offer=%s inquiry=%s supplier=%s)."
                ),
                offer.reference_code,
                offer.inquiry.reference_code,
                supplier.code,
            )
            _notify_internal_supplier_notification_failure(
                offer=offer,
                supplier=supplier,
                supplier_items=supplier_group["items"],
                failure_reason_code="send_failure",
                failure_detail=str(error),
            )


def _notify_internal_supplier_notification_failure(
    *,
    offer: InquiryOffer,
    supplier: Supplier,
    supplier_items: list[dict],
    failure_reason_code: str,
    failure_detail: str = "",
) -> None:
    recipients = _resolve_internal_notification_recipients()
    if not recipients:
        logger.warning(
            (
                "Internal supplier-notification failure email skipped because no "
                "internal recipients are configured (offer=%s inquiry=%s supplier=%s reason=%s)."
            ),
            offer.reference_code,
            offer.inquiry.reference_code,
            supplier.code,
            failure_reason_code,
        )
        return

    context = _build_internal_supplier_notification_failure_email_context(
        offer=offer,
        supplier=supplier,
        supplier_items=supplier_items,
        failure_reason_code=failure_reason_code,
        failure_detail=failure_detail,
    )
    subject = _render_subject(
        "inquiries/emails/internal_supplier_notification_failure_subject.txt",
        context,
        SUPPLIER_NOTIFICATION_LANGUAGE,
    )
    body = _render_body(
        "inquiries/emails/internal_supplier_notification_failure_body.txt",
        context,
        SUPPLIER_NOTIFICATION_LANGUAGE,
    )
    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.SERVER_EMAIL,
        to=recipients,
    )

    try:
        email.send(fail_silently=False)
    except Exception:
        logger.exception(
            (
                "Failed to send internal supplier-notification failure email "
                "(offer=%s inquiry=%s supplier=%s reason=%s)."
            ),
            offer.reference_code,
            offer.inquiry.reference_code,
            supplier.code,
            failure_reason_code,
        )


def _notify_internal_supplier_inquiry_notification_failure(
    *,
    inquiry: Inquiry,
    supplier: Supplier,
    supplier_items: list[dict],
    failure_reason_code: str,
    failure_detail: str = "",
) -> None:
    recipients = _resolve_internal_notification_recipients()
    if not recipients:
        logger.warning(
            (
                "Internal supplier inquiry-notification failure email skipped because no "
                "internal recipients are configured (inquiry=%s supplier=%s reason=%s)."
            ),
            inquiry.reference_code,
            supplier.code,
            failure_reason_code,
        )
        return

    context = _build_internal_supplier_inquiry_notification_failure_email_context(
        inquiry=inquiry,
        supplier=supplier,
        supplier_items=supplier_items,
        failure_reason_code=failure_reason_code,
        failure_detail=failure_detail,
    )
    subject = _render_subject(
        "inquiries/emails/internal_supplier_inquiry_notification_failure_subject.txt",
        context,
        SUPPLIER_NOTIFICATION_LANGUAGE,
    )
    body = _render_body(
        "inquiries/emails/internal_supplier_inquiry_notification_failure_body.txt",
        context,
        SUPPLIER_NOTIFICATION_LANGUAGE,
    )
    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.SERVER_EMAIL,
        to=recipients,
    )

    try:
        email.send(fail_silently=False)
    except Exception:
        logger.exception(
            (
                "Failed to send internal supplier inquiry-notification failure email "
                "(inquiry=%s supplier=%s reason=%s)."
            ),
            inquiry.reference_code,
            supplier.code,
            failure_reason_code,
        )


def send_internal_offer_response_notification_email(
    offer: InquiryOffer,
    *,
    response_status: str,
) -> bool:
    recipients = _resolve_internal_notification_recipients()
    if not recipients:
        return False

    if response_status not in {InquiryOffer.Status.ACCEPTED, InquiryOffer.Status.REJECTED}:
        raise ValueError("Offer response notification supports only accepted or rejected status.")

    context = _build_internal_offer_response_email_context(offer)
    language = _resolve_language(offer.inquiry.language)
    template_suffix = (
        "accepted" if response_status == InquiryOffer.Status.ACCEPTED else "rejected"
    )
    subject = _render_subject(
        f"inquiries/emails/internal_offer_{template_suffix}_subject.txt",
        context,
        language,
    )
    body = _render_body(
        f"inquiries/emails/internal_offer_{template_suffix}_body.txt",
        context,
        language,
    )
    customer_email = context.get("requester_email")
    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.SERVER_EMAIL,
        to=recipients,
        reply_to=[customer_email] if customer_email else None,
    )
    email.send(fail_silently=False)
    return True


def send_internal_payment_paid_notification_email(payment: InquiryOfferPayment) -> bool:
    recipients = _resolve_internal_notification_recipients()
    if not recipients:
        return False

    context = _build_internal_payment_paid_email_context(payment)
    language = _resolve_language(payment.offer.inquiry.language)
    subject = _render_subject(
        "inquiries/emails/internal_payment_paid_subject.txt",
        context,
        language,
    )
    body = _render_body(
        "inquiries/emails/internal_payment_paid_body.txt",
        context,
        language,
    )
    customer_email = context.get("requester_email")
    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.SERVER_EMAIL,
        to=recipients,
        reply_to=[customer_email] if customer_email else None,
    )
    email.send(fail_silently=False)
    return True


def send_customer_payment_paid_confirmation_email(payment: InquiryOfferPayment) -> bool:
    context = _build_customer_payment_paid_email_context(payment)
    customer_email = context.get("requester_email")
    if not customer_email:
        logger.warning(
            "Customer paid-confirmation email skipped due to missing recipient email (payment=%s).",
            payment.reference_code,
        )
        return False

    language = _resolve_language(payment.offer.inquiry.language)
    subject = _render_subject(
        "inquiries/emails/customer_payment_paid_subject.txt",
        context,
        language,
    )
    body = _render_body(
        "inquiries/emails/customer_payment_paid_body.txt",
        context,
        language,
    )
    reply_to_emails = _resolve_customer_reply_to_emails()
    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[customer_email],
        reply_to=reply_to_emails or None,
    )
    email.send(fail_silently=False)
    return True


def send_customer_negative_resolution_email(inquiry: Inquiry) -> bool:
    context = _build_negative_resolution_email_context(inquiry)
    customer_email = context.get("requester_email")
    if not customer_email:
        logger.warning(
            (
                "Customer negative-resolution email skipped due to "
                "missing recipient email (inquiry=%s)."
            ),
            inquiry.reference_code,
        )
        return False

    language = _resolve_language(inquiry.language)
    subject = _render_subject(
        "inquiries/emails/customer_negative_resolution_subject.txt",
        context,
        language,
    )
    body = _render_body(
        "inquiries/emails/customer_negative_resolution_body.txt",
        context,
        language,
    )
    reply_to_emails = _resolve_customer_reply_to_emails()
    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[customer_email],
        reply_to=reply_to_emails or None,
    )
    email.send(fail_silently=False)
    return True


def _build_inquiry_email_context(inquiry: Inquiry) -> dict:
    requester_name = inquiry.requester_display
    if inquiry.user_id and inquiry.user:
        full_name = inquiry.user.get_full_name().strip()
        if full_name:
            requester_name = full_name

    requester_email = _resolve_requester_email(inquiry)
    item_rows = [
        {
            "sku": item.product.sku,
            "title": item.product.title,
            "quantity": item.requested_quantity,
        }
        for item in inquiry.items.select_related("product").order_by("id")
    ]

    return {
        "inquiry": inquiry,
        "items": item_rows,
        "requester_name": requester_name,
        "requester_email": requester_email,
        "requester_phone": inquiry.guest_phone,
        "company_name": inquiry.company_name,
        "tax_id": inquiry.tax_id,
        "customer_reply_to_email": _resolve_customer_reply_to_display(),
    }


def _build_offer_sent_email_context(offer: InquiryOffer) -> dict:
    requester_email = _resolve_requester_email(offer.inquiry)
    return {
        "inquiry": offer.inquiry,
        "offer": offer,
        "requester_email": requester_email,
        "offer_public_url": _build_offer_public_url(offer),
        "customer_reply_to_email": _resolve_customer_reply_to_display(),
    }


def _build_supplier_item_groups_for_inquiry(inquiry: Inquiry) -> list[dict]:
    grouped_suppliers: dict[int, dict] = {}
    inquiry_items = inquiry.items.select_related("product__supplier").order_by("id")

    for inquiry_item in inquiry_items:
        supplier = inquiry_item.product.supplier
        supplier_id = supplier.pk
        if supplier_id is None:
            continue

        group = grouped_suppliers.setdefault(
            supplier_id,
            {
                "supplier": supplier,
                "items": [],
            },
        )
        group["items"].append(
            {
                "sku": inquiry_item.product.sku,
                "title": inquiry_item.product.title,
                "quantity": inquiry_item.requested_quantity,
            }
        )

    return list(grouped_suppliers.values())


def _build_supplier_item_groups_for_offer(offer: InquiryOffer) -> list[dict]:
    return _build_supplier_item_groups_for_inquiry(offer.inquiry)


def _build_supplier_inquiry_submitted_email_context(
    *,
    inquiry: Inquiry,
    supplier: Supplier,
    supplier_items: list[dict],
) -> dict:
    return {
        "inquiry": inquiry,
        "supplier": supplier,
        "items": supplier_items,
    }


def _build_supplier_offer_sent_email_context(
    *,
    offer: InquiryOffer,
    supplier: Supplier,
    supplier_items: list[dict],
) -> dict:
    return {
        "offer": offer,
        "inquiry": offer.inquiry,
        "supplier": supplier,
        "items": supplier_items,
    }


def _build_internal_supplier_notification_failure_email_context(
    *,
    offer: InquiryOffer,
    supplier: Supplier,
    supplier_items: list[dict],
    failure_reason_code: str,
    failure_detail: str,
) -> dict:
    return {
        "offer": offer,
        "inquiry": offer.inquiry,
        "supplier": supplier,
        "items": supplier_items,
        "failure_reason_code": failure_reason_code,
        "failure_reason_label": _build_supplier_notification_failure_reason_label(
            failure_reason_code
        ),
        "failure_detail": failure_detail,
    }


def _build_internal_supplier_inquiry_notification_failure_email_context(
    *,
    inquiry: Inquiry,
    supplier: Supplier,
    supplier_items: list[dict],
    failure_reason_code: str,
    failure_detail: str,
) -> dict:
    return {
        "inquiry": inquiry,
        "supplier": supplier,
        "items": supplier_items,
        "failure_reason_code": failure_reason_code,
        "failure_reason_label": _build_supplier_notification_failure_reason_label(
            failure_reason_code
        ),
        "failure_detail": failure_detail,
    }


def _build_supplier_notification_failure_reason_label(failure_reason_code: str) -> str:
    if failure_reason_code == "missing_orders_email":
        return "Missing supplier operational orders email."
    if failure_reason_code == "send_failure":
        return "Supplier notification delivery failed."
    return "Unknown supplier notification issue."


def _build_negative_resolution_email_context(inquiry: Inquiry) -> dict:
    requester_email = _resolve_requester_email(inquiry)
    return {
        "inquiry": inquiry,
        "requester_email": requester_email,
        "customer_reply_to_email": _resolve_customer_reply_to_display(),
    }


def _build_internal_offer_response_email_context(offer: InquiryOffer) -> dict:
    requester_email = _resolve_requester_email(offer.inquiry)
    return {
        "inquiry": offer.inquiry,
        "offer": offer,
        "requester_email": requester_email,
        "offer_public_url": _build_offer_public_url(offer),
    }


def _build_internal_payment_paid_email_context(payment: InquiryOfferPayment) -> dict:
    requester_email = _resolve_requester_email(payment.offer.inquiry)
    return {
        "inquiry": payment.offer.inquiry,
        "offer": payment.offer,
        "payment": payment,
        "requester_email": requester_email,
        "offer_public_url": _build_offer_public_url(payment.offer),
    }


def _build_customer_payment_paid_email_context(payment: InquiryOfferPayment) -> dict:
    requester_email = _resolve_requester_email(payment.offer.inquiry)
    return {
        "inquiry": payment.offer.inquiry,
        "offer": payment.offer,
        "payment": payment,
        "requester_email": requester_email,
        "offer_public_url": _build_offer_public_url(payment.offer),
        "customer_reply_to_email": _resolve_customer_reply_to_display(),
    }


def _resolve_requester_email(inquiry: Inquiry) -> str:
    if inquiry.user_id and inquiry.user and inquiry.user.email:
        return inquiry.user.email.strip().lower()
    return (inquiry.guest_email or "").strip().lower()


def _resolve_customer_reply_to_emails() -> list[str]:
    raw_value = getattr(settings, "INQUIRY_CUSTOMER_REPLY_TO_EMAIL", "")

    if isinstance(raw_value, str):
        candidates = raw_value.split(",")
    elif isinstance(raw_value, (list, tuple, set)):
        candidates = []
        for value in raw_value:
            if isinstance(value, str):
                candidates.extend(value.split(","))
    else:
        return []

    cleaned_emails: list[str] = []
    seen_normalized: set[str] = set()
    for candidate in candidates:
        email = candidate.strip()
        if not email:
            continue
        normalized_email = email.lower()
        if normalized_email in seen_normalized:
            continue
        seen_normalized.add(normalized_email)
        cleaned_emails.append(email)
    return cleaned_emails


def _resolve_customer_reply_to_display() -> str:
    return ", ".join(_resolve_customer_reply_to_emails())


def _resolve_supplier_internal_copy_recipients() -> list[str]:
    recipients = _resolve_internal_notification_recipients()
    if recipients:
        return recipients

    server_email = getattr(settings, "SERVER_EMAIL", "")
    if isinstance(server_email, str):
        cleaned_server_email = server_email.strip()
        if cleaned_server_email:
            return [cleaned_server_email]

    default_from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "")
    if isinstance(default_from_email, str):
        cleaned_default_from_email = default_from_email.strip()
        if cleaned_default_from_email:
            return [cleaned_default_from_email]

    return []


def _resolve_internal_notification_recipients() -> list[str]:
    raw_value = getattr(settings, "INQUIRY_INTERNAL_NOTIFICATION_EMAILS", "")

    if isinstance(raw_value, str):
        candidates = raw_value.split(",")
    elif isinstance(raw_value, (list, tuple, set)):
        candidates = []
        for value in raw_value:
            if isinstance(value, str):
                candidates.extend(value.split(","))
    else:
        return []

    cleaned_recipients: list[str] = []
    seen_normalized: set[str] = set()
    for candidate in candidates:
        recipient = candidate.strip()
        if not recipient:
            continue
        normalized_recipient = recipient.lower()
        if normalized_recipient in seen_normalized:
            continue
        seen_normalized.add(normalized_recipient)
        cleaned_recipients.append(recipient)
    return cleaned_recipients


def _render_supplier_notification_subject(
    *,
    supplier: Supplier,
    custom_template: str,
    default_template_name: str,
    context: dict,
    custom_template_field: str,
) -> str:
    rendered_subject = _render_custom_supplier_template(
        supplier=supplier,
        custom_template=custom_template,
        context=context,
        custom_template_field=custom_template_field,
    )
    if rendered_subject:
        return " ".join(rendered_subject.splitlines()).strip()
    return _render_subject(default_template_name, context, SUPPLIER_NOTIFICATION_LANGUAGE)


def _render_supplier_notification_body(
    *,
    supplier: Supplier,
    custom_template: str,
    default_template_name: str,
    context: dict,
    custom_template_field: str,
) -> str:
    rendered_body = _render_custom_supplier_template(
        supplier=supplier,
        custom_template=custom_template,
        context=context,
        custom_template_field=custom_template_field,
    )
    if rendered_body:
        return rendered_body
    return _render_body(default_template_name, context, SUPPLIER_NOTIFICATION_LANGUAGE)


def _render_custom_supplier_template(
    *,
    supplier: Supplier,
    custom_template: str,
    context: dict,
    custom_template_field: str,
) -> str:
    template_source = (custom_template or "").strip()
    if not template_source:
        return ""

    try:
        template = Template(template_source)
    except TemplateSyntaxError:
        logger.exception(
            "Invalid custom supplier email template syntax (%s supplier=%s).",
            custom_template_field,
            supplier.code,
        )
        return ""

    try:
        return template.render(Context(context)).strip()
    except Exception:
        logger.exception(
            "Failed to render custom supplier email template (%s supplier=%s).",
            custom_template_field,
            supplier.code,
        )
        return ""


def _resolve_language(language_code: str) -> str:
    if language_code in SUPPORTED_INQUIRY_LANGUAGES:
        return language_code
    return settings.LANGUAGE_CODE


def _build_offer_public_url(offer: InquiryOffer) -> str:
    language = _resolve_language(offer.inquiry.language)
    with translation.override(language):
        offer_path = reverse(
            "inquiries:public_inquiry_offer_detail",
            kwargs={"access_token": offer.access_token},
        )

    public_base_url = (settings.PUBLIC_BASE_URL or "").strip()
    if not public_base_url:
        return offer_path
    return urljoin(public_base_url.rstrip("/") + "/", offer_path.lstrip("/"))


def _render_subject(template_name: str, context: dict, language: str) -> str:
    return " ".join(_render_body(template_name, context, language).splitlines()).strip()


def _render_body(template_name: str, context: dict, language: str) -> str:
    with translation.override(language):
        return render_to_string(template_name, context).strip()
