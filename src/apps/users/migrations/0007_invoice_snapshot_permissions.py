from django.db import migrations


ROLE_INTERNAL_STAFF = "internal_staff"
MODEL_NAMES = (
    "InvoiceIssuerConfiguration",
    "PaymentInvoiceSnapshot",
    "PaymentInvoiceLineSnapshot",
)
ALL_ACTIONS = ("add", "change", "delete", "view")


def add_permissions(apps, schema_editor):
    del schema_editor
    ContentType = apps.get_model("contenttypes", "ContentType")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group, _ = Group.objects.get_or_create(name=ROLE_INTERNAL_STAFF)
    permission_ids = []
    for model_name in MODEL_NAMES:
        model = apps.get_model("inquiries", model_name)
        content_type, _ = ContentType.objects.get_or_create(
            app_label="inquiries", model=model._meta.model_name
        )
        for action in ALL_ACTIONS:
            permission, _ = Permission.objects.get_or_create(
                content_type=content_type,
                codename=f"{action}_{model._meta.model_name}",
                defaults={"name": f"Can {action} {model._meta.verbose_name}"},
            )
            permission_ids.append(permission.id)
    group.permissions.add(*permission_ids)


def remove_permissions(apps, schema_editor):
    del schema_editor
    Group = apps.get_model("auth", "Group")
    group = Group.objects.filter(name=ROLE_INTERNAL_STAFF).first()
    if group is None:
        return
    model_names = tuple(name.lower() for name in MODEL_NAMES)
    group.permissions.remove(
        *group.permissions.filter(
            content_type__app_label="inquiries",
            content_type__model__in=model_names,
        )
    )


class Migration(migrations.Migration):
    dependencies = [
        ("inquiries", "0018_invoiceissuerconfiguration_and_more"),
        ("users", "0006_inquiry_offer_payment_details_permissions"),
    ]

    operations = [migrations.RunPython(add_permissions, remove_permissions)]
