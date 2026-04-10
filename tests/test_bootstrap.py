from django.conf import settings


def test_postgresql_is_configured_for_default_database() -> None:
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"


def test_phase_zero_apps_are_registered() -> None:
    required_apps = {
        "apps.common.apps.CommonConfig",
        "apps.users.apps.UsersConfig",
        "apps.catalog.apps.CatalogConfig",
        "apps.vehicles.apps.VehiclesConfig",
        "apps.search.apps.SearchConfig",
        "apps.cart.apps.CartConfig",
        "apps.inquiries.apps.InquiriesConfig",
        "apps.orders.apps.OrdersConfig",
        "apps.checkout.apps.CheckoutConfig",
        "apps.suppliers.apps.SuppliersConfig",
        "apps.imports.apps.ImportsConfig",
        "apps.pages.apps.PagesConfig",
        "apps.seo.apps.SeoConfig",
    }

    assert required_apps.issubset(set(settings.INSTALLED_APPS))
