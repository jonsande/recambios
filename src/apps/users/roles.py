ROLE_ADMINISTRATOR = "administrator"
ROLE_INTERNAL_STAFF = "internal_staff"
ROLE_RESTRICTED_SUPPLIER = "restricted_supplier"
ROLE_REGISTERED_CUSTOMER = "registered_customer"

ROLE_NAMES = (
    ROLE_ADMINISTRATOR,
    ROLE_INTERNAL_STAFF,
    ROLE_RESTRICTED_SUPPLIER,
    ROLE_REGISTERED_CUSTOMER,
)


def user_has_role(user, role_name: str) -> bool:
    if not user.is_authenticated or not user.is_active:
        return False
    if role_name == ROLE_ADMINISTRATOR:
        return user.is_superuser
    return user.groups.filter(name=role_name).exists()


def is_internal_staff_user(user) -> bool:
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=ROLE_INTERNAL_STAFF).exists()


def is_restricted_supplier_user(user) -> bool:
    if not user.is_authenticated or not user.is_active or user.is_superuser:
        return False
    return user.groups.filter(name=ROLE_RESTRICTED_SUPPLIER).exists()
