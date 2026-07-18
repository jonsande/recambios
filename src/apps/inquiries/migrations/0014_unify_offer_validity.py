from datetime import timedelta

from django.db import migrations, models
from django.utils.translation import gettext_lazy as _


def recalculate_offer_validity(apps, schema_editor):
    InquiryOffer = apps.get_model("inquiries", "InquiryOffer")
    InquiryOfferPayment = apps.get_model("inquiries", "InquiryOfferPayment")

    for offer in InquiryOffer.objects.filter(
        status__in=["sent", "accepted"],
        sent_at__isnull=False,
    ).iterator():
        hours = offer.validity_hours_snapshot or 24
        offer.valid_until = offer.sent_at + timedelta(hours=hours)
        offer.save(update_fields=["valid_until"])

    InquiryOfferPayment.objects.update(checkout_expires_at=None)


class Migration(migrations.Migration):
    dependencies = [
        ("inquiries", "0013_alter_inquiryofferpaymentdetails_billing_tax_id"),
        ("suppliers", "0010_unify_offer_validity"),
    ]

    operations = [
        migrations.RenameField(
            model_name="inquiryoffer",
            old_name="offer_response_deadline_at",
            new_name="valid_until",
        ),
        migrations.RenameField(
            model_name="inquiryoffer",
            old_name="response_deadline_hours_snapshot",
            new_name="validity_hours_snapshot",
        ),
        migrations.RenameField(
            model_name="inquiryofferpayment",
            old_name="payment_deadline_at",
            new_name="checkout_expires_at",
        ),
        migrations.RemoveIndex(
            model_name="inquiryoffer",
            name="inq_offer_status_respdl_idx",
        ),
        migrations.RemoveIndex(
            model_name="inquiryofferpayment",
            name="inq_pay_status_deadl_idx",
        ),
        migrations.AlterField(
            model_name="inquiryoffer",
            name="valid_until",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                null=True,
                verbose_name=_("fecha límite de vigencia"),
            ),
        ),
        migrations.AlterField(
            model_name="inquiryoffer",
            name="validity_hours_snapshot",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name=_("horas de vigencia aplicadas"),
            ),
        ),
        migrations.AlterField(
            model_name="inquiryofferpayment",
            name="checkout_expires_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                null=True,
                verbose_name=_("vencimiento de la sesión de pago"),
            ),
        ),
        migrations.AddIndex(
            model_name="inquiryoffer",
            index=models.Index(
                fields=["status", "valid_until"],
                name="inq_offer_status_valid_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="inquiryofferpayment",
            index=models.Index(
                fields=["status", "checkout_expires_at"],
                name="inq_pay_status_checkout_idx",
            ),
        ),
        migrations.RunPython(recalculate_offer_validity, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="inquiryoffer",
            name="payment_deadline_hours_snapshot",
        ),
    ]
