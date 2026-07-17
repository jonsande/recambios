from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.urls import include, path
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import RedirectView

from apps.inquiries.views import StripeCheckoutWebhookView

admin.site.site_header = format_lazy(
    _("Administración de {brand}"),
    brand=settings.SITE_BRAND_NAME_ES,
)
admin.site.site_title = settings.SITE_BRAND_NAME_ES
admin.site.index_title = _("Gestión interna")

urlpatterns = [
    path("", RedirectView.as_view(url="/es/", permanent=False), name="root-redirect"),
    path('admin/', admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path(
        "webhooks/stripe/checkout/",
        StripeCheckoutWebhookView.as_view(),
        name="stripe_checkout_webhook",
    ),
]

urlpatterns += i18n_patterns(
    path("", include(("apps.pages.urls", "pages"), namespace="pages")),
    path("", include(("apps.catalog.urls", "catalog"), namespace="catalog")),
    path("", include(("apps.cart.urls", "cart"), namespace="cart")),
    path("", include(("apps.inquiries.urls", "inquiries"), namespace="inquiries")),
    prefix_default_language=True,
)
