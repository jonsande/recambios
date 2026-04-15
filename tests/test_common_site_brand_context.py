from django.test import RequestFactory, override_settings

from apps.common.context_processors import site_brand


@override_settings(
    SITE_BRAND_NAME="Default Brand",
    SITE_BRAND_NAME_ES="Marca ES",
    SITE_BRAND_NAME_EN="Brand EN",
)
def test_site_brand_context_uses_current_language() -> None:
    request = RequestFactory().get("/es/")
    request.LANGUAGE_CODE = "es"

    context = site_brand(request)

    assert context["site_brand_name"] == "Marca ES"


@override_settings(
    SITE_BRAND_NAME="Default Brand",
    SITE_BRAND_NAME_ES="Marca ES",
    SITE_BRAND_NAME_EN="Brand EN",
)
def test_site_brand_context_falls_back_to_default_for_unknown_language() -> None:
    request = RequestFactory().get("/fr/")
    request.LANGUAGE_CODE = "fr"

    context = site_brand(request)

    assert context["site_brand_name"] == "Default Brand"

