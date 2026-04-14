from datetime import timedelta

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.catalog.models import Brand, Category, Condition, Product
from apps.inquiries.models import Inquiry, InquiryItem
from apps.suppliers.models import Supplier

pytestmark = pytest.mark.django_db(transaction=True)


def make_public_product(*, sku: str) -> Product:
    supplier = Supplier.objects.create(
        name=f"Supplier {sku}",
        slug=f"supplier-{sku.lower()}",
        code=f"SUP-{sku}",
        is_active=True,
    )
    brand = Brand.objects.create(
        name=f"Brand {sku}",
        slug=f"brand-{sku.lower()}",
        brand_type=Brand.BrandType.PARTS,
        is_active=True,
    )
    category = Category.objects.create(name=f"Category {sku}", slug=f"category-{sku.lower()}")
    condition = Condition.objects.create(
        code=f"cond-{sku.lower()}",
        name=f"Cond {sku}",
        slug=f"cond-{sku.lower()}",
    )

    return Product.objects.create(
        supplier=supplier,
        supplier_product_code=f"{supplier.code}-{sku}",
        sku=sku,
        title=f"Product {sku}",
        short_description=f"Short {sku}",
        brand=brand,
        category=category,
        condition=condition,
        publication_status=Product.PublicationStatus.PUBLISHED,
        published_at=timezone.now() - timedelta(hours=1),
        is_active=True,
    )


@pytest.fixture
def email_settings(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "Recambios <noreply@example.com>"
    settings.SERVER_EMAIL = "Server <server@example.com>"
    settings.INQUIRY_INTERNAL_NOTIFICATION_EMAILS = ["internal-team@example.com"]
    settings.INQUIRY_CUSTOMER_REPLY_TO_EMAIL = "atencion@example.com"


@pytest.mark.usefixtures("email_settings")
def test_add_product_to_request_cart_and_keep_current_page(client) -> None:
    product = make_public_product(sku="SKU-P9-ADD")

    response = client.post(
        f"/es/solicitud/carrito/anadir/{product.id}/",
        data={"quantity": "2", "next": "/es/productos/"},
    )

    assert response.status_code == 302
    assert response.url == "/es/productos/"

    cart = client.session.get("request_cart_v1", {})
    assert cart[str(product.id)]["quantity"] == 2
    assert cart[str(product.id)]["note"] == ""


@pytest.mark.usefixtures("email_settings")
def test_update_and_remove_request_cart_item(client) -> None:
    product = make_public_product(sku="SKU-P9-UPD")
    session = client.session
    session["request_cart_v1"] = {str(product.id): {"quantity": 1, "note": ""}}
    session.save()

    response = client.post(
        f"/es/solicitud/carrito/actualizar/{product.id}/",
        data={"quantity": "3", "note": "Revisar conector"},
    )
    assert response.status_code == 302

    updated_cart = client.session.get("request_cart_v1", {})
    assert updated_cart[str(product.id)]["quantity"] == 3
    assert updated_cart[str(product.id)]["note"] == "Revisar conector"

    response = client.post(f"/es/solicitud/carrito/eliminar/{product.id}/")
    assert response.status_code == 302
    assert str(product.id) not in client.session.get("request_cart_v1", {})


@pytest.mark.usefixtures("email_settings")
@pytest.mark.parametrize("quantity", ["0", "-4", "abc"])
def test_add_with_invalid_quantity_does_not_create_cart_line(client, quantity: str) -> None:
    product = make_public_product(sku=f"SKU-P9-BADADD-{quantity.replace('-', 'neg')}")

    response = client.post(
        f"/es/solicitud/carrito/anadir/{product.id}/",
        data={"quantity": quantity, "next": "/es/productos/"},
        follow=True,
    )

    assert response.status_code == 200
    assert "La cantidad debe ser un número válido." in response.content.decode()
    assert client.session.get("request_cart_v1", {}) == {}


@pytest.mark.usefixtures("email_settings")
@pytest.mark.parametrize("quantity", ["-2", "abc"])
def test_update_with_invalid_quantity_keeps_previous_cart_line(client, quantity: str) -> None:
    product = make_public_product(sku=f"SKU-P9-BADUPD-{quantity.replace('-', 'neg')}")
    session = client.session
    session["request_cart_v1"] = {str(product.id): {"quantity": 2, "note": "Inicial"}}
    session.save()

    response = client.post(
        f"/es/solicitud/carrito/actualizar/{product.id}/",
        data={"quantity": quantity, "note": "Nota nueva"},
        follow=True,
    )

    assert response.status_code == 200
    assert "La cantidad debe ser un número válido." in response.content.decode()
    cart = client.session.get("request_cart_v1", {})
    assert cart[str(product.id)]["quantity"] == 2
    assert cart[str(product.id)]["note"] == "Inicial"


@pytest.mark.usefixtures("email_settings")
def test_cart_operations_do_not_create_inquiry(client) -> None:
    product = make_public_product(sku="SKU-P9-NOINQ")

    client.post(f"/es/solicitud/carrito/anadir/{product.id}/", data={"quantity": "1"})
    client.post(
        f"/es/solicitud/carrito/actualizar/{product.id}/",
        data={"quantity": "4", "note": "Lado derecho"},
    )

    assert Inquiry.objects.count() == 0
    assert len(mail.outbox) == 0


@pytest.mark.usefixtures("email_settings")
def test_guest_submission_creates_submitted_inquiry_and_items(client) -> None:
    first_product = make_public_product(sku="SKU-P9-GUEST-1")
    second_product = make_public_product(sku="SKU-P9-GUEST-2")

    client.post(
        f"/es/solicitud/carrito/anadir/{first_product.id}/",
        data={"quantity": "1"},
    )
    client.post(
        f"/es/solicitud/carrito/anadir/{second_product.id}/",
        data={"quantity": "2", "note": "Necesito versión reforzada"},
    )

    response = client.post(
        "/es/solicitud/enviar/",
        data={
            "contact_name": "Taller Central",
            "contact_email": "compras@tallercentral.example",
            "phone": "+34 600 100 200",
            "company_name": "Taller Central SL",
            "tax_id": "B12345678",
            "notes_from_customer": "Confirmar plazo para esta semana",
        },
    )

    assert response.status_code == 302
    assert "/es/solicitud/enviada/" in response.url

    inquiry = Inquiry.objects.get()
    assert inquiry.status == Inquiry.Status.SUBMITTED
    assert inquiry.user_id is None
    assert inquiry.guest_name == "Taller Central"
    assert inquiry.guest_email == "compras@tallercentral.example"
    assert inquiry.notes_from_customer == "Confirmar plazo para esta semana"

    items = list(inquiry.items.select_related("product").order_by("product__sku"))
    assert len(items) == 2
    assert items[0].product.sku == "SKU-P9-GUEST-1"
    assert items[0].requested_quantity == 1
    assert items[1].product.sku == "SKU-P9-GUEST-2"
    assert items[1].requested_quantity == 2
    assert items[1].customer_note == "Necesito versión reforzada"

    assert len(mail.outbox) == 2
    assert "request_cart_v1" not in client.session


@pytest.mark.usefixtures("email_settings")
def test_registered_user_submission_uses_account_email_fallback(client, django_user_model) -> None:
    user = django_user_model.objects.create_user(
        username="phase9user",
        email="phase9.user@example.com",
        password="pass1234",
    )
    client.force_login(user)

    product = make_public_product(sku="SKU-P9-AUTH")
    client.post(f"/es/solicitud/carrito/anadir/{product.id}/", data={"quantity": "3"})

    response = client.post(
        "/es/solicitud/enviar/",
        data={
            "contact_name": "Comprador Taller",
            "contact_email": "",
            "phone": "+34 699 000 111",
            "company_name": "Autorecambios Norte",
            "tax_id": "B87654321",
            "notes_from_customer": "Necesito factura",
        },
    )

    assert response.status_code == 302

    inquiry = Inquiry.objects.get()
    assert inquiry.user_id == user.id
    assert inquiry.guest_name == "Comprador Taller"
    assert inquiry.guest_email == "phase9.user@example.com"
    assert inquiry.status == Inquiry.Status.SUBMITTED

    assert len(mail.outbox) == 2
    assert any("phase9.user@example.com" in message.to for message in mail.outbox)


@pytest.mark.usefixtures("email_settings")
def test_final_submit_is_only_event_creating_submitted_inquiry_and_emails(client) -> None:
    product = make_public_product(sku="SKU-P9-FINAL")
    client.post(f"/es/solicitud/carrito/anadir/{product.id}/", data={"quantity": "1"})

    assert Inquiry.objects.count() == 0
    assert len(mail.outbox) == 0

    response = client.post(
        "/es/solicitud/enviar/",
        data={
            "contact_name": "Cliente Final",
            "contact_email": "cliente.final@example.com",
            "phone": "",
            "company_name": "",
            "tax_id": "",
            "notes_from_customer": "",
        },
    )

    assert response.status_code == 302
    assert Inquiry.objects.count() == 1
    assert len(mail.outbox) == 2

    success_response = client.get(response.url)
    assert success_response.status_code == 200
    assert len(mail.outbox) == 2


@pytest.mark.usefixtures("email_settings")
def test_submitted_inquiry_does_not_resend_emails_on_later_saves(client) -> None:
    product = make_public_product(sku="SKU-P9-NODUPMAIL")
    client.post(f"/es/solicitud/carrito/anadir/{product.id}/", data={"quantity": "1"})

    response = client.post(
        "/es/solicitud/enviar/",
        data={
            "contact_name": "Cliente sin duplicados",
            "contact_email": "sin.duplicados@example.com",
            "phone": "",
            "company_name": "",
            "tax_id": "",
            "notes_from_customer": "",
        },
    )
    assert response.status_code == 302
    assert len(mail.outbox) == 2

    inquiry = Inquiry.objects.get()
    inquiry.internal_notes = "Nota interna posterior"
    inquiry.save(update_fields=["internal_notes"])
    inquiry.status = Inquiry.Status.SUBMITTED
    inquiry.save(update_fields=["status"])

    assert len(mail.outbox) == 2


@pytest.mark.usefixtures("email_settings")
def test_empty_cart_submit_routes_redirect_to_cart_and_do_not_create_inquiry(client) -> None:
    get_response = client.get("/es/solicitud/enviar/")
    assert get_response.status_code == 302
    assert get_response.url == "/es/solicitud/carrito/"

    post_response = client.post(
        "/es/solicitud/enviar/",
        data={
            "contact_name": "Cliente",
            "contact_email": "cliente@example.com",
        },
    )
    assert post_response.status_code == 302
    assert post_response.url == "/es/solicitud/carrito/"

    assert Inquiry.objects.count() == 0
    assert len(mail.outbox) == 0


@pytest.mark.usefixtures("email_settings")
def test_invalid_guest_form_does_not_create_inquiry_or_send_emails(client) -> None:
    product = make_public_product(sku="SKU-P9-INVALID")
    client.post(f"/es/solicitud/carrito/anadir/{product.id}/", data={"quantity": "1"})

    response = client.post(
        "/es/solicitud/enviar/",
        data={
            "contact_name": "",
            "contact_email": "",
            "notes_from_customer": "Falta contacto",
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "El nombre de contacto es obligatorio." in content
    assert "El email de contacto es obligatorio." in content
    assert Inquiry.objects.count() == 0
    assert len(mail.outbox) == 0


@pytest.mark.usefixtures("email_settings")
def test_submit_view_handles_stale_non_public_products_safely(client) -> None:
    product = make_public_product(sku="SKU-P9-STALE")
    client.post(f"/es/solicitud/carrito/anadir/{product.id}/", data={"quantity": "1"})

    product.is_active = False
    product.save(update_fields=["is_active"])

    response = client.get("/es/solicitud/enviar/")
    assert response.status_code == 302
    assert response.url == "/es/solicitud/carrito/"
    assert client.session.get("request_cart_v1", {}) == {}
    assert Inquiry.objects.count() == 0
    assert len(mail.outbox) == 0


@pytest.mark.usefixtures("email_settings")
def test_submit_rejects_tampered_cart_quantities(client) -> None:
    product = make_public_product(sku="SKU-P9-TAMPER")
    session = client.session
    session["request_cart_v1"] = {str(product.id): {"quantity": "not-an-int", "note": "x"}}
    session.save()

    response = client.get("/es/solicitud/enviar/")
    assert response.status_code == 302
    assert response.url == "/es/solicitud/carrito/"
    assert client.session.get("request_cart_v1", {}) == {}
    assert Inquiry.objects.count() == 0
    assert len(mail.outbox) == 0


@pytest.mark.usefixtures("email_settings")
def test_submit_is_atomic_when_item_creation_fails(client, monkeypatch) -> None:
    product = make_public_product(sku="SKU-P9-ATOMIC")
    client.post(f"/es/solicitud/carrito/anadir/{product.id}/", data={"quantity": "2"})

    def _raise_validation_error(*args, **kwargs):
        raise ValidationError("broken item payload")

    monkeypatch.setattr(InquiryItem.objects, "create", _raise_validation_error)

    response = client.post(
        "/es/solicitud/enviar/",
        data={
            "contact_name": "Cliente atómico",
            "contact_email": "atomico@example.com",
            "phone": "",
            "company_name": "",
            "tax_id": "",
            "notes_from_customer": "",
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "No se ha podido registrar tu solicitud." in content
    assert Inquiry.objects.count() == 0
    assert len(mail.outbox) == 0

    cart = client.session.get("request_cart_v1", {})
    assert cart[str(product.id)]["quantity"] == 2


@pytest.mark.usefixtures("email_settings")
def test_invalid_form_renders_accessible_error_bindings(client) -> None:
    product = make_public_product(sku="SKU-P9-A11Y")
    client.post(f"/es/solicitud/carrito/anadir/{product.id}/", data={"quantity": "1"})

    response = client.post(
        "/es/solicitud/enviar/",
        data={
            "contact_name": "",
            "contact_email": "",
            "phone": "",
            "company_name": "",
            "tax_id": "",
            "notes_from_customer": "",
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert 'aria-describedby="contact_name-errors"' in content
    assert 'aria-describedby="contact_email-errors"' in content
    assert 'id="contact_name-errors"' in content
    assert 'id="contact_email-errors"' in content
    assert 'role="alert"' in content


@pytest.mark.usefixtures("email_settings")
def test_public_request_routes_work_in_es_and_en(client) -> None:
    product = make_public_product(sku="SKU-P9-ROUTES")

    es_add = client.post(
        f"/es/solicitud/carrito/anadir/{product.id}/",
        data={"quantity": "1", "next": "/es/solicitud/carrito/"},
    )
    assert es_add.status_code == 302
    assert client.get("/es/solicitud/carrito/").status_code == 200
    assert client.get("/es/solicitud/enviar/").status_code == 200

    session = client.session
    session.flush()

    en_add = client.post(
        f"/en/request/cart/add/{product.id}/",
        data={"quantity": "1", "next": "/en/request/cart/"},
    )
    assert en_add.status_code == 302
    assert client.get("/en/request/cart/").status_code == 200
    assert client.get("/en/request/submit/").status_code == 200
