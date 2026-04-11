from apps.users.roles import is_restricted_supplier_user

from .models import SupplierUserAssignment


def get_active_supplier_ids_for_user(user) -> list[int]:
    if not user.is_authenticated:
        return []
    return list(
        SupplierUserAssignment.objects.filter(
            user=user,
            is_active=True,
            supplier__is_active=True,
        ).values_list("supplier_id", flat=True)
    )


def user_can_manage_supplier(user, supplier_id: int | None) -> bool:
    if supplier_id is None:
        return False
    if not is_restricted_supplier_user(user):
        return True
    return SupplierUserAssignment.objects.filter(
        user=user,
        supplier_id=supplier_id,
        is_active=True,
        supplier__is_active=True,
    ).exists()
