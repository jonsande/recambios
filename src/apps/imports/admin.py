from django.contrib import admin
from django.core.exceptions import PermissionDenied

from apps.suppliers.access import get_active_supplier_ids_for_user, user_can_manage_supplier
from apps.users.roles import is_restricted_supplier_user

from .models import SupplierImport, SupplierImportRow


class SupplierImportRowInline(admin.TabularInline):
    model = SupplierImportRow
    extra = 0
    fields = ("row_number", "processing_status", "linked_product", "error_message")
    readonly_fields = ("row_number", "processing_status", "error_message")
    autocomplete_fields = ("linked_product",)
    show_change_link = True
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if is_restricted_supplier_user(request.user):
            readonly_fields.append("linked_product")
        return tuple(dict.fromkeys(readonly_fields))


@admin.register(SupplierImport)
class SupplierImportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "supplier",
        "uploaded_by",
        "import_status",
        "total_rows",
        "successful_rows",
        "failed_rows",
        "started_at",
        "finished_at",
        "updated_at",
    )
    list_filter = ("import_status", "supplier")
    search_fields = ("id", "supplier__name", "supplier__code", "uploaded_by__username")
    ordering = ("-created_at",)
    list_select_related = ("supplier", "uploaded_by")
    autocomplete_fields = ("supplier", "uploaded_by")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "updated_at"
    inlines = (SupplierImportRowInline,)

    def supplier_ids_for_request(self, request) -> list[int]:
        return get_active_supplier_ids_for_user(request.user)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if is_restricted_supplier_user(request.user):
            supplier_ids = self.supplier_ids_for_request(request)
            return queryset.filter(supplier_id__in=supplier_ids)
        return queryset

    def has_view_permission(self, request, obj=None):
        if is_restricted_supplier_user(request.user) and obj is not None:
            return user_can_manage_supplier(request.user, obj.supplier_id)
        return super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        if is_restricted_supplier_user(request.user):
            supplier_scope_exists = bool(self.supplier_ids_for_request(request))
            return supplier_scope_exists and super().has_add_permission(request)
        return super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        allowed = super().has_change_permission(request, obj)
        if not is_restricted_supplier_user(request.user):
            return allowed
        if obj is None:
            return allowed
        return False

    def has_delete_permission(self, request, obj=None):
        if is_restricted_supplier_user(request.user):
            return False
        return super().has_delete_permission(request, obj)

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        if not is_restricted_supplier_user(request.user):
            return form

        supplier_ids = self.supplier_ids_for_request(request)
        form.base_fields["supplier"].queryset = form.base_fields["supplier"].queryset.filter(
            id__in=supplier_ids
        )
        if len(supplier_ids) == 1 and obj is None:
            form.base_fields["supplier"].initial = supplier_ids[0]
        return form

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if is_restricted_supplier_user(request.user):
            readonly_fields.extend(
                (
                    "uploaded_by",
                    "import_status",
                    "total_rows",
                    "successful_rows",
                    "failed_rows",
                    "started_at",
                    "finished_at",
                )
            )
        return tuple(dict.fromkeys(readonly_fields))

    def save_model(self, request, obj, form, change):
        if is_restricted_supplier_user(request.user):
            supplier_ids = set(self.supplier_ids_for_request(request))
            if obj.supplier_id not in supplier_ids:
                raise PermissionDenied("This import is outside your supplier scope.")
            obj.uploaded_by = request.user
            obj.import_status = SupplierImport.ImportStatus.PENDING
            obj.total_rows = 0
            obj.successful_rows = 0
            obj.failed_rows = 0
            obj.started_at = None
            obj.finished_at = None
        elif not obj.uploaded_by:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(SupplierImportRow)
class SupplierImportRowAdmin(admin.ModelAdmin):
    list_display = (
        "supplier_import",
        "row_number",
        "processing_status",
        "linked_product",
        "updated_at",
    )
    list_filter = ("processing_status", "supplier_import__supplier")
    search_fields = ("supplier_import__id", "linked_product__sku", "error_message")
    ordering = ("supplier_import", "row_number")
    list_select_related = ("supplier_import", "linked_product", "supplier_import__supplier")
    autocomplete_fields = ("supplier_import", "linked_product")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "updated_at"

    def supplier_ids_for_request(self, request) -> list[int]:
        return get_active_supplier_ids_for_user(request.user)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if is_restricted_supplier_user(request.user):
            supplier_ids = self.supplier_ids_for_request(request)
            return queryset.filter(supplier_import__supplier_id__in=supplier_ids)
        return queryset

    def has_view_permission(self, request, obj=None):
        if is_restricted_supplier_user(request.user) and obj is not None:
            return user_can_manage_supplier(request.user, obj.supplier_import.supplier_id)
        return super().has_view_permission(request, obj)

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
