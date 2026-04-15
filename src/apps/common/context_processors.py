from __future__ import annotations

from django.conf import settings


def site_brand(request) -> dict[str, str]:
    language_code = getattr(request, "LANGUAGE_CODE", settings.LANGUAGE_CODE)
    language = str(language_code).split("-")[0].lower()

    localized_name = {
        "es": settings.SITE_BRAND_NAME_ES,
        "en": settings.SITE_BRAND_NAME_EN,
    }.get(language, settings.SITE_BRAND_NAME)

    chrome_variant = settings.SITE_CHROME_VARIANT
    brand_logo = (
        settings.SITE_BRAND_LOGO_DARK
        if chrome_variant == "dark"
        else settings.SITE_BRAND_LOGO_LIGHT
    )

    return {
        "site_brand_name": localized_name,
        "site_brand_logo": brand_logo,
        "site_chrome_variant": chrome_variant,
        "site_chrome_class": f"site-chrome-{chrome_variant}",
        "site_chrome_bg_light": settings.SITE_CHROME_BG_LIGHT,
        "site_chrome_bg_dark": settings.SITE_CHROME_BG_DARK,
    }
