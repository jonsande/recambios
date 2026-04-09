from .base import *
from decouple import config

DEBUG = False
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    cast=lambda v: [s.strip() for s in v.split(",") if s.strip()],
)

CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")