from django.db import migrations, models
from django.utils.translation import gettext_lazy as _


class Migration(migrations.Migration):
    dependencies = [
        ("suppliers", "0009_alter_supplier_accepted_payment_deadline_hours_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="supplier",
            old_name="offer_response_deadline_hours",
            new_name="offer_validity_hours",
        ),
        migrations.AlterField(
            model_name="supplier",
            name="offer_validity_hours",
            field=models.PositiveIntegerField(
                default=24,
                help_text=_(
                    "Número máximo de horas desde el envío para aceptar la oferta "
                    "y completar el pago."
                ),
                verbose_name=_("horas de vigencia de la oferta"),
            ),
        ),
        migrations.RemoveField(
            model_name="supplier",
            name="accepted_payment_deadline_hours",
        ),
        migrations.AlterField(
            model_name="supplier",
            name="auto_send_offer_expired_notification",
            field=models.BooleanField(
                default=False,
                help_text=_(
                    "Activa el aviso automático al proveedor cuando una oferta caduca "
                    "sin aceptación."
                ),
                verbose_name=_("enviar automáticamente al caducar una oferta"),
            ),
        ),
        migrations.AlterField(
            model_name="supplier",
            name="auto_send_payment_expired_notification",
            field=models.BooleanField(
                default=False,
                help_text=_(
                    "Activa el aviso automático al proveedor cuando caduca una oferta "
                    "aceptada sin pago."
                ),
                verbose_name=_("enviar automáticamente al caducar un pago"),
            ),
        ),
    ]
