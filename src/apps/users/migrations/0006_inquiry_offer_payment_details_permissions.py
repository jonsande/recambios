from django.db import migrations


ROLE_INTERNAL_STAFF = "internal_staff"
MODEL_NAME = "InquiryOfferPaymentDetails"
ALL_ACTIONS = ("add", "change", "delete", "view")


def add_permissions(apps, schema_editor):
    del schema_editor
    ContentType = apps.get_model("contenttypes", "ContentType")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    model = apps.get_model("inquiries", MODEL_NAME)
    content_type, _ = ContentType.objects.get_or_create(
        app_label="inquiries",
        model=model._meta.model_name,
    )
    group, _ = Group.objects.get_or_create(name=ROLE_INTERNAL_STAFF)
    permission_ids = []
    for action in ALL_ACTIONS:
        codename = f"{action}_{model._meta.model_name}"
        permission, _ = Permission.objects.get_or_create(
            content_type=content_type,
            codename=codename,
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
    group.permissions.remove(
        *group.permissions.filter(
            content_type__app_label="inquiries",
            codename__endswith="_inquiryofferpaymentdetails",
        )
    )


class Migration(migrations.Migration):
    dependencies = [
        ("inquiries", "0009_inquiry_destination_country_and_more"),
        ("users", "0005_inquiry_submission_group_permissions"),
    ]

    operations = [migrations.RunPython(add_permissions, remove_permissions)]
