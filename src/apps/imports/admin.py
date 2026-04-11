from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.urls import path, reverse

from apps.suppliers.access import get_active_supplier_ids_for_user, user_can_manage_supplier
from apps.users.roles import is_internal_staff_user, is_restricted_supplier_user

from .models import SupplierImport, SupplierImportRow
from .services import run_supplier_import
from .template_builder import build_supplier_import_template_xlsx


class SupplierImportAdminForm(forms.ModelForm):
    class Meta:
        model = SupplierImport
        fields = "__all__"

    def clean_original_file(self):
        original_file = self.cleaned_data.get("original_file")
        if original_file is None and not self.instance.pk:
            raise forms.ValidationError("Upload an .xlsx file to create an import.")
        if original_file is not None and not original_file.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Only .xlsx files are supported for v1 imports.")
        return original_file


class SupplierImportRowInline(admin.TabularInline):
    model = SupplierImportRow
    extra = 0
    fields = (
        "row_number",
        "processing_status",
        "linked_product",
        "error_message",
        "raw_payload",
    )
    readonly_fields = (
        "row_number",
        "processing_status",
        "linked_product",
        "error_message",
        "raw_payload",
    )
    autocomplete_fields = ("linked_product",)
    show_change_link = True
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SupplierImport)
class SupplierImportAdmin(admin.ModelAdmin):
    form = SupplierImportAdminForm
    change_list_template = "admin/imports/supplierimport/change_list.html"
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
        "processing_notes_short",
        "updated_at",
    )
    list_filter = ("import_status", "supplier")
    search_fields = (
        "id",
        "supplier__name",
        "supplier__code",
        "uploaded_by__username",
        "processing_notes",
    )
    ordering = ("-created_at",)
    list_select_related = ("supplier", "uploaded_by")
    autocomplete_fields = ("supplier", "uploaded_by")
    readonly_fields = ("created_at", "updated_at", "processing_notes")
    date_hierarchy = "updated_at"
    inlines = (SupplierImportRowInline,)
    actions = ("process_selected_imports",)

    fieldsets = (
        (
            "Import File",
            {
                "fields": (
                    "supplier",
                    "original_file",
                    "uploaded_by",
                )
            },
        ),
        (
            "Processing",
            {
                "fields": (
                    "import_status",
                    "total_rows",
                    "successful_rows",
                    "failed_rows",
                    "started_at",
                    "finished_at",
                    "processing_notes",
                )
            },
        ),
        ("Audit", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Notes")
    def processing_notes_short(self, obj: SupplierImport) -> str:
        if not obj.processing_notes:
            return "-"
        first_line = obj.processing_notes.splitlines()[0]
        if len(first_line) <= 80:
            return first_line
        return f"{first_line[:77]}..."

    def supplier_ids_for_request(self, request) -> list[int]:
        return get_active_supplier_ids_for_user(request.user)

    def _can_process_imports(self, request) -> bool:
        return is_internal_staff_user(request.user)

    def get_urls(self):
        custom_urls = [
            path(
                "download-template/",
                self.admin_site.admin_view(self.download_template_view),
                name="imports_supplierimport_download_template",
            )
        ]
        return custom_urls + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["import_template_download_url"] = reverse(
            "admin:imports_supplierimport_download_template"
        )
        return super().changelist_view(request, extra_context=extra_context)

    def download_template_view(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied
        content = build_supplier_import_template_xlsx()
        response = HttpResponse(
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="supplier_import_template_v1.xlsx"'
        return response

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not self._can_process_imports(request):
            actions.pop("process_selected_imports", None)
        return actions

    @admin.action(description="Process selected imports")
    def process_selected_imports(self, request, queryset):
        if not self._can_process_imports(request):
            self.message_user(
                request,
                "You do not have permission to process imports.",
                level=messages.ERROR,
            )
            return

        eligible_statuses = {
            SupplierImport.ImportStatus.PENDING,
            SupplierImport.ImportStatus.FAILED,
            SupplierImport.ImportStatus.COMPLETED_WITH_ERRORS,
        }
        processed = 0
        completed_with_errors = 0
        failed = 0
        skipped = 0

        for import_record in queryset.select_related("supplier"):
            if import_record.import_status not in eligible_statuses:
                skipped += 1
                continue
            result = run_supplier_import(import_record=import_record, requested_by=request.user)
            if result.import_status == SupplierImport.ImportStatus.COMPLETED:
                processed += 1
            elif result.import_status == SupplierImport.ImportStatus.COMPLETED_WITH_ERRORS:
                completed_with_errors += 1
            else:
                failed += 1

        if processed:
            self.message_user(
                request,
                f"Processed successfully: {processed}.",
                level=messages.SUCCESS,
            )
        if completed_with_errors:
            self.message_user(
                request,
                f"Processed with row warnings/errors: {completed_with_errors}.",
                level=messages.WARNING,
            )
        if failed:
            self.message_user(
                request,
                f"Failed imports: {failed}. Review processing notes.",
                level=messages.ERROR,
            )
        if skipped:
            self.message_user(
                request,
                f"Skipped (status not eligible for manual processing): {skipped}.",
                level=messages.INFO,
            )

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
                    "processing_notes",
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
            obj.processing_notes = ""
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
    readonly_fields = (
        "supplier_import",
        "row_number",
        "processing_status",
        "linked_product",
        "error_message",
        "raw_payload",
        "created_at",
        "updated_at",
    )
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
