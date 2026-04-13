from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied

from apps.catalog.models import Product
from apps.suppliers.access import get_active_supplier_ids_for_user, user_can_manage_supplier
from apps.users.roles import is_restricted_supplier_user

from .models import ProductVehicleFitment, Vehicle


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = (
        "brand",
        "model",
        "generation",
        "variant",
        "vehicle_type",
        "fuel_type",
        "year_start",
        "year_end",
        "is_active",
    )
    list_filter = ("vehicle_type", "fuel_type", "is_active", "brand")
    search_fields = ("brand__name", "model", "generation", "variant", "engine_code")
    ordering = ("brand__name", "model", "generation", "variant")
    list_select_related = ("brand",)
    autocomplete_fields = ("brand",)
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "updated_at"

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


@admin.register(ProductVehicleFitment)
class ProductVehicleFitmentAdmin(admin.ModelAdmin):
    list_display = ("product", "vehicle", "source", "is_verified", "updated_at")
    list_filter = ("source", "is_verified", "vehicle__vehicle_type")
    search_fields = ("product__sku", "product__title", "vehicle__brand__name", "vehicle__model")
    ordering = ("product__sku", "vehicle__brand__name", "vehicle__model")
    list_select_related = ("product", "vehicle", "product__supplier", "vehicle__brand")
    autocomplete_fields = ("product", "vehicle")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "updated_at"
    actions = (
        "mark_selected_as_verified",
        "mark_selected_as_unverified",
        "set_source_supplier",
        "set_source_import",
        "set_source_manual",
    )

    def supplier_ids_for_request(self, request) -> list[int]:
        return get_active_supplier_ids_for_user(request.user)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if is_restricted_supplier_user(request.user):
            supplier_ids = self.supplier_ids_for_request(request)
            return queryset.filter(product__supplier_id__in=supplier_ids)
        return queryset

    def has_view_permission(self, request, obj=None):
        if is_restricted_supplier_user(request.user) and obj is not None:
            return user_can_manage_supplier(request.user, obj.product.supplier_id)
        return super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        if is_restricted_supplier_user(request.user):
            supplier_scope_exists = bool(self.supplier_ids_for_request(request))
            return supplier_scope_exists and super().has_add_permission(request)
        return super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        allowed = super().has_change_permission(request, obj)
        if not is_restricted_supplier_user(request.user) or obj is None:
            return allowed
        return (
            allowed
            and user_can_manage_supplier(request.user, obj.product.supplier_id)
            and obj.product.publication_status == obj.product.PublicationStatus.DRAFT
        )

    def has_delete_permission(self, request, obj=None):
        allowed = super().has_delete_permission(request, obj)
        if not is_restricted_supplier_user(request.user) or obj is None:
            return allowed
        return (
            allowed
            and user_can_manage_supplier(request.user, obj.product.supplier_id)
            and obj.product.publication_status == obj.product.PublicationStatus.DRAFT
        )

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        if not is_restricted_supplier_user(request.user):
            return form
        supplier_ids = self.supplier_ids_for_request(request)
        form.base_fields["product"].queryset = form.base_fields["product"].queryset.filter(
            supplier_id__in=supplier_ids,
            publication_status=Product.PublicationStatus.DRAFT,
        )
        form.base_fields["vehicle"].queryset = form.base_fields["vehicle"].queryset.filter(
            is_active=True
        )
        return form

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if is_restricted_supplier_user(request.user):
            readonly_fields.extend(("source", "is_verified"))
        return tuple(dict.fromkeys(readonly_fields))

    def get_actions(self, request):
        actions = super().get_actions(request)
        if is_restricted_supplier_user(request.user):
            actions.pop("mark_selected_as_verified", None)
            actions.pop("mark_selected_as_unverified", None)
            actions.pop("set_source_supplier", None)
            actions.pop("set_source_import", None)
            actions.pop("set_source_manual", None)
        return actions

    def _bulk_update_is_verified(self, request, queryset, is_verified, label):
        if is_restricted_supplier_user(request.user):
            self.message_user(
                request,
                "Supplier users cannot bulk-edit verification fields.",
                level=messages.ERROR,
            )
            return

        total_selected = queryset.count()
        queryset = queryset.exclude(is_verified=is_verified)
        updated_count = queryset.update(is_verified=is_verified)
        skipped_count = total_selected - updated_count

        if updated_count:
            self.message_user(
                request,
                f"{label} applied to {updated_count} fitment(s).",
                level=messages.SUCCESS,
            )
        if skipped_count:
            self.message_user(
                request,
                f"Skipped {skipped_count} fitment(s) because no change was needed.",
                level=messages.WARNING,
            )

    def _bulk_update_source(self, request, queryset, source, label):
        if is_restricted_supplier_user(request.user):
            self.message_user(
                request,
                "Supplier users cannot bulk-edit source fields.",
                level=messages.ERROR,
            )
            return

        total_selected = queryset.count()
        queryset = queryset.exclude(source=source)
        updated_count = queryset.update(source=source)
        skipped_count = total_selected - updated_count

        if updated_count:
            self.message_user(
                request,
                f"{label} applied to {updated_count} fitment(s).",
                level=messages.SUCCESS,
            )
        if skipped_count:
            self.message_user(
                request,
                f"Skipped {skipped_count} fitment(s) because no change was needed.",
                level=messages.WARNING,
            )

    @admin.action(description="Set selected fitments as verified")
    def mark_selected_as_verified(self, request, queryset):
        self._bulk_update_is_verified(
            request=request,
            queryset=queryset,
            is_verified=True,
            label="Verified status",
        )

    @admin.action(description="Set selected fitments as not verified")
    def mark_selected_as_unverified(self, request, queryset):
        self._bulk_update_is_verified(
            request=request,
            queryset=queryset,
            is_verified=False,
            label="Not verified status",
        )

    @admin.action(description="Set source to Supplier")
    def set_source_supplier(self, request, queryset):
        self._bulk_update_source(
            request=request,
            queryset=queryset,
            source=ProductVehicleFitment.FitmentSource.SUPPLIER,
            label="Supplier source",
        )

    @admin.action(description="Set source to Import")
    def set_source_import(self, request, queryset):
        self._bulk_update_source(
            request=request,
            queryset=queryset,
            source=ProductVehicleFitment.FitmentSource.IMPORT,
            label="Import source",
        )

    @admin.action(description="Set source to Manual")
    def set_source_manual(self, request, queryset):
        self._bulk_update_source(
            request=request,
            queryset=queryset,
            source=ProductVehicleFitment.FitmentSource.MANUAL,
            label="Manual source",
        )

    def save_model(self, request, obj, form, change):
        if is_restricted_supplier_user(request.user):
            supplier_ids = set(self.supplier_ids_for_request(request))
            if obj.product.supplier_id not in supplier_ids:
                raise PermissionDenied("This product is outside your supplier scope.")
            if obj.product.publication_status != obj.product.PublicationStatus.DRAFT:
                raise PermissionDenied("Only draft products can be edited by suppliers.")
            obj.source = ProductVehicleFitment.FitmentSource.SUPPLIER
            obj.is_verified = False
        super().save_model(request, obj, form, change)
