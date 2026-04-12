from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(url="/es/", permanent=False), name="root-redirect"),
    path('admin/', admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
]

urlpatterns += i18n_patterns(
    path("", include(("apps.pages.urls", "pages"), namespace="pages")),
    path("", include(("apps.catalog.urls", "catalog"), namespace="catalog")),
    prefix_default_language=True,
)
