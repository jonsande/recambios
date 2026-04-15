from __future__ import annotations

from django.conf import settings


def site_brand(request) -> dict[str, str]:
    language_code = getattr(request, "LANGUAGE_CODE", settings.LANGUAGE_CODE)
    language = str(language_code).split("-")[0].lower()

    localized_name = {
        "es": settings.SITE_BRAND_NAME_ES,
        "en": settings.SITE_BRAND_NAME_EN,
    }.get(language, settings.SITE_BRAND_NAME)

    return {
        "site_brand_name": localized_name,
    }

