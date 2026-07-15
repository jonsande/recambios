from django.db import migrations


ROLE_INTERNAL_STAFF = "internal_staff"
MODEL_NAME = "InquirySubmissionGroup"
ALL_ACTIONS = ("add", "change", "delete", "view")


def default_permission_name(model, codename: str) -> str:
    action_map = {
        "add": "Can add",
        "change": "Can change",
        "delete": "Can delete",
        "view": "Can view",
    }
    action = codename.split("_", 1)[0]
    return f"{action_map[action]} {model._meta.verbose_name}"


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
            defaults={"name": default_permission_name(model, codename)},
        )
        permission_ids.append(permission.id)
    group.permissions.add(*permission_ids)


def remove_permissions(apps, schema_editor):
    del schema_editor
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group = Group.objects.filter(name=ROLE_INTERNAL_STAFF).first()
    if group is None:
        return
    codenames = [f"{action}_inquirysubmissiongroup" for action in ALL_ACTIONS]
    permissions = Permission.objects.filter(
        content_type__app_label="inquiries",
        codename__in=codenames,
    )
    group.permissions.remove(*permissions)


class Migration(migrations.Migration):
    dependencies = [
        ("inquiries", "0008_inquirysubmissiongroup_inquiry_submission_group_and_more"),
        ("users", "0004_inquiry_offer_payment_permissions"),
    ]

    operations = [migrations.RunPython(add_permissions, remove_permissions)]
