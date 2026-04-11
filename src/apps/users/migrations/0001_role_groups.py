from django.db import migrations

ROLE_ADMINISTRATOR = "administrator"
ROLE_INTERNAL_STAFF = "internal_staff"
ROLE_RESTRICTED_SUPPLIER = "restricted_supplier"
ROLE_REGISTERED_CUSTOMER = "registered_customer"

ROLE_GROUPS = (
    ROLE_ADMINISTRATOR,
    ROLE_INTERNAL_STAFF,
    ROLE_RESTRICTED_SUPPLIER,
    ROLE_REGISTERED_CUSTOMER,
)


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
    if codename == "can_publish_product":
        return "Can publish product"
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


def build_role_permissions(apps):
    all_actions = ("add", "change", "delete", "view")
    internal_staff_targets = [
        ("catalog", "Brand", all_actions),
        ("catalog", "Category", all_actions),
        ("catalog", "Condition", all_actions),
        ("catalog", "Product", all_actions + ("can_publish_product",)),
        ("catalog", "PartNumber", all_actions),
        ("catalog", "AttributeDefinition", all_actions),
        ("catalog", "ProductAttributeValue", all_actions),
        ("catalog", "ProductImage", all_actions),
        ("suppliers", "Supplier", all_actions),
        ("suppliers", "SupplierUserAssignment", all_actions),
        ("vehicles", "Vehicle", all_actions),
        ("vehicles", "ProductVehicleFitment", all_actions),
        ("imports", "SupplierImport", all_actions),
        ("imports", "SupplierImportRow", all_actions),
        ("auth", "User", all_actions),
        ("auth", "Group", all_actions),
    ]
    restricted_supplier_targets = [
        ("catalog", "Brand", ("view",)),
        ("catalog", "Category", ("view",)),
        ("catalog", "Condition", ("view",)),
        ("catalog", "AttributeDefinition", ("view",)),
        ("catalog", "Product", all_actions),
        ("catalog", "PartNumber", all_actions),
        ("catalog", "ProductAttributeValue", all_actions),
        ("catalog", "ProductImage", all_actions),
        ("suppliers", "Supplier", ("view",)),
        ("vehicles", "Vehicle", ("view",)),
        ("vehicles", "ProductVehicleFitment", all_actions),
        ("imports", "SupplierImport", ("add", "change", "view")),
        ("imports", "SupplierImportRow", ("view",)),
    ]

    role_permissions = {
        ROLE_ADMINISTRATOR: set(),
        ROLE_INTERNAL_STAFF: set(),
        ROLE_RESTRICTED_SUPPLIER: set(),
        ROLE_REGISTERED_CUSTOMER: set(),
    }

    for app_label, model_name, actions in internal_staff_targets:
        for action in actions:
            codename = action if action == "can_publish_product" else f"{action}_{model_name.lower()}"
            permission = get_or_create_permission(apps, app_label, model_name, codename)
            role_permissions[ROLE_INTERNAL_STAFF].add(permission.id)

    for app_label, model_name, actions in restricted_supplier_targets:
        for action in actions:
            codename = f"{action}_{model_name.lower()}"
            permission = get_or_create_permission(apps, app_label, model_name, codename)
            role_permissions[ROLE_RESTRICTED_SUPPLIER].add(permission.id)

    return role_permissions


def sync_role_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    role_permissions = build_role_permissions(apps)

    for role_name in ROLE_GROUPS:
        group, _ = Group.objects.get_or_create(name=role_name)
        group.permissions.set(role_permissions[role_name])


def remove_role_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=ROLE_GROUPS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("catalog", "0002_alter_product_options"),
        ("suppliers", "0002_supplieruserassignment"),
        ("vehicles", "0001_initial"),
        ("imports", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(sync_role_groups, remove_role_groups),
    ]
