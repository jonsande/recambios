from django.conf import settings
from django.db import models


class Supplier(models.Model):
    name = models.CharField(max_length=180, unique=True)
    slug = models.SlugField(max_length=180, unique=True)
    code = models.CharField(max_length=32, unique=True)
    country = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    contact_name = models.CharField(max_length=150, blank=True)
    contact_email = models.EmailField(blank=True)
    orders_email = models.EmailField(
        blank=True,
        help_text=(
            "Operational mailbox for orders, confirmed offers, and availability updates."
        ),
    )
    auto_send_offer_sent_notification = models.BooleanField(
        default=False,
        help_text=(
            "Enable automatic supplier notification when a customer-facing offer is sent."
        ),
    )
    auto_send_inquiry_submitted_notification = models.BooleanField(
        default=False,
        help_text=(
            "Enable automatic supplier inquiry notification when a customer inquiry is submitted."
        ),
    )
    inquiry_submitted_email_subject_template = models.TextField(
        blank=True,
        help_text=(
            "Optional subject template for automatic supplier inquiry notifications. "
            "Supports Django template variables such as inquiry, supplier, and items."
        ),
    )
    inquiry_submitted_email_body_template = models.TextField(
        blank=True,
        help_text=(
            "Optional body template for automatic supplier inquiry notifications. "
            "Supports Django template variables such as inquiry, supplier, and items."
        ),
    )
    offer_sent_email_subject_template = models.TextField(
        blank=True,
        help_text=(
            "Optional subject template for automatic supplier offer-sent notifications. "
            "Supports Django template variables such as offer, inquiry, supplier, and items."
        ),
    )
    offer_sent_email_body_template = models.TextField(
        blank=True,
        help_text=(
            "Optional body template for automatic supplier offer-sent notifications. "
            "Supports Django template variables such as offer, inquiry, supplier, and items."
        ),
    )
    contact_phone = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active", "name"], name="sup_supplier_active_name_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class SupplierUserAssignment(models.Model):
    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.CASCADE,
        related_name="user_assignments",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="supplier_assignments",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["supplier__name", "user__username"]
        constraints = [
            models.UniqueConstraint(
                fields=["supplier", "user"],
                name="sup_user_assignment_supplier_user_uq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "is_active"],
                name="sup_uasg_user_act_idx",
            ),
            models.Index(
                fields=["supplier", "is_active"],
                name="sup_uasg_sup_act_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} -> {self.supplier.code}"
