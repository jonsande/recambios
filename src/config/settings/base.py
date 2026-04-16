from pathlib import Path

from decouple import config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parents[3]
APPS_DIR = BASE_DIR / "src"


def csv_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


# Security
SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DJANGO_DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="127.0.0.1,localhost",
    cast=csv_list,
)

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.common.apps.CommonConfig",
    "apps.users.apps.UsersConfig",
    "apps.suppliers.apps.SuppliersConfig",
    "apps.catalog.apps.CatalogConfig",
    "apps.vehicles.apps.VehiclesConfig",
    "apps.search.apps.SearchConfig",
    "apps.cart.apps.CartConfig",
    "apps.inquiries.apps.InquiriesConfig",
    "apps.orders.apps.OrdersConfig",
    "apps.checkout.apps.CheckoutConfig",
    "apps.imports.apps.ImportsConfig",
    "apps.pages.apps.PagesConfig",
    "apps.seo.apps.SeoConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [APPS_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.cart.context_processors.request_cart_summary",
                "apps.common.context_processors.site_brand",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("POSTGRES_DB"),
        "USER": config("POSTGRES_USER"),
        "PASSWORD": config("POSTGRES_PASSWORD"),
        "HOST": config("POSTGRES_HOST", default="127.0.0.1"),
        "PORT": config("POSTGRES_PORT", default="5432"),
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "es"
LANGUAGES = [
    ("es", "Español"),
    ("en", "English"),
]
TIME_ZONE = "Europe/Madrid"
USE_I18N = True
USE_TZ = True
LOCALE_PATHS = [APPS_DIR / "locale"]

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATICFILES_DIRS = [APPS_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Email
EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = config("EMAIL_HOST", default="localhost")
EMAIL_PORT = config("EMAIL_PORT", default=25, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=False, cast=bool)
EMAIL_USE_SSL = config("EMAIL_USE_SSL", default=False, cast=bool)
EMAIL_TIMEOUT = config("EMAIL_TIMEOUT", default=10, cast=int)
DEFAULT_FROM_EMAIL = config(
    "DEFAULT_FROM_EMAIL",
    default="Recambios Tecnicos <noreply@recambiostecnicos.local>",
)
SERVER_EMAIL = config("SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)

INQUIRY_INTERNAL_NOTIFICATION_EMAILS = config(
    "INQUIRY_INTERNAL_NOTIFICATION_EMAILS",
    default="",
    cast=csv_list,
)
INQUIRY_CUSTOMER_REPLY_TO_EMAIL = config(
    "INQUIRY_CUSTOMER_REPLY_TO_EMAIL",
    default=DEFAULT_FROM_EMAIL,
    cast=csv_list,
)
PUBLIC_BASE_URL = config(
    "PUBLIC_BASE_URL",
    default="http://127.0.0.1:8000",
)

SITE_BRAND_NAME = config(
    "SITE_BRAND_NAME",
    default="Recambios Técnicos",
)
SITE_BRAND_NAME_ES = config(
    "SITE_BRAND_NAME_ES",
    default=SITE_BRAND_NAME,
)
SITE_BRAND_NAME_EN = config(
    "SITE_BRAND_NAME_EN",
    default=SITE_BRAND_NAME,
)
SITE_BRAND_LOGO_LIGHT = config(
    "SITE_BRAND_LOGO_LIGHT",
    default="img/logo_min_alfa.png",
)
SITE_BRAND_LOGO_DARK = config(
    "SITE_BRAND_LOGO_DARK",
    default="img/logo_min_alfa_white.png",
)
SITE_CHROME_VARIANT = config(
    "SITE_CHROME_VARIANT",
    default="light",
).strip().lower()
if SITE_CHROME_VARIANT not in {"light", "dark"}:
    SITE_CHROME_VARIANT = "light"
SITE_CHROME_BG_LIGHT = config(
    "SITE_CHROME_BG_LIGHT",
    default="#f7fbff",
)
SITE_CHROME_BG_DARK = config(
    "SITE_CHROME_BG_DARK",
    default="#557873",
)
SITE_HERO_VARIANT = config(
    "SITE_HERO_VARIANT",
    default="light",
).strip().lower()
if SITE_HERO_VARIANT not in {"light", "dark"}:
    SITE_HERO_VARIANT = "light"
SITE_FOOTER_VARIANT = config(
    "SITE_FOOTER_VARIANT",
    default="inherit",
).strip().lower()
if SITE_FOOTER_VARIANT not in {"inherit", "light", "dark"}:
    SITE_FOOTER_VARIANT = "inherit"
SITE_FOOTER_BG = config(
    "SITE_FOOTER_BG",
    default="",
).strip()

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
