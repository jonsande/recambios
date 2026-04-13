from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.suppliers.access import get_active_supplier_ids_for_user, user_can_manage_supplier
from apps.users.roles import is_restricted_supplier_user
from apps.vehicles.models import ProductVehicleFitment

from .models import (
    AttributeDefinition,
    Brand,
    Category,
    Condition,
    PartNumber,
    PartNumberType,
    Product,
    ProductAttributeValue,
    ProductImage,
)


def resolve_lookup_value(obj, lookup: str):
    value = obj
    for part in lookup.split("__"):
        value = getattr(value, part, None)
        if value is None:
            return None
    if hasattr(value, "pk"):
        return value.pk
    return value


class ReferenceDataAdminMixin:
    def has_add_permission(self, request):
        if is_restricted_supplier_user(request.user):
            return False
        return super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        if is_restricted_supplier_user(request.user):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if is_restricted_supplier_user(request.user):
            return False
        return super().has_delete_permission(request, obj)


class SupplierScopedAdminMixin:
    supplier_lookup = "supplier_id"

    def supplier_ids_for_request(self, request) -> list[int]:
        return get_active_supplier_ids_for_user(request.user)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if is_restricted_supplier_user(request.user):
            supplier_ids = self.supplier_ids_for_request(request)
            return queryset.filter(**{f"{self.supplier_lookup}__in": supplier_ids})
        return queryset

    def has_view_permission(self, request, obj=None):
        if is_restricted_supplier_user(request.user) and obj is not None:
            supplier_id = resolve_lookup_value(obj, self.supplier_lookup)
            return user_can_manage_supplier(request.user, supplier_id)
        return super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        if is_restricted_supplier_user(request.user):
            supplier_scope_exists = bool(self.supplier_ids_for_request(request))
            return supplier_scope_exists and super().has_add_permission(request)
        return super().has_add_permission(request)


class DraftScopedAdminMixin(SupplierScopedAdminMixin):
    publication_lookup = "publication_status"
    product_field_name = "product"

    def is_object_draft(self, obj) -> bool:
        return resolve_lookup_value(obj, self.publication_lookup) == Product.PublicationStatus.DRAFT

    def has_change_permission(self, request, obj=None):
        allowed = super().has_change_permission(request, obj)
        if not is_restricted_supplier_user(request.user) or obj is None:
            return allowed
        return allowed and self.is_object_draft(obj)

    def has_delete_permission(self, request, obj=None):
        allowed = super().has_delete_permission(request, obj)
        if not is_restricted_supplier_user(request.user) or obj is None:
            return allowed
        return allowed and self.is_object_draft(obj)

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        if not is_restricted_supplier_user(request.user):
            return form
        if self.product_field_name in form.base_fields:
            supplier_ids = self.supplier_ids_for_request(request)
            form.base_fields[self.product_field_name].queryset = form.base_fields[
                self.product_field_name
            ].queryset.filter(
                supplier_id__in=supplier_ids,
                publication_status=Product.PublicationStatus.DRAFT,
            )
        return form

    def save_model(self, request, obj, form, change):
        if is_restricted_supplier_user(request.user):
            product = getattr(obj, self.product_field_name)
            supplier_ids = set(self.supplier_ids_for_request(request))
            if product.supplier_id not in supplier_ids:
                raise PermissionDenied("This product is outside your supplier scope.")
            if product.publication_status != Product.PublicationStatus.DRAFT:
                raise PermissionDenied("Only draft products can be edited by suppliers.")
        return super().save_model(request, obj, form, change)


@admin.register(Brand)
class BrandAdmin(ReferenceDataAdminMixin, admin.ModelAdmin):
    list_display = ("name", "brand_type", "country", "is_active", "updated_at")
    list_filter = ("brand_type", "is_active", "country")
    search_fields = ("name", "slug")
    ordering = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "updated_at"


@admin.register(Category)
class CategoryAdmin(ReferenceDataAdminMixin, admin.ModelAdmin):
    list_display = ("name", "parent", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    ordering = ("sort_order", "name")
    autocomplete_fields = ("parent",)
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "updated_at"


@admin.register(Condition)
class ConditionAdmin(ReferenceDataAdminMixin, admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "code", "slug")
    ordering = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "updated_at"


@admin.register(PartNumberType)
class PartNumberTypeAdmin(ReferenceDataAdminMixin, admin.ModelAdmin):
    list_display = ("code", "name", "sort_order", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    ordering = ("sort_order", "code")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "updated_at"


class PartNumberInline(admin.TabularInline):
    model = PartNumber
    verbose_name_plural = "PART NUMBERS"
    extra = 0
    fields = (
        "number_raw",
        "number_normalized",
        "part_number_type",
        "brand",
        "is_primary",
    )
    readonly_fields = ("number_normalized",)
    autocomplete_fields = ("brand",)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "part_number_type":
            kwargs["queryset"] = PartNumberType.objects.filter(is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    verbose_name_plural = "PRODUCT IMAGES"
    extra = 0
    fields = ("image", "alt_text", "sort_order", "is_primary")


class ProductVehicleFitmentInline(admin.TabularInline):
    model = ProductVehicleFitment
    verbose_name_plural = "PRODUCT VEHICLE FITMENTS"
    extra = 0
    fields = ("vehicle", "fitment_notes", "source", "is_verified")
    autocomplete_fields = ("vehicle",)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "vehicle":
            kwargs["queryset"] = db_field.related_model.objects.filter(is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if is_restricted_supplier_user(request.user):
            readonly_fields.extend(("source", "is_verified"))
        return tuple(dict.fromkeys(readonly_fields))


@admin.register(Product)
class ProductAdmin(SupplierScopedAdminMixin, admin.ModelAdmin):
    supplier_lookup = "supplier_id"
    list_display = (
        "sku",
        "title",
        "supplier",
        "brand",
        "category",
        "publication_status",
        "price_visibility_mode",
        "is_active",
        "featured",
        "updated_at",
    )
    list_filter = (
        "publication_status",
        "price_visibility_mode",
        "is_active",
        "featured",
        "supplier",
        "brand",
        "category",
        "condition",
    )
    search_fields = ("sku", "slug", "title", "supplier_product_code")
    ordering = ("-updated_at",)
    list_select_related = ("supplier", "brand", "category", "condition")
    autocomplete_fields = ("supplier", "brand", "category", "condition")
    inlines = (PartNumberInline, ProductVehicleFitmentInline, ProductImageInline)
    readonly_fields = ("slug", "created_at", "updated_at")
    date_hierarchy = "updated_at"
    actions = (
        "mark_selected_as_draft",
        "mark_selected_as_in_review",
        "mark_selected_as_published",
    )
    fieldsets = (
        (
            "Product Identity",
            {
                "fields": (
                    "supplier",
                    "sku",
                    "supplier_product_code",
                    "title",
                    "slug",
                    "short_description",
                    "long_description",
                )
            },
        ),
        (
            "Classification",
            {"fields": ("brand", "category", "condition", "is_active", "featured")},
        ),
        (
            "Pricing",
            {
                "fields": (
                    "last_known_price",
                    "currency",
                    "unit_of_sale",
                    "quantity",
                    "unit_of_quantity",
                )
            },
        ),
        ("Dimensions", {"fields": ("weight", "length", "width", "height")}),
        (
            "Publication",
            {"fields": ("publication_status", "published_at", "price_visibility_mode")},
        ),
        ("Audit", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def has_change_permission(self, request, obj=None):
        allowed = super().has_change_permission(request, obj)
        if not is_restricted_supplier_user(request.user) or obj is None:
            return allowed
        return allowed and obj.publication_status == Product.PublicationStatus.DRAFT

    def has_delete_permission(self, request, obj=None):
        allowed = super().has_delete_permission(request, obj)
        if not is_restricted_supplier_user(request.user) or obj is None:
            return allowed
        return allowed and obj.publication_status == Product.PublicationStatus.DRAFT

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        if not is_restricted_supplier_user(request.user):
            return form

        supplier_ids = self.supplier_ids_for_request(request)
        if "supplier" in form.base_fields:
            form.base_fields["supplier"].queryset = form.base_fields["supplier"].queryset.filter(
                id__in=supplier_ids
            )
            if len(supplier_ids) == 1 and obj is None:
                form.base_fields["supplier"].initial = supplier_ids[0]

        if "publication_status" in form.base_fields:
            allowed_choices = {
                Product.PublicationStatus.DRAFT,
                Product.PublicationStatus.REVIEW,
            }
            form.base_fields["publication_status"].choices = [
                choice
                for choice in form.base_fields["publication_status"].choices
                if choice[0] in allowed_choices
            ]
        return form

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if is_restricted_supplier_user(request.user):
            readonly_fields.append("published_at")
        return tuple(dict.fromkeys(readonly_fields))

    def get_actions(self, request):
        actions = super().get_actions(request)
        can_publish = request.user.is_superuser or request.user.has_perm(
            "catalog.can_publish_product"
        )
        if is_restricted_supplier_user(request.user) or not can_publish:
            actions.pop("mark_selected_as_published", None)
        return actions

    def _change_publication_status(self, request, queryset, target_status, action_label):
        is_restricted_supplier = is_restricted_supplier_user(request.user)
        total_selected = queryset.count()

        if is_restricted_supplier:
            allowed_statuses = {
                Product.PublicationStatus.DRAFT,
                Product.PublicationStatus.REVIEW,
            }
            if target_status not in allowed_statuses:
                self.message_user(
                    request,
                    "Supplier users cannot publish products.",
                    level=messages.ERROR,
                )
                return
            queryset = queryset.filter(publication_status=Product.PublicationStatus.DRAFT)

        if (
            target_status == Product.PublicationStatus.PUBLISHED
            and not request.user.is_superuser
            and not request.user.has_perm("catalog.can_publish_product")
        ):
            self.message_user(
                request,
                "You do not have permission to publish products.",
                level=messages.ERROR,
            )
            return

        queryset = queryset.exclude(publication_status=target_status)
        if target_status == Product.PublicationStatus.PUBLISHED:
            updated_count = queryset.update(
                publication_status=target_status,
                published_at=timezone.now(),
            )
        else:
            updated_count = queryset.update(publication_status=target_status, published_at=None)

        skipped_count = total_selected - updated_count
        if updated_count:
            self.message_user(
                request,
                f"{action_label} applied to {updated_count} product(s).",
                level=messages.SUCCESS,
            )
        if skipped_count:
            self.message_user(
                request,
                (
                    f"Skipped {skipped_count} product(s) due to permission/status "
                    "constraints or no changes."
                ),
                level=messages.WARNING,
            )

    @admin.action(description="Set publication status to Draft")
    def mark_selected_as_draft(self, request, queryset):
        self._change_publication_status(
            request=request,
            queryset=queryset,
            target_status=Product.PublicationStatus.DRAFT,
            action_label="Draft status",
        )

    @admin.action(description="Set publication status to In Review")
    def mark_selected_as_in_review(self, request, queryset):
        self._change_publication_status(
            request=request,
            queryset=queryset,
            target_status=Product.PublicationStatus.REVIEW,
            action_label="In review status",
        )

    @admin.action(description="Set publication status to Published")
    def mark_selected_as_published(self, request, queryset):
        self._change_publication_status(
            request=request,
            queryset=queryset,
            target_status=Product.PublicationStatus.PUBLISHED,
            action_label="Published status",
        )

    def save_model(self, request, obj, form, change):
        is_restricted_supplier = is_restricted_supplier_user(request.user)

        if is_restricted_supplier:
            supplier_ids = set(self.supplier_ids_for_request(request))
            if obj.supplier_id not in supplier_ids:
                raise PermissionDenied("This product is outside your supplier scope.")
            if change:
                previous_status = Product.objects.only("publication_status").get(pk=obj.pk)
                if previous_status.publication_status != Product.PublicationStatus.DRAFT:
                    raise PermissionDenied("Only draft products can be edited by suppliers.")
            if obj.publication_status == Product.PublicationStatus.PUBLISHED:
                raise PermissionDenied("Supplier users cannot publish products.")
            if obj.publication_status not in {
                Product.PublicationStatus.DRAFT,
                Product.PublicationStatus.REVIEW,
            }:
                raise PermissionDenied("Supplier users can only keep draft or submit for review.")
            obj.published_at = None
        else:
            if (
                obj.publication_status == Product.PublicationStatus.PUBLISHED
                and not request.user.has_perm("catalog.can_publish_product")
                and not request.user.is_superuser
            ):
                raise PermissionDenied("You do not have permission to publish products.")
            if (
                obj.publication_status == Product.PublicationStatus.PUBLISHED
                and not obj.published_at
            ):
                obj.published_at = timezone.now()
            elif obj.publication_status != Product.PublicationStatus.PUBLISHED:
                obj.published_at = None

        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        if formset.model is ProductVehicleFitment and is_restricted_supplier_user(request.user):
            instances = formset.save(commit=False)
            for deleted_obj in formset.deleted_objects:
                deleted_obj.delete()
            for fitment in instances:
                fitment.source = ProductVehicleFitment.FitmentSource.SUPPLIER
                fitment.is_verified = False
                fitment.save()
            formset.save_m2m()
            return
        super().save_formset(request, form, formset, change)


@admin.register(PartNumber)
class PartNumberAdmin(DraftScopedAdminMixin, admin.ModelAdmin):
    supplier_lookup = "product__supplier_id"
    publication_lookup = "product__publication_status"
    product_field_name = "product"
    list_display = (
        "number_raw",
        "number_normalized",
        "part_number_type",
        "product",
        "brand",
        "is_primary",
    )
    list_filter = ("part_number_type", "is_primary", "brand")
    search_fields = ("number_raw", "number_normalized", "product__sku", "product__title")
    ordering = ("number_normalized",)
    list_select_related = ("product", "part_number_type", "brand", "product__supplier")
    autocomplete_fields = ("product", "brand")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "updated_at"


@admin.register(AttributeDefinition)
class AttributeDefinitionAdmin(ReferenceDataAdminMixin, admin.ModelAdmin):
    list_display = (
        "name",
        "data_type",
        "unit",
        "is_filterable",
        "is_visible_on_product",
        "allows_multiple_values",
        "sort_order",
    )
    list_filter = (
        "data_type",
        "is_filterable",
        "is_visible_on_product",
        "allows_multiple_values",
    )
    search_fields = ("name", "slug", "unit")
    ordering = ("sort_order", "name")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "updated_at"


@admin.register(ProductAttributeValue)
class ProductAttributeValueAdmin(DraftScopedAdminMixin, admin.ModelAdmin):
    supplier_lookup = "product__supplier_id"
    publication_lookup = "product__publication_status"
    product_field_name = "product"
    list_display = (
        "product",
        "attribute_definition",
        "value_text",
        "value_number",
        "value_boolean",
    )
    list_filter = ("attribute_definition", "attribute_definition__data_type")
    search_fields = ("product__sku", "product__title", "value_text", "value_normalized")
    ordering = ("product", "attribute_definition")
    list_select_related = ("product", "attribute_definition", "product__supplier")
    autocomplete_fields = ("product", "attribute_definition")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "updated_at"


@admin.register(ProductImage)
class ProductImageAdmin(DraftScopedAdminMixin, admin.ModelAdmin):
    supplier_lookup = "product__supplier_id"
    publication_lookup = "product__publication_status"
    product_field_name = "product"
    list_display = ("product", "sort_order", "is_primary", "updated_at")
    list_filter = ("is_primary",)
    search_fields = ("product__sku", "product__title", "alt_text")
    ordering = ("product", "sort_order", "id")
    list_select_related = ("product", "product__supplier")
    autocomplete_fields = ("product",)
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "updated_at"
