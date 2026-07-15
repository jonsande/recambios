from decimal import Decimal

import pytest
from django.contrib import admin
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError

from apps.catalog.models import Brand, Category, Condition, Product
from apps.inquiries.models import Inquiry, InquiryItem, InquirySubmissionGroup
from apps.suppliers.models import Supplier
from apps.users.roles import ROLE_INTERNAL_STAFF, ROLE_RESTRICTED_SUPPLIER


def make_supplier(code: str = "SUP-INQ") -> Supplier:
    return Supplier.objects.create(
        name=f"Supplier {code}",
        slug=f"supplier-{code.lower()}",
        code=code,
    )


def make_brand(name: str = "Brembo", slug: str = "brembo") -> Brand:
    return Brand.objects.create(name=name, slug=slug, brand_type=Brand.BrandType.PARTS)


def make_category(name: str = "Brake Pads", slug: str = "brake-pads") -> Category:
    return Category.objects.create(name=name, slug=slug)


def make_condition(code: str = "new", name: str = "Nuevo", slug: str = "new") -> Condition:
    return Condition.objects.create(code=code, name=name, slug=slug)


def make_product(
    sku: str = "SKU-INQ-1",
    price: Decimal | None = Decimal("99.90"),
) -> Product:
    supplier = make_supplier(code=f"SUP-{sku}")
    brand = make_brand(name=f"Brand {sku}", slug=f"brand-{sku.lower()}")
    category = make_category(name=f"Category {sku}", slug=f"category-{sku.lower()}")
    condition = make_condition(
        code=f"cond-{sku.lower()}",
        name=f"Cond {sku}",
        slug=f"cond-{sku.lower()}",
    )
    return Product.objects.create(
        supplier=supplier,
        supplier_product_code=f"{supplier.code}-{sku}",
        sku=sku,
        slug=f"product-{sku.lower()}",
        title=f"Product {sku}",
        brand=brand,
        category=category,
        condition=condition,
        last_known_price=price,
    )


@pytest.mark.django_db
def test_registered_user_inquiry_is_valid_and_defaults_to_submitted(django_user_model) -> None:
    user = django_user_model.objects.create_user(
        username="registered_customer",
        email="registered@example.com",
        password="pass1234",
    )

    inquiry = Inquiry.objects.create(user=user, notes_from_customer="Need lead time")

    assert inquiry.status == Inquiry.Status.SUBMITTED
    assert inquiry.reference_code.startswith("INQ-")


@pytest.mark.django_db
def test_guest_inquiry_requires_name_and_email() -> None:
    inquiry = Inquiry(
        guest_name="Guest Buyer",
        guest_email="guest@example.com",
        guest_phone="+34 600 111 222",
    )
    inquiry.full_clean()
    inquiry.save()

    invalid_inquiry = Inquiry(guest_name="", guest_email="", guest_phone="+34 600 333 444")
    with pytest.raises(ValidationError):
        invalid_inquiry.full_clean()


@pytest.mark.django_db
def test_submission_group_generates_reference_and_requires_guest_contact() -> None:
    submission_group = InquirySubmissionGroup.objects.create(
        guest_name="Grouped Guest",
        guest_email="GROUPED@EXAMPLE.COM",
        notes_from_customer="  Shared note  ",
    )

    assert submission_group.reference_code.startswith("REQ-")
    assert submission_group.guest_email == "grouped@example.com"
    assert submission_group.notes_from_customer == "Shared note"

    with pytest.raises(ValidationError):
        InquirySubmissionGroup.objects.create(guest_name="", guest_email="")


@pytest.mark.django_db
def test_submission_group_relates_independent_inquiries_without_limiting_legacy_shape(
    django_user_model,
) -> None:
    user = django_user_model.objects.create_user(
        username="grouped_customer",
        email="grouped.customer@example.com",
        password="pass1234",
    )
    submission_group = InquirySubmissionGroup.objects.create(
        user=user,
        guest_name="Grouped Customer",
        guest_email=user.email,
    )
    grouped_inquiry = Inquiry.objects.create(user=user, submission_group=submission_group)
    legacy_inquiry = Inquiry.objects.create(user=user)
    first_product = make_product(sku="SKU-INQ-GROUPED")
    second_product = make_product(sku="SKU-INQ-LEGACY-1")
    third_product = make_product(sku="SKU-INQ-LEGACY-2")

    InquiryItem.objects.create(inquiry=grouped_inquiry, product=first_product)
    InquiryItem.objects.create(inquiry=legacy_inquiry, product=second_product)
    InquiryItem.objects.create(inquiry=legacy_inquiry, product=third_product)

    assert list(submission_group.inquiries.all()) == [grouped_inquiry]
    assert grouped_inquiry.items.count() == 1
    assert legacy_inquiry.submission_group_id is None
    assert legacy_inquiry.items.count() == 2


@pytest.mark.django_db
def test_submission_group_is_registered_in_admin_for_operational_visibility() -> None:
    assert InquirySubmissionGroup in admin.site._registry
    group_admin = admin.site._registry[InquirySubmissionGroup]
    assert group_admin.inlines
    assert "reference_code" in group_admin.search_fields
    assert "inquiries__reference_code" in group_admin.search_fields


@pytest.mark.django_db
def test_inquiry_status_transition_rules_are_explicit(django_user_model) -> None:
    user = django_user_model.objects.create_user(
        username="status_user",
        email="status@example.com",
        password="pass1234",
    )
    inquiry = Inquiry.objects.create(user=user)

    assert inquiry.can_transition_to(Inquiry.Status.IN_REVIEW)
    assert not inquiry.can_transition_to(Inquiry.Status.ACCEPTED)

    inquiry.transition_to(Inquiry.Status.IN_REVIEW)
    assert inquiry.status == Inquiry.Status.IN_REVIEW

    with pytest.raises(ValueError):
        inquiry.transition_to(Inquiry.Status.ACCEPTED)


@pytest.mark.django_db
def test_inquiry_item_enforces_unique_product_per_inquiry(django_user_model) -> None:
    user = django_user_model.objects.create_user(
        username="item_user",
        email="item@example.com",
        password="pass1234",
    )
    inquiry = Inquiry.objects.create(user=user)
    product = make_product(sku="SKU-INQ-UNIQ")

    InquiryItem.objects.create(inquiry=inquiry, product=product, requested_quantity=2)

    with pytest.raises(ValidationError):
        InquiryItem.objects.create(inquiry=inquiry, product=product, requested_quantity=1)


@pytest.mark.django_db
def test_inquiry_item_rejects_non_positive_quantity(django_user_model) -> None:
    user = django_user_model.objects.create_user(
        username="quantity_user",
        email="quantity@example.com",
        password="pass1234",
    )
    inquiry = Inquiry.objects.create(user=user)
    product = make_product(sku="SKU-INQ-QTY")

    with pytest.raises(ValidationError):
        InquiryItem.objects.create(inquiry=inquiry, product=product, requested_quantity=0)


@pytest.mark.django_db
def test_inquiry_item_uses_last_known_price_snapshot_on_create(django_user_model) -> None:
    user = django_user_model.objects.create_user(
        username="snapshot_user",
        email="snapshot@example.com",
        password="pass1234",
    )
    inquiry = Inquiry.objects.create(user=user)
    product = make_product(sku="SKU-INQ-PRICE", price=Decimal("120.00"))

    inquiry_item = InquiryItem.objects.create(
        inquiry=inquiry,
        product=product,
        requested_quantity=1,
    )

    assert inquiry_item.last_known_price_snapshot == Decimal("120.00")

    product.last_known_price = Decimal("150.00")
    product.save(update_fields=["last_known_price"])
    inquiry_item.refresh_from_db()

    assert inquiry_item.last_known_price_snapshot == Decimal("120.00")


@pytest.mark.django_db
def test_internal_staff_has_inquiry_permissions_and_restricted_supplier_does_not() -> None:
    internal_staff = Group.objects.get(name=ROLE_INTERNAL_STAFF)
    restricted_supplier = Group.objects.get(name=ROLE_RESTRICTED_SUPPLIER)

    assert internal_staff.permissions.filter(
        content_type__app_label="inquiries",
        codename="view_inquiry",
    ).exists()
    assert internal_staff.permissions.filter(
        content_type__app_label="inquiries",
        codename="view_inquirysubmissiongroup",
    ).exists()
    assert internal_staff.permissions.filter(
        content_type__app_label="inquiries",
        codename="change_inquiryitem",
    ).exists()

    assert not restricted_supplier.permissions.filter(
        content_type__app_label="inquiries",
        codename="view_inquiry",
    ).exists()
