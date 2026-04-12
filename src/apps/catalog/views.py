
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from django.views.generic import DetailView, ListView

from .public import get_public_categories_queryset, get_public_products_queryset

PRODUCTS_PER_PAGE = 12


def _format_decimal_value(value) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _render_attribute_value(attribute_value) -> str:
    value = ""
    if attribute_value.value_text:
        value = attribute_value.value_text
    elif attribute_value.value_number is not None:
        value = _format_decimal_value(attribute_value.value_number)
    elif attribute_value.value_boolean is not None:
        value = _("Sí") if attribute_value.value_boolean else _("No")

    if not value:
        return ""

    unit = attribute_value.attribute_definition.unit
    if unit:
        return f"{value} {unit}"
    return value


def _render_year_range(year_start, year_end) -> str:
    if year_start and year_end:
        return f"{year_start}-{year_end}"
    if year_start and not year_end:
        return _("%(start)s en adelante") % {"start": year_start}
    if year_end and not year_start:
        return _("%(end)s y anteriores") % {"end": year_end}
    return _("Año no especificado")


class CategoryListView(ListView):
    template_name = "catalog/category_list.html"
    context_object_name = "categories"

    def get_queryset(self):
        return (
            get_public_categories_queryset(with_counts=True)
            .filter(public_product_count__gt=0)
        )


class ProductListView(ListView):
    template_name = "catalog/product_list.html"
    context_object_name = "products"
    paginate_by = PRODUCTS_PER_PAGE
    current_category = None

    def get_queryset(self):
        queryset = get_public_products_queryset()
        category_slug = self.kwargs.get("category_slug")
        if category_slug:
            self.current_category = get_object_or_404(
                get_public_categories_queryset(with_counts=True).filter(
                    public_product_count__gt=0
                ),
                slug=category_slug,
            )
            queryset = queryset.filter(category=self.current_category)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_category"] = self.current_category
        if self.current_category:
            context["page_title"] = _("Productos de %(category)s") % {
                "category": self.current_category.name
            }
        else:
            context["page_title"] = _("Catálogo de recambios")
        return context


class ProductDetailView(DetailView):
    template_name = "catalog/product_detail.html"
    context_object_name = "product"
    slug_url_kwarg = "slug"
    slug_field = "slug"

    def get_queryset(self):
        return get_public_products_queryset().prefetch_related(
            "part_numbers__brand",
            "attribute_values__attribute_definition",
            "fitments__vehicle__brand",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = context["product"]
        context["part_numbers"] = product.part_numbers.select_related("brand").order_by(
            "-is_primary",
            "part_number_type",
            "number_normalized",
        )

        fitments = product.fitments.select_related("vehicle__brand").filter(
            vehicle__is_active=True
        ).order_by("-is_verified", "vehicle__brand__name", "vehicle__model", "vehicle__year_start")
        context["fitments"] = [
            {
                "vehicle_name": " ".join(
                    part
                    for part in [
                        fitment.vehicle.brand.name,
                        fitment.vehicle.model,
                        fitment.vehicle.generation,
                        fitment.vehicle.variant,
                    ]
                    if part
                ),
                "year_range": _render_year_range(
                    fitment.vehicle.year_start,
                    fitment.vehicle.year_end,
                ),
                "engine_code": fitment.vehicle.engine_code,
                "fitment_notes": fitment.fitment_notes,
                "is_verified": fitment.is_verified,
            }
            for fitment in fitments
        ]

        raw_attribute_values = product.attribute_values.select_related(
            "attribute_definition"
        ).filter(attribute_definition__is_visible_on_product=True)

        technical_attributes = []
        for attribute_value in raw_attribute_values:
            rendered_value = _render_attribute_value(attribute_value)
            if not rendered_value:
                continue
            technical_attributes.append(
                {
                    "name": attribute_value.attribute_definition.name,
                    "value": rendered_value,
                }
            )

        context["technical_attributes"] = technical_attributes
        return context
