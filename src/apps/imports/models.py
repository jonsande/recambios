from django.conf import settings
from django.db import models


class SupplierImport(models.Model):
    class ImportStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        COMPLETED_WITH_ERRORS = "completed_with_errors", "Completed With Errors"
        FAILED = "failed", "Failed"

    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.PROTECT,
        related_name="imports",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supplier_imports",
    )
    original_file = models.FileField(upload_to="supplier_imports/%Y/%m/%d/", null=True, blank=True)
    import_status = models.CharField(
        max_length=24,
        choices=ImportStatus.choices,
        default=ImportStatus.PENDING,
        db_index=True,
    )
    total_rows = models.PositiveIntegerField(default=0)
    successful_rows = models.PositiveIntegerField(default=0)
    failed_rows = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["supplier", "import_status"],
                name="imports_supplier_status_idx",
            ),
            models.Index(fields=["created_at"], name="imports_created_at_idx"),
        ]

    def __str__(self) -> str:
        return f"Import {self.id} · {self.supplier.code}"


class SupplierImportRow(models.Model):
    class ProcessingStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        SKIPPED = "skipped", "Skipped"
        ERROR = "error", "Error"

    supplier_import = models.ForeignKey(
        "imports.SupplierImport",
        on_delete=models.CASCADE,
        related_name="rows",
    )
    row_number = models.PositiveIntegerField()
    raw_payload = models.JSONField(default=dict, blank=True)
    processing_status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING,
        db_index=True,
    )
    linked_product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="import_rows",
    )
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["supplier_import", "row_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["supplier_import", "row_number"],
                name="imports_row_import_row_number_uq",
            )
        ]
        indexes = [
            models.Index(
                fields=["supplier_import", "processing_status"],
                name="imports_row_status_idx",
            ),
            models.Index(fields=["linked_product"], name="imports_row_linked_product_idx"),
        ]

    def __str__(self) -> str:
        return f"Import {self.supplier_import_id} · row {self.row_number}"
