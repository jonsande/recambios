from decimal import Decimal

import pytest
from django.core import mail

from apps.catalog.models import Brand, Category, Condition, Product
from apps.inquiries.models import Inquiry, InquiryItem
from apps.suppliers.models import Supplier


def make_product(sku: str = "SKU-INQ-EMAIL") -> Product:
    supplier = Supplier.objects.create(
        name=f"Supplier {sku}",
        slug=f"supplier-{sku.lower()}",
        code=f"SUP-{sku}",
    )
    brand = Brand.objects.create(
        name=f"Brand {sku}",
        slug=f"brand-{sku.lower()}",
        brand_type=Brand.BrandType.PARTS,
    )
    category = Category.objects.create(
        name=f"Category {sku}",
        slug=f"category-{sku.lower()}",
    )
    condition = Condition.objects.create(
        code=f"cond-{sku.lower()}",
        name=f"Condition {sku}",
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
        last_known_price=Decimal("99.90"),
    )


@pytest.fixture
def email_settings(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "Recambios <noreply@example.com>"
    settings.SERVER_EMAIL = "Server <server@example.com>"
    settings.INQUIRY_INTERNAL_NOTIFICATION_EMAILS = ["internal-team@example.com"]
    settings.INQUIRY_CUSTOMER_REPLY_TO_EMAIL = "atencion@example.com"


@pytest.mark.django_db(transaction=True)
def test_sends_internal_and_customer_emails_on_draft_to_submitted_transition(
    django_user_model,
    email_settings,
) -> None:
    user = django_user_model.objects.create_user(
        username="phase8user",
        email="phase8@example.com",
        password="pass1234",
    )
    inquiry = Inquiry.objects.create(
        user=user,
        status=Inquiry.Status.DRAFT,
        language=Inquiry.Language.SPANISH,
        notes_from_customer="Necesito plazo de entrega",
    )
    InquiryItem.objects.create(
        inquiry=inquiry,
        product=make_product("SKU-INQ-EMAIL-TRANS"),
        requested_quantity=2,
    )

    mail.outbox.clear()
    inquiry.status = Inquiry.Status.SUBMITTED
    inquiry.save(update_fields=["status"])

    assert len(mail.outbox) == 2

    internal_email = mail.outbox[0]
    customer_email = mail.outbox[1]

    assert internal_email.to == ["internal-team@example.com"]
    assert inquiry.reference_code in internal_email.subject
    assert "Resumen de artículos" in internal_email.body
    assert "SKU-INQ-EMAIL-TRANS" in internal_email.body

    assert customer_email.to == ["phase8@example.com"]
    assert inquiry.reference_code in customer_email.subject
    assert customer_email.reply_to == ["atencion@example.com"]
    assert "confirma la recepción de tu solicitud" in customer_email.body


@pytest.mark.django_db(transaction=True)
def test_sends_on_create_when_inquiry_starts_in_submitted_state(email_settings) -> None:
    inquiry = Inquiry.objects.create(
        guest_name="Invitado",
        guest_email="guest-phase8@example.com",
        status=Inquiry.Status.SUBMITTED,
        language=Inquiry.Language.SPANISH,
    )

    assert len(mail.outbox) == 2
    assert inquiry.reference_code in mail.outbox[0].subject
    assert inquiry.reference_code in mail.outbox[1].subject


@pytest.mark.django_db(transaction=True)
def test_does_not_send_for_non_submitted_states(django_user_model, email_settings) -> None:
    user = django_user_model.objects.create_user(
        username="phase8draft",
        email="phase8draft@example.com",
        password="pass1234",
    )
    inquiry = Inquiry.objects.create(user=user, status=Inquiry.Status.DRAFT)

    assert len(mail.outbox) == 0

    inquiry.status = Inquiry.Status.CLOSED
    inquiry.save(update_fields=["status"])

    assert len(mail.outbox) == 0


@pytest.mark.django_db(transaction=True)
def test_repeated_saves_in_submitted_state_do_not_resend(django_user_model, email_settings) -> None:
    user = django_user_model.objects.create_user(
        username="phase8repeat",
        email="phase8repeat@example.com",
        password="pass1234",
    )
    inquiry = Inquiry.objects.create(user=user, status=Inquiry.Status.DRAFT)
    InquiryItem.objects.create(
        inquiry=inquiry,
        product=make_product("SKU-INQ-EMAIL-REPEAT"),
        requested_quantity=1,
    )

    mail.outbox.clear()
    inquiry.status = Inquiry.Status.SUBMITTED
    inquiry.save(update_fields=["status"])
    assert len(mail.outbox) == 2

    inquiry.notes_from_customer = "Actualizacion de nota"
    inquiry.save(update_fields=["notes_from_customer"])
    inquiry.status = Inquiry.Status.SUBMITTED
    inquiry.save(update_fields=["status"])

    assert len(mail.outbox) == 2


@pytest.mark.django_db(transaction=True)
def test_english_templates_render_when_inquiry_language_is_en(
    django_user_model,
    email_settings,
) -> None:
    user = django_user_model.objects.create_user(
        username="phase8en",
        email="phase8en@example.com",
        password="pass1234",
    )
    inquiry = Inquiry.objects.create(
        user=user,
        status=Inquiry.Status.DRAFT,
        language=Inquiry.Language.ENGLISH,
    )
    InquiryItem.objects.create(
        inquiry=inquiry,
        product=make_product("SKU-INQ-EMAIL-EN"),
        requested_quantity=3,
    )

    mail.outbox.clear()
    inquiry.status = Inquiry.Status.SUBMITTED
    inquiry.save(update_fields=["status"])

    assert len(mail.outbox) == 2
    assert "New inquiry received:" in mail.outbox[0].subject
    assert "A new spare parts inquiry has been submitted." in mail.outbox[0].body
    assert "We have received your inquiry" in mail.outbox[1].subject
    assert "This email confirms we received your inquiry" in mail.outbox[1].body


@pytest.mark.django_db(transaction=True)
def test_spanish_templates_render_when_inquiry_language_is_es(
    django_user_model,
    email_settings,
) -> None:
    user = django_user_model.objects.create_user(
        username="phase8es",
        email="phase8es@example.com",
        password="pass1234",
    )
    inquiry = Inquiry.objects.create(
        user=user,
        status=Inquiry.Status.DRAFT,
        language=Inquiry.Language.SPANISH,
    )
    InquiryItem.objects.create(
        inquiry=inquiry,
        product=make_product("SKU-INQ-EMAIL-ES"),
        requested_quantity=1,
    )

    mail.outbox.clear()
    inquiry.status = Inquiry.Status.SUBMITTED
    inquiry.save(update_fields=["status"])

    assert len(mail.outbox) == 2
    assert "Nueva solicitud recibida:" in mail.outbox[0].subject
    assert "Se ha enviado una nueva solicitud de recambios." in mail.outbox[0].body
    assert "Hemos recibido tu solicitud" in mail.outbox[1].subject
