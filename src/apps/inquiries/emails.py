from __future__ import annotations

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import translation

from .models import Inquiry

SUPPORTED_INQUIRY_LANGUAGES = {choice for choice, _label in Inquiry.Language.choices}


def send_inquiry_submitted_emails(inquiry: Inquiry) -> None:
    context = _build_inquiry_email_context(inquiry)
    send_internal_submission_notification_email(inquiry, context=context)
    send_customer_submission_confirmation_email(inquiry, context=context)


def send_internal_submission_notification_email(
    inquiry: Inquiry,
    *,
    context: dict | None = None,
) -> None:
    recipients = list(getattr(settings, "INQUIRY_INTERNAL_NOTIFICATION_EMAILS", []))
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
    reply_to_email = (settings.INQUIRY_CUSTOMER_REPLY_TO_EMAIL or "").strip()
    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[customer_email],
        reply_to=[reply_to_email] if reply_to_email else None,
    )
    email.send(fail_silently=False)


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
        "customer_reply_to_email": settings.INQUIRY_CUSTOMER_REPLY_TO_EMAIL,
    }


def _resolve_requester_email(inquiry: Inquiry) -> str:
    if inquiry.user_id and inquiry.user and inquiry.user.email:
        return inquiry.user.email.strip().lower()
    return (inquiry.guest_email or "").strip().lower()


def _resolve_language(language_code: str) -> str:
    if language_code in SUPPORTED_INQUIRY_LANGUAGES:
        return language_code
    return settings.LANGUAGE_CODE


def _render_subject(template_name: str, context: dict, language: str) -> str:
    return " ".join(_render_body(template_name, context, language).splitlines()).strip()


def _render_body(template_name: str, context: dict, language: str) -> str:
    with translation.override(language):
        return render_to_string(template_name, context).strip()
