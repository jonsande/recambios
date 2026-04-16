from django.test import RequestFactory, override_settings

from apps.common.context_processors import site_brand


@override_settings(
    SITE_BRAND_NAME="Default Brand",
    SITE_BRAND_NAME_ES="Marca ES",
    SITE_BRAND_NAME_EN="Brand EN",
    SITE_BRAND_LOGO_LIGHT="img/light.png",
    SITE_BRAND_LOGO_DARK="img/dark.png",
    SITE_CHROME_VARIANT="light",
    SITE_CHROME_BG_LIGHT="#ffffff",
    SITE_CHROME_BG_DARK="#557873",
    SITE_FOOTER_VARIANT="inherit",
    SITE_FOOTER_BG="",
)
def test_site_brand_context_uses_current_language() -> None:
    request = RequestFactory().get("/es/")
    request.LANGUAGE_CODE = "es"

    context = site_brand(request)

    assert context["site_brand_name"] == "Marca ES"
    assert context["site_brand_logo"] == "img/light.png"
    assert context["site_chrome_variant"] == "light"
    assert context["site_chrome_class"] == "site-chrome-light"
    assert context["site_chrome_bg_light"] == "#ffffff"
    assert context["site_chrome_bg_dark"] == "#557873"
    assert context["site_footer_variant"] == "light"
    assert context["site_footer_class"] == "site-footer-light"
    assert context["site_footer_logo"] == "img/light.png"
    assert context["site_footer_bg"] == ""


@override_settings(
    SITE_BRAND_NAME="Default Brand",
    SITE_BRAND_NAME_ES="Marca ES",
    SITE_BRAND_NAME_EN="Brand EN",
    SITE_BRAND_LOGO_LIGHT="img/light.png",
    SITE_BRAND_LOGO_DARK="img/dark.png",
    SITE_CHROME_VARIANT="dark",
    SITE_CHROME_BG_LIGHT="#f8f8f8",
    SITE_CHROME_BG_DARK="#557873",
    SITE_FOOTER_VARIANT="light",
    SITE_FOOTER_BG="#101010",
)
def test_site_brand_context_falls_back_to_default_for_unknown_language() -> None:
    request = RequestFactory().get("/fr/")
    request.LANGUAGE_CODE = "fr"

    context = site_brand(request)

    assert context["site_brand_name"] == "Default Brand"
    assert context["site_brand_logo"] == "img/dark.png"
    assert context["site_chrome_variant"] == "dark"
    assert context["site_chrome_class"] == "site-chrome-dark"
    assert context["site_chrome_bg_light"] == "#f8f8f8"
    assert context["site_chrome_bg_dark"] == "#557873"
    assert context["site_footer_variant"] == "light"
    assert context["site_footer_class"] == "site-footer-light"
    assert context["site_footer_logo"] == "img/light.png"
    assert context["site_footer_bg"] == "#101010"
