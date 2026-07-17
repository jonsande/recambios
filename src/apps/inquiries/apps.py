from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class InquiriesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.inquiries"
    verbose_name = _("Solicitudes, ofertas y pagos")

    def ready(self) -> None:
        from . import signals  # noqa: F401
