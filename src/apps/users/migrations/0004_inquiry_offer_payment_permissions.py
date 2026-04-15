from django.db import migrations

ROLE_INTERNAL_STAFF = "internal_staff"
MODEL_NAME = "InquiryOfferPayment"
ALL_ACTIONS = ("add", "change", "delete", "view")


def default_permission_name(model, codename: str) -> str:
    action_map = {
        "add": "Can add",
        "change": "Can change",
        "delete": "Can delete",
        "view": "Can view",
    }
    action = codename.split("_", 1)[0]
    if action in action_map:
        return f"{action_map[action]} {model._meta.verbose_name}"
    return codename.replace("_", " ").capitalize()


def get_or_create_permission(apps, app_label: str, model_name: str, codename: str):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    model = apps.get_model(app_label, model_name)
    content_type, _ = ContentType.objects.get_or_create(
        app_label=app_label,
        model=model._meta.model_name,
    )
    permission, _ = Permission.objects.get_or_create(
        content_type=content_type,
        codename=codename,
        defaults={"name": default_permission_name(model, codename)},
    )
    return permission


def add_inquiry_offer_payment_permissions_to_internal_staff(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    group, _ = Group.objects.get_or_create(name=ROLE_INTERNAL_STAFF)

    permission_ids = []
    for action in ALL_ACTIONS:
        codename = f"{action}_{MODEL_NAME.lower()}"
        permission = get_or_create_permission(apps, "inquiries", MODEL_NAME, codename)
        permission_ids.append(permission.id)

    group.permissions.add(*permission_ids)


def remove_inquiry_offer_payment_permissions_from_internal_staff(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    try:
        group = Group.objects.get(name=ROLE_INTERNAL_STAFF)
    except Group.DoesNotExist:
        return

    codenames = [f"{action}_{MODEL_NAME.lower()}" for action in ALL_ACTIONS]
    permissions = Permission.objects.filter(
        content_type__app_label="inquiries",
        codename__in=codenames,
    )
    group.permissions.remove(*permissions)


class Migration(migrations.Migration):
    dependencies = [
        ("inquiries", "0005_inquiryofferpayment"),
        ("users", "0003_inquiry_offer_permissions"),
    ]

    operations = [
        migrations.RunPython(
            add_inquiry_offer_payment_permissions_to_internal_staff,
            remove_inquiry_offer_payment_permissions_from_internal_staff,
        ),
    ]
