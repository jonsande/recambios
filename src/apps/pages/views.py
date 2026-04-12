from django.utils.translation import gettext as _
from django.views.generic import TemplateView

from apps.catalog.public import get_public_categories_queryset, get_public_products_queryset

HOME_PRODUCT_LIMIT = 6
HOME_CATEGORY_LIMIT = 8


class HomeView(TemplateView):
    template_name = "pages/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        public_products = get_public_products_queryset()
        featured_products = list(public_products.filter(featured=True)[:HOME_PRODUCT_LIMIT])

        if featured_products:
            home_products = featured_products
            products_section_title = _("Productos destacados")
        else:
            home_products = list(public_products[:HOME_PRODUCT_LIMIT])
            products_section_title = _("Últimos productos publicados")

        highlight_categories = list(
            get_public_categories_queryset(with_counts=True)
            .filter(public_product_count__gt=0)[:HOME_CATEGORY_LIMIT]
        )
        context.update(
            {
                "home_products": home_products,
                "products_section_title": products_section_title,
                "highlight_categories": highlight_categories,
            }
        )
        return context


class AboutView(TemplateView):
    template_name = "pages/about.html"


class ContactView(TemplateView):
    template_name = "pages/contact.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product_hint = (self.request.GET.get("product") or "").strip()
        context["product_hint"] = product_hint[:120]
        return context


class LegalView(TemplateView):
    template_name = "pages/legal.html"
