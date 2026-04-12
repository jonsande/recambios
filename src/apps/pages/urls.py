from django.urls import path
from django.utils.translation import gettext_lazy as _

from .views import AboutView, ContactView, HomeView, LegalView

app_name = "pages"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path(_("nosotros/"), AboutView.as_view(), name="about"),
    path(_("contacto/"), ContactView.as_view(), name="contact"),
    path(_("legal/"), LegalView.as_view(), name="legal"),
]
