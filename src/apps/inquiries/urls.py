from django.urls import path
from django.utils.translation import gettext_lazy as _

from .views import (
    PublicInquiryOfferDetailView,
    PublicInquiryOfferPaymentPlaceholderView,
    PublicInquirySubmitView,
    PublicInquirySuccessView,
)

app_name = "inquiries"

urlpatterns = [
    path(_("solicitud/enviar/"), PublicInquirySubmitView.as_view(), name="public_inquiry_submit"),
    path(
        _("solicitud/enviada/<str:reference_code>/"),
        PublicInquirySuccessView.as_view(),
        name="public_inquiry_success",
    ),
    path(
        _("oferta/<uuid:access_token>/"),
        PublicInquiryOfferDetailView.as_view(),
        name="public_inquiry_offer_detail",
    ),
    path(
        _("oferta/<uuid:access_token>/pago/"),
        PublicInquiryOfferPaymentPlaceholderView.as_view(),
        name="public_inquiry_offer_payment_placeholder",
    ),
]
