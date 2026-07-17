from django.conf import settings
from django.urls import Resolver404, resolve
from django.utils import translation


class AdminSpanishLanguageMiddleware:
    """Keep the internal admin in Spanish, independently of the public language."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            match = resolve(request.path_info)
        except Resolver404:
            return self.get_response(request)

        if "admin" not in match.namespaces:
            return self.get_response(request)

        with translation.override(settings.ADMIN_LANGUAGE_CODE):
            request.LANGUAGE_CODE = settings.ADMIN_LANGUAGE_CODE
            response = self.get_response(request)
            response.headers["Content-Language"] = settings.ADMIN_LANGUAGE_CODE
            return response
