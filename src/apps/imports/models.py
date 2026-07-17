from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class SupplierImport(models.Model):
    class ImportStatus(models.TextChoices):
        PENDING = "pending", _("Pendiente")
        PROCESSING = "processing", _("En proceso")
        COMPLETED = "completed", _("Completada")
        COMPLETED_WITH_ERRORS = "completed_with_errors", _("Completada con errores")
        FAILED = "failed", _("Fallida")

    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.PROTECT,
        related_name="imports",
        verbose_name=_("proveedor"),
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supplier_imports",
        verbose_name=_("subida por"),
    )
    original_file = models.FileField(
        _("archivo original"),
        upload_to="supplier_imports/%Y/%m/%d/",
        null=True,
        blank=True,
    )
    import_status = models.CharField(
        _("estado de importación"),
        max_length=24,
        choices=ImportStatus.choices,
        default=ImportStatus.PENDING,
        db_index=True,
    )
    total_rows = models.PositiveIntegerField(_("filas totales"), default=0)
    successful_rows = models.PositiveIntegerField(_("filas correctas"), default=0)
    failed_rows = models.PositiveIntegerField(_("filas con error"), default=0)
    processing_notes = models.TextField(_("notas de procesamiento"), blank=True)
    started_at = models.DateTimeField(_("iniciada el"), null=True, blank=True)
    finished_at = models.DateTimeField(_("finalizada el"), null=True, blank=True)
    created_at = models.DateTimeField(_("creada el"), auto_now_add=True)
    updated_at = models.DateTimeField(_("actualizada el"), auto_now=True)

    class Meta:
        verbose_name = _("importación de proveedor")
        verbose_name_plural = _("importaciones de proveedores")
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["supplier", "import_status"],
                name="imports_supplier_status_idx",
            ),
            models.Index(fields=["created_at"], name="imports_created_at_idx"),
        ]

    def __str__(self) -> str:
        return f"Import {self.id} - {self.supplier.code}"


class SupplierImportRow(models.Model):
    class ProcessingStatus(models.TextChoices):
        PENDING = "pending", _("Pendiente")
        SUCCESS = "success", _("Correcta")
        SKIPPED = "skipped", _("Omitida")
        ERROR = "error", _("Error")

    supplier_import = models.ForeignKey(
        "imports.SupplierImport",
        on_delete=models.CASCADE,
        related_name="rows",
        verbose_name=_("importación de proveedor"),
    )
    row_number = models.PositiveIntegerField(_("número de fila"))
    raw_payload = models.JSONField(_("datos originales"), default=dict, blank=True)
    processing_status = models.CharField(
        _("estado de procesamiento"),
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
        verbose_name=_("producto vinculado"),
    )
    error_message = models.TextField(_("mensaje de error"), blank=True)
    created_at = models.DateTimeField(_("creada el"), auto_now_add=True)
    updated_at = models.DateTimeField(_("actualizada el"), auto_now=True)

    class Meta:
        verbose_name = _("fila de importación")
        verbose_name_plural = _("filas de importación")
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
        return f"Import {self.supplier_import.pk} - row {self.row_number}"
