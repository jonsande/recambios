from collections import OrderedDict
from urllib.parse import urlencode

from django.db.models import Count, Max, Min, Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.generic import DetailView, ListView, TemplateView

from apps.vehicles.models import Vehicle

from .models import AttributeDefinition, ProductAttributeValue, normalize_part_number
from .public import get_public_categories_queryset, get_public_products_queryset

PRODUCTS_PER_PAGE = 12
VEHICLE_TYPE_ORDER = tuple(choice for choice, _label in Vehicle.VehicleType.choices)


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


def _parse_year_value(raw_value: str) -> int | None:
    if not raw_value or not raw_value.isdigit():
        return None

    parsed_value = int(raw_value)
    if parsed_value < 1900 or parsed_value > 2100:
        return None
    return parsed_value


def _clean_selected_values(values: list[str]) -> list[str]:
    cleaned_values: list[str] = []
    for value in values:
        stripped_value = value.strip()
        if stripped_value and stripped_value not in cleaned_values:
            cleaned_values.append(stripped_value)
    return cleaned_values


def _extract_selected_attribute_filters(query_params) -> dict[str, list[str]]:
    selected_filters: dict[str, list[str]] = {}
    for key in query_params.keys():
        if not key.startswith("attr_"):
            continue

        attribute_slug = key[5:]
        if not attribute_slug:
            continue

        cleaned_values = _clean_selected_values(query_params.getlist(key))
        if cleaned_values:
            selected_filters[attribute_slug] = cleaned_values
    return selected_filters


def _build_attribute_filter_options(
    option_scope_queryset,
    selected_attribute_filters: dict[str, list[str]],
) -> list[dict]:
    attribute_values = (
        ProductAttributeValue.objects.filter(
            product__in=option_scope_queryset.order_by(),
            attribute_definition__is_filterable=True,
        )
        .select_related("attribute_definition")
        .order_by(
            "attribute_definition__sort_order",
            "attribute_definition__name",
            "value_normalized",
            "id",
        )
    )

    attributes_map: OrderedDict[str, dict] = OrderedDict()
    for attribute_value in attribute_values:
        normalized_value = attribute_value.value_normalized
        if not normalized_value:
            continue

        attribute = attribute_value.attribute_definition
        attribute_option = attributes_map.setdefault(
            attribute.slug,
            {
                "name": attribute.name,
                "slug": attribute.slug,
                "param_name": f"attr_{attribute.slug}",
                "selected_values": set(selected_attribute_filters.get(attribute.slug, [])),
                "values_by_normalized": OrderedDict(),
            },
        )

        values_by_normalized = attribute_option["values_by_normalized"]
        if normalized_value in values_by_normalized:
            continue

        rendered_value = _render_attribute_value(attribute_value) or normalized_value
        values_by_normalized[normalized_value] = {
            "normalized": normalized_value,
            "label": rendered_value,
            "selected": normalized_value in attribute_option["selected_values"],
        }

    attribute_options: list[dict] = []
    for option in attributes_map.values():
        values = list(option["values_by_normalized"].values())
        if not values:
            continue
        attribute_options.append(
            {
                "name": option["name"],
                "slug": option["slug"],
                "param_name": option["param_name"],
                "values": values,
            }
        )

    return attribute_options


def _clean_vehicle_type_value(raw_value: str) -> str:
    value = (raw_value or "").strip().lower()
    if value in VEHICLE_TYPE_ORDER:
        return value
    return ""


def _vehicle_type_label(vehicle_type: str) -> str:
    labels = {
        Vehicle.VehicleType.CAR: _("Coche"),
        Vehicle.VehicleType.MOTORCYCLE: _("Moto"),
        Vehicle.VehicleType.TRUCK: _("Camión"),
        Vehicle.VehicleType.VAN: _("Furgoneta"),
        Vehicle.VehicleType.OTHER: _("Otros vehículos"),
    }
    return labels.get(vehicle_type, vehicle_type)


def _build_product_filter_options(
    option_scope_queryset,
    *,
    include_categories: bool,
    selected_vehicle_type: str,
    selected_vehicle_brand_slug: str,
    selected_attribute_filters: dict[str, list[str]],
) -> dict[str, list]:
    scope_queryset = option_scope_queryset.order_by()
    fitment_scope_queryset = scope_queryset.filter(
        fitments__vehicle__is_active=True,
        fitments__vehicle__brand__is_active=True,
    )

    available_vehicle_types = set(
        fitment_scope_queryset.values_list("fitments__vehicle__vehicle_type", flat=True)
        .distinct()
        .order_by()
    )
    vehicle_type_options = [
        {
            "value": vehicle_type,
            "label": _vehicle_type_label(vehicle_type),
        }
        for vehicle_type in VEHICLE_TYPE_ORDER
        if vehicle_type in available_vehicle_types
    ]

    vehicle_brand_queryset = fitment_scope_queryset
    if selected_vehicle_type:
        vehicle_brand_queryset = vehicle_brand_queryset.filter(
            fitments__vehicle__vehicle_type=selected_vehicle_type
        )

    vehicle_brand_rows = list(
        vehicle_brand_queryset.values(
            "fitments__vehicle__brand__slug",
            "fitments__vehicle__brand__name",
        )
        .distinct()
        .order_by("fitments__vehicle__brand__name")
    )
    vehicle_brand_options = [
        {
            "slug": row["fitments__vehicle__brand__slug"],
            "name": row["fitments__vehicle__brand__name"],
        }
        for row in vehicle_brand_rows
        if row["fitments__vehicle__brand__slug"]
    ]

    model_queryset = fitment_scope_queryset
    if selected_vehicle_type:
        model_queryset = model_queryset.filter(
            fitments__vehicle__vehicle_type=selected_vehicle_type
        )
    if selected_vehicle_brand_slug:
        model_queryset = model_queryset.filter(
            fitments__vehicle__brand__slug=selected_vehicle_brand_slug,
        )

    model_options = list(
        model_queryset.exclude(fitments__vehicle__model="")
        .values_list("fitments__vehicle__model", flat=True)
        .distinct()
        .order_by("fitments__vehicle__model")
    )

    condition_rows = list(
        scope_queryset.values("condition__code", "condition__name")
        .distinct()
        .order_by("condition__name")
    )
    condition_options = [
        {
            "code": row["condition__code"],
            "name": row["condition__name"],
        }
        for row in condition_rows
    ]

    category_options: list[dict] = []
    if include_categories:
        category_rows = list(
            scope_queryset.values("category__slug", "category__name")
            .distinct()
            .order_by("category__name")
        )
        category_options = [
            {
                "slug": row["category__slug"],
                "name": row["category__name"],
            }
            for row in category_rows
        ]

    return {
        "vehicle_type_options": vehicle_type_options,
        "vehicle_brand_options": vehicle_brand_options,
        "model_options": model_options,
        "condition_options": condition_options,
        "category_options": category_options,
        "attribute_options": _build_attribute_filter_options(
            scope_queryset,
            selected_attribute_filters,
        ),
    }


def _build_compatibility_context_parts(
    *,
    selected_vehicle_type: str,
    selected_vehicle_brand_slug: str,
    selected_vehicle_model: str,
    selected_year_input: str,
    vehicle_brand_options: list[dict],
) -> list[str]:
    context_parts: list[str] = []

    if selected_vehicle_type:
        context_parts.append(_vehicle_type_label(selected_vehicle_type))

    if selected_vehicle_brand_slug:
        selected_brand_name = selected_vehicle_brand_slug
        for option in vehicle_brand_options:
            if option["slug"] == selected_vehicle_brand_slug:
                selected_brand_name = option["name"]
                break
        context_parts.append(selected_brand_name)

    if selected_vehicle_model:
        context_parts.append(selected_vehicle_model)

    parsed_year = _parse_year_value(selected_year_input)
    if parsed_year is not None:
        context_parts.append(str(parsed_year))

    return context_parts


class CategoryListView(ListView):
    template_name = "catalog/category_list.html"
    context_object_name = "categories"

    def get_queryset(self):
        return get_public_categories_queryset(with_counts=True).filter(public_product_count__gt=0)


class CompatibilityVehicleTypeListView(TemplateView):
    template_name = "catalog/compatibility_vehicle_types.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        scope_queryset = get_public_products_queryset().filter(
            fitments__vehicle__is_active=True,
            fitments__vehicle__brand__is_active=True,
        )
        type_rows = list(
            scope_queryset.values("fitments__vehicle__vehicle_type")
            .annotate(public_product_count=Count("id", distinct=True))
            .order_by()
        )

        count_by_type = {
            row["fitments__vehicle__vehicle_type"]: row["public_product_count"]
            for row in type_rows
            if row["fitments__vehicle__vehicle_type"]
        }
        type_options = [
            {
                "value": vehicle_type,
                "label": _vehicle_type_label(vehicle_type),
                "public_product_count": count_by_type[vehicle_type],
                "browse_url": reverse(
                    "catalog:compatibility_vehicle_brands",
                    kwargs={"vehicle_type": vehicle_type},
                ),
            }
            for vehicle_type in VEHICLE_TYPE_ORDER
            if count_by_type.get(vehicle_type)
        ]

        context.update(
            {
                "page_title": _("Compatibilidad por vehículo"),
                "vehicle_type_options": type_options,
            }
        )
        return context


class CompatibilityBrandListView(TemplateView):
    template_name = "catalog/compatibility_brands.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        selected_vehicle_type = _clean_vehicle_type_value(self.kwargs.get("vehicle_type", ""))
        if not selected_vehicle_type:
            raise Http404

        scope_queryset = get_public_products_queryset().filter(
            fitments__vehicle__is_active=True,
            fitments__vehicle__brand__is_active=True,
            fitments__vehicle__vehicle_type=selected_vehicle_type,
        )
        brand_rows = list(
            scope_queryset.values(
                "fitments__vehicle__brand__slug",
                "fitments__vehicle__brand__name",
            )
            .annotate(public_product_count=Count("id", distinct=True))
            .distinct()
            .order_by("fitments__vehicle__brand__name")
        )

        brand_options = [
            {
                "slug": row["fitments__vehicle__brand__slug"],
                "name": row["fitments__vehicle__brand__name"],
                "public_product_count": row["public_product_count"],
                "browse_url": reverse(
                    "catalog:compatibility_vehicle_models",
                    kwargs={
                        "vehicle_type": selected_vehicle_type,
                        "brand_slug": row["fitments__vehicle__brand__slug"],
                    },
                ),
            }
            for row in brand_rows
            if row["fitments__vehicle__brand__slug"]
        ]

        if not brand_options:
            raise Http404

        context.update(
            {
                "page_title": _("Compatibilidad por marca"),
                "selected_vehicle_type": selected_vehicle_type,
                "selected_vehicle_type_label": _vehicle_type_label(selected_vehicle_type),
                "brand_options": brand_options,
                "vehicle_types_url": reverse("catalog:compatibility_vehicle_types"),
            }
        )
        return context


class CompatibilityModelYearView(TemplateView):
    template_name = "catalog/compatibility_model_year.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        selected_vehicle_type = _clean_vehicle_type_value(self.kwargs.get("vehicle_type", ""))
        if not selected_vehicle_type:
            raise Http404

        brand_slug = (self.kwargs.get("brand_slug") or "").strip()
        if not brand_slug:
            raise Http404

        scope_queryset = get_public_products_queryset().filter(
            fitments__vehicle__is_active=True,
            fitments__vehicle__brand__is_active=True,
            fitments__vehicle__vehicle_type=selected_vehicle_type,
        )
        brand_queryset = scope_queryset.filter(fitments__vehicle__brand__slug=brand_slug)

        selected_brand = brand_queryset.values(
            "fitments__vehicle__brand__slug",
            "fitments__vehicle__brand__name",
        ).first()
        if not selected_brand:
            raise Http404

        model_options = list(
            brand_queryset.exclude(fitments__vehicle__model="")
            .values_list("fitments__vehicle__model", flat=True)
            .distinct()
            .order_by("fitments__vehicle__model")
        )
        if not model_options:
            raise Http404

        selected_model_raw = (self.request.GET.get("model") or "").strip()
        selected_model = ""
        for model_option in model_options:
            if model_option.casefold() == selected_model_raw.casefold():
                selected_model = model_option
                break

        selected_year_input = (self.request.GET.get("year") or "").strip()
        selected_year = _parse_year_value(selected_year_input)

        year_scope_queryset = brand_queryset
        if selected_model:
            year_scope_queryset = year_scope_queryset.filter(
                fitments__vehicle__model__iexact=selected_model
            )

        year_limits = year_scope_queryset.aggregate(
            min_year=Min("fitments__vehicle__year_start"),
            max_year=Max("fitments__vehicle__year_end"),
        )

        catalog_results_url = ""
        if selected_model:
            query_params = {
                "vehicle_type": selected_vehicle_type,
                "brand": brand_slug,
                "model": selected_model,
            }
            if selected_year is not None:
                query_params["year"] = str(selected_year)
            catalog_results_url = (
                f"{reverse('catalog:product_list')}?{urlencode(query_params)}"
            )

        context.update(
            {
                "page_title": _("Compatibilidad por modelo y año"),
                "selected_vehicle_type": selected_vehicle_type,
                "selected_vehicle_type_label": _vehicle_type_label(selected_vehicle_type),
                "selected_brand_slug": selected_brand["fitments__vehicle__brand__slug"],
                "selected_brand_name": selected_brand["fitments__vehicle__brand__name"],
                "model_options": model_options,
                "selected_model": selected_model,
                "selected_year_input": selected_year_input,
                "year_input_invalid": bool(selected_year_input) and selected_year is None,
                "model_selection_invalid": bool(selected_model_raw) and not selected_model,
                "year_hint_start": year_limits["min_year"],
                "year_hint_end": year_limits["max_year"],
                "catalog_results_url": catalog_results_url,
                "can_view_results": bool(selected_model),
                "brand_list_url": reverse(
                    "catalog:compatibility_vehicle_brands",
                    kwargs={"vehicle_type": selected_vehicle_type},
                ),
            }
        )
        return context


class ProductListView(ListView):
    template_name = "catalog/product_list.html"
    context_object_name = "products"
    paginate_by = PRODUCTS_PER_PAGE
    current_category = None
    search_query = ""
    selected_vehicle_type = ""
    selected_vehicle_brand_slug = ""
    selected_vehicle_model = ""
    selected_year_input = ""
    selected_category_slug = ""
    selected_condition_code = ""
    selected_attribute_filters: dict[str, list[str]]
    has_active_filters = False

    def get_queryset(self):
        queryset = get_public_products_queryset()
        self.current_category = None
        category_slug = self.kwargs.get("category_slug")
        if category_slug:
            self.current_category = get_object_or_404(
                get_public_categories_queryset(with_counts=True).filter(
                    public_product_count__gt=0
                ),
                slug=category_slug,
            )
            queryset = queryset.filter(category=self.current_category)

        self.search_query = (self.request.GET.get("q") or "").strip()
        self.selected_vehicle_type = _clean_vehicle_type_value(
            self.request.GET.get("vehicle_type") or ""
        )
        self.selected_vehicle_brand_slug = (self.request.GET.get("brand") or "").strip()
        self.selected_vehicle_model = (self.request.GET.get("model") or "").strip()
        self.selected_year_input = (self.request.GET.get("year") or "").strip()
        self.selected_category_slug = (self.request.GET.get("category") or "").strip()
        self.selected_condition_code = (self.request.GET.get("condition") or "").strip()
        self.selected_attribute_filters = {}

        if self.search_query:
            normalized_reference = normalize_part_number(self.search_query)
            vehicle_search_filters = Q(
                fitments__vehicle__is_active=True,
                fitments__vehicle__brand__is_active=True,
            ) & (
                Q(fitments__vehicle__brand__name__icontains=self.search_query)
                | Q(fitments__vehicle__model__icontains=self.search_query)
                | Q(fitments__vehicle__generation__icontains=self.search_query)
                | Q(fitments__vehicle__variant__icontains=self.search_query)
            )
            search_filters = (
                Q(sku__icontains=self.search_query)
                | Q(part_numbers__number_raw__icontains=self.search_query)
                | vehicle_search_filters
            )
            if normalized_reference:
                search_filters |= Q(part_numbers__number_normalized__icontains=normalized_reference)
            queryset = queryset.filter(search_filters)

        vehicle_filter = Q()
        has_vehicle_filter = False
        if self.selected_vehicle_type:
            has_vehicle_filter = True
            vehicle_filter &= Q(fitments__vehicle__vehicle_type=self.selected_vehicle_type)

        if self.selected_vehicle_brand_slug:
            has_vehicle_filter = True
            vehicle_filter &= Q(
                fitments__vehicle__brand__slug=self.selected_vehicle_brand_slug,
                fitments__vehicle__brand__is_active=True,
            )

        if self.selected_vehicle_model:
            has_vehicle_filter = True
            vehicle_filter &= Q(fitments__vehicle__model__iexact=self.selected_vehicle_model)

        selected_year = _parse_year_value(self.selected_year_input)
        if selected_year is not None:
            has_vehicle_filter = True
            vehicle_filter &= (
                Q(fitments__vehicle__year_start__isnull=True)
                | Q(fitments__vehicle__year_start__lte=selected_year)
            )
            vehicle_filter &= (
                Q(fitments__vehicle__year_end__isnull=True)
                | Q(fitments__vehicle__year_end__gte=selected_year)
            )

        if has_vehicle_filter:
            vehicle_filter &= Q(fitments__vehicle__is_active=True)
            queryset = queryset.filter(vehicle_filter)

        if not self.current_category and self.selected_category_slug:
            queryset = queryset.filter(category__slug=self.selected_category_slug)

        if self.selected_condition_code:
            queryset = queryset.filter(condition__code=self.selected_condition_code)

        requested_attribute_filters = _extract_selected_attribute_filters(self.request.GET)
        if requested_attribute_filters:
            filterable_attribute_ids = dict(
                AttributeDefinition.objects.filter(
                    is_filterable=True,
                    slug__in=requested_attribute_filters.keys(),
                ).values_list("slug", "id")
            )
            for attribute_slug, selected_values in requested_attribute_filters.items():
                attribute_id = filterable_attribute_ids.get(attribute_slug)
                if not attribute_id:
                    continue
                queryset = queryset.filter(
                    attribute_values__attribute_definition_id=attribute_id,
                    attribute_values__value_normalized__in=selected_values,
                )
                self.selected_attribute_filters[attribute_slug] = selected_values

        self.has_active_filters = any(
            [
                self.search_query,
                self.selected_vehicle_type,
                self.selected_vehicle_brand_slug,
                self.selected_vehicle_model,
                self.selected_year_input,
                (not self.current_category and self.selected_category_slug),
                self.selected_condition_code,
                bool(self.selected_attribute_filters),
            ]
        )

        return queryset.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_category"] = self.current_category
        context["search_query"] = self.search_query
        context["selected_vehicle_type"] = self.selected_vehicle_type
        context["selected_vehicle_brand_slug"] = self.selected_vehicle_brand_slug
        context["selected_vehicle_model"] = self.selected_vehicle_model
        context["selected_year_input"] = self.selected_year_input
        context["selected_category_slug"] = self.selected_category_slug
        context["selected_condition_code"] = self.selected_condition_code
        context["selected_attribute_filters"] = self.selected_attribute_filters
        context["has_active_filters"] = self.has_active_filters

        if self.current_category:
            context["page_title"] = _("Productos de %(category)s") % {
                "category": self.current_category.name
            }
        else:
            context["page_title"] = _("Catálogo de recambios")

        option_scope_queryset = get_public_products_queryset()
        if self.current_category:
            option_scope_queryset = option_scope_queryset.filter(category=self.current_category)

        filter_options = _build_product_filter_options(
            option_scope_queryset,
            include_categories=not self.current_category,
            selected_vehicle_type=self.selected_vehicle_type,
            selected_vehicle_brand_slug=self.selected_vehicle_brand_slug,
            selected_attribute_filters=self.selected_attribute_filters,
        )
        context.update(filter_options)

        compatibility_context_parts = _build_compatibility_context_parts(
            selected_vehicle_type=self.selected_vehicle_type,
            selected_vehicle_brand_slug=self.selected_vehicle_brand_slug,
            selected_vehicle_model=self.selected_vehicle_model,
            selected_year_input=self.selected_year_input,
            vehicle_brand_options=context["vehicle_brand_options"],
        )
        context["has_compatibility_context"] = bool(compatibility_context_parts)
        context["compatibility_context_label"] = " · ".join(compatibility_context_parts)
        context["compatibility_browse_url"] = reverse("catalog:compatibility_vehicle_types")

        query_params_without_page = self.request.GET.copy()
        query_params_without_page.pop("page", None)
        context["query_string_without_page"] = query_params_without_page.urlencode()
        if self.current_category:
            context["reset_filters_url"] = reverse(
                "catalog:category_products",
                kwargs={"category_slug": self.current_category.slug},
            )
        else:
            context["reset_filters_url"] = reverse("catalog:product_list")

        return context


class ProductDetailView(DetailView):
    template_name = "catalog/product_detail.html"
    context_object_name = "product"
    slug_url_kwarg = "slug"
    slug_field = "slug"

    def get_queryset(self):
        return get_public_products_queryset().prefetch_related(
            "part_numbers__brand",
            "part_numbers__part_number_type",
            "attribute_values__attribute_definition",
            "fitments__vehicle__brand",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = context["product"]
        context["part_numbers"] = product.part_numbers.select_related(
            "brand",
            "part_number_type",
        ).order_by(
            "-is_primary",
            "part_number_type__sort_order",
            "part_number_type__code",
            "number_normalized",
        )

        fitments = product.fitments.select_related("vehicle__brand").filter(
            vehicle__is_active=True
        ).order_by(
            "-is_verified",
            "vehicle__vehicle_type",
            "vehicle__brand__name",
            "vehicle__model",
            "vehicle__generation",
            "vehicle__variant",
            "vehicle__year_start",
        )

        fitment_groups_map: OrderedDict[tuple[str, str, str], dict] = OrderedDict()
        for fitment in fitments:
            vehicle = fitment.vehicle
            group_key = (vehicle.vehicle_type, vehicle.brand.name, vehicle.model)
            fitment_group = fitment_groups_map.setdefault(
                group_key,
                {
                    "vehicle_type": vehicle.vehicle_type,
                    "vehicle_type_label": _vehicle_type_label(vehicle.vehicle_type),
                    "brand_name": vehicle.brand.name,
                    "model": vehicle.model,
                    "applications": [],
                },
            )
            application_parts = [part for part in [vehicle.generation, vehicle.variant] if part]
            if application_parts:
                application_label = " ".join(application_parts)
            else:
                application_label = _("Configuración base")
            fitment_group["applications"].append(
                {
                    "application_label": application_label,
                    "year_range": _render_year_range(vehicle.year_start, vehicle.year_end),
                    "engine_code": vehicle.engine_code,
                    "fitment_notes": fitment.fitment_notes,
                    "is_verified": fitment.is_verified,
                }
            )

        context["fitment_groups"] = list(fitment_groups_map.values())

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
