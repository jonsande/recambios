from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Supplier(models.Model):
    name = models.CharField(_("nombre"), max_length=180, unique=True)
    slug = models.SlugField(_("slug"), max_length=180, unique=True)
    code = models.CharField(_("código"), max_length=32, unique=True)
    country = models.CharField(_("país"), max_length=100, blank=True)
    website = models.URLField(_("sitio web"), blank=True)
    contact_name = models.CharField(_("persona de contacto"), max_length=150, blank=True)
    contact_email = models.EmailField(_("correo de contacto"), blank=True)
    orders_email = models.EmailField(
        _("correo de pedidos"),
        blank=True,
        help_text=(
            _(
                "Buzón operativo para pedidos, ofertas confirmadas y "
                "actualizaciones de disponibilidad."
            )
        ),
    )
    inquiry_submitted_notification_email = models.EmailField(
        _("correo para nuevas solicitudes"),
        blank=True,
        help_text=(
            _("Destino opcional para avisos de nuevas solicitudes. Si está vacío, se usa "
              "el correo de pedidos.")
        ),
    )
    offer_sent_notification_email = models.EmailField(
        _("correo para ofertas enviadas"),
        blank=True,
        help_text=(
            _("Destino opcional para avisos de ofertas enviadas. Si está vacío, se usa "
              "el correo de pedidos.")
        ),
    )
    offer_accepted_notification_email = models.EmailField(
        _("correo para ofertas aceptadas"),
        blank=True,
        help_text=(
            _("Destino opcional para avisos de ofertas aceptadas. Si está vacío, se usa "
              "el correo de pedidos.")
        ),
    )
    offer_rejected_notification_email = models.EmailField(
        _("correo para ofertas rechazadas"),
        blank=True,
        help_text=(
            _("Destino opcional para avisos de ofertas rechazadas. Si está vacío, se usa "
              "el correo de pedidos.")
        ),
    )
    payment_paid_notification_email = models.EmailField(
        _("correo para pagos confirmados"),
        blank=True,
        help_text=(
            _("Destino opcional para avisos de pagos confirmados. Si está vacío, se usa "
              "el correo de pedidos.")
        ),
    )
    offer_expired_notification_email = models.EmailField(
        _("correo para ofertas caducadas"),
        blank=True,
        help_text=(
            _("Destino opcional para avisos de ofertas caducadas. Si está vacío, se usa "
              "el correo de pedidos.")
        ),
    )
    payment_expired_notification_email = models.EmailField(
        _("correo para pagos caducados"),
        blank=True,
        help_text=(
            _("Destino opcional para avisos de pagos caducados. Si está vacío, se usa "
              "el correo de pedidos.")
        ),
    )
    offer_response_deadline_hours = models.PositiveIntegerField(
        _("horas para responder a la oferta"),
        default=24,
        help_text=(
            _("Número máximo de horas para que el cliente acepte o rechace una oferta enviada.")
        ),
    )
    accepted_payment_deadline_hours = models.PositiveIntegerField(
        _("horas para pagar una oferta aceptada"),
        default=24,
        help_text=(
            _("Número máximo de horas para pagar después de aceptar una oferta.")
        ),
    )
    auto_send_offer_sent_notification = models.BooleanField(
        _("enviar automáticamente al enviar una oferta"),
        default=False,
        help_text=(
            _("Activa el aviso automático al proveedor cuando se envía una oferta.")
        ),
    )
    auto_send_offer_accepted_notification = models.BooleanField(
        _("enviar automáticamente al aceptar una oferta"),
        default=False,
        help_text=(
            _("Activa el aviso automático al proveedor cuando el cliente acepta una oferta.")
        ),
    )
    auto_send_offer_rejected_notification = models.BooleanField(
        _("enviar automáticamente al rechazar una oferta"),
        default=False,
        help_text=(
            _("Activa el aviso automático al proveedor cuando el cliente rechaza una oferta.")
        ),
    )
    auto_send_payment_paid_notification = models.BooleanField(
        _("enviar automáticamente al confirmar un pago"),
        default=False,
        help_text=(
            _("Activa el aviso automático al proveedor cuando se confirma el pago.")
        ),
    )
    auto_send_offer_expired_notification = models.BooleanField(
        _("enviar automáticamente al caducar una oferta"),
        default=False,
        help_text=(
            _("Activa el aviso automático al proveedor cuando una oferta caduca sin respuesta.")
        ),
    )
    auto_send_payment_expired_notification = models.BooleanField(
        _("enviar automáticamente al caducar un pago"),
        default=False,
        help_text=(
            _("Activa el aviso automático al proveedor cuando caduca el plazo de pago.")
        ),
    )
    auto_send_inquiry_submitted_notification = models.BooleanField(
        _("enviar automáticamente al recibir una solicitud"),
        default=False,
        help_text=(
            _("Activa el aviso automático al proveedor al recibir una solicitud.")
        ),
    )
    send_inquiry_submitted_notification_internal_copy = models.BooleanField(
        _("enviar copia interna de nuevas solicitudes"),
        default=False,
        help_text=(
            _("Envía una copia interna oculta de los avisos automáticos de nuevas solicitudes.")
        ),
    )
    send_offer_sent_notification_internal_copy = models.BooleanField(
        _("enviar copia interna de ofertas enviadas"),
        default=False,
        help_text=(
            _("Envía una copia interna oculta de los avisos de ofertas enviadas.")
        ),
    )
    send_offer_accepted_notification_internal_copy = models.BooleanField(
        _("enviar copia interna de ofertas aceptadas"),
        default=False,
        help_text=(
            _("Envía una copia interna oculta de los avisos de ofertas aceptadas.")
        ),
    )
    send_offer_rejected_notification_internal_copy = models.BooleanField(
        _("enviar copia interna de ofertas rechazadas"),
        default=False,
        help_text=(
            _("Envía una copia interna oculta de los avisos de ofertas rechazadas.")
        ),
    )
    send_payment_paid_notification_internal_copy = models.BooleanField(
        _("enviar copia interna de pagos confirmados"),
        default=False,
        help_text=(
            _("Envía una copia interna oculta de los avisos de pagos confirmados.")
        ),
    )
    inquiry_submitted_email_subject_template = models.TextField(
        _("plantilla del asunto para nuevas solicitudes"),
        blank=True,
        help_text=(
            _("Plantilla opcional del asunto. Admite variables de Django como inquiry, "
              "supplier e items.")
        ),
    )
    inquiry_submitted_email_body_template = models.TextField(
        _("plantilla del cuerpo para nuevas solicitudes"),
        blank=True,
        help_text=(
            _("Plantilla opcional del cuerpo. Admite variables de Django como inquiry, "
              "supplier e items.")
        ),
    )
    offer_sent_email_subject_template = models.TextField(
        _("plantilla del asunto para ofertas enviadas"),
        blank=True,
        help_text=(
            _("Plantilla opcional del asunto. Admite variables de Django como offer, "
              "inquiry, supplier e items.")
        ),
    )
    offer_sent_email_body_template = models.TextField(
        _("plantilla del cuerpo para ofertas enviadas"),
        blank=True,
        help_text=(
            _("Plantilla opcional del cuerpo. Admite variables de Django como offer, "
              "inquiry, supplier e items.")
        ),
    )
    contact_phone = models.CharField(_("teléfono de contacto"), max_length=50, blank=True)
    is_active = models.BooleanField(_("activo"), default=True, db_index=True)
    created_at = models.DateTimeField(_("creado el"), auto_now_add=True)
    updated_at = models.DateTimeField(_("actualizado el"), auto_now=True)

    class Meta:
        verbose_name = _("proveedor")
        verbose_name_plural = _("proveedores")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active", "name"], name="sup_supplier_active_name_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class SupplierUserAssignment(models.Model):
    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.CASCADE,
        related_name="user_assignments",
        verbose_name=_("proveedor"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="supplier_assignments",
        verbose_name=_("usuario"),
    )
    is_active = models.BooleanField(_("activa"), default=True, db_index=True)
    created_at = models.DateTimeField(_("creada el"), auto_now_add=True)
    updated_at = models.DateTimeField(_("actualizada el"), auto_now=True)

    class Meta:
        verbose_name = _("asignación de usuario a proveedor")
        verbose_name_plural = _("asignaciones de usuarios a proveedores")
        ordering = ["supplier__name", "user__username"]
        constraints = [
            models.UniqueConstraint(
                fields=["supplier", "user"],
                name="sup_user_assignment_supplier_user_uq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "is_active"],
                name="sup_uasg_user_act_idx",
            ),
            models.Index(
                fields=["supplier", "is_active"],
                name="sup_uasg_sup_act_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} -> {self.supplier.code}"
