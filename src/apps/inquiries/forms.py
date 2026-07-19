from __future__ import annotations

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField

from .models import InquiryOfferPayment, InquiryOfferPaymentDetails


class PublicInquirySubmissionForm(forms.Form):
    destination_country = CountryField(blank_label=_("Seleccione un país")).formfield(
        label=_("País de destino"),
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    destination_region = forms.CharField(
        label=_("Provincia / región / estado"),
        max_length=120,
        widget=forms.TextInput(attrs={"class": "form-input", "autocomplete": "address-level1"}),
    )
    destination_city = forms.CharField(
        label=_("Ciudad / localidad de destino"),
        max_length=120,
        widget=forms.TextInput(attrs={"class": "form-input", "autocomplete": "address-level2"}),
    )
    destination_postal_code = forms.CharField(
        label=_("Código postal de destino"),
        max_length=32,
        widget=forms.TextInput(attrs={"class": "form-input", "autocomplete": "postal-code"}),
    )
    contact_name = forms.CharField(
        label=_("Nombre de contacto"),
        max_length=150,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
            }
        ),
    )
    contact_email = forms.EmailField(
        label=_("Email de contacto"),
        required=False,
        widget=forms.EmailInput(
            attrs={
                "class": "form-input",
                "autocomplete": "email",
            }
        ),
    )
    phone = forms.CharField(
        label=_("Teléfono"),
        max_length=50,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "autocomplete": "tel",
            }
        ),
    )
    company_name = forms.CharField(
        label=_("Empresa"),
        max_length=180,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "autocomplete": "organization",
            }
        ),
    )
    tax_id = forms.CharField(
        label=_("NIF/CIF"),
        max_length=64,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
            }
        ),
    )
    notes_from_customer = forms.CharField(
        label=_("Notas de la solicitud"),
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "class": "form-textarea",
            }
        ),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            error_id = f"{field_name}-errors"
            described_by = field.widget.attrs.get("aria-describedby", "").strip()
            field.widget.attrs["aria-describedby"] = " ".join(
                value for value in [described_by, error_id] if value
            )

        if not self.is_bound and self.user and self.user.is_authenticated:
            account_name = self.user.get_full_name().strip() or self.user.get_username()
            if account_name:
                self.initial.setdefault("contact_name", account_name)
            if self.user.email:
                self.initial.setdefault("contact_email", self.user.email)

    def clean_contact_name(self) -> str:
        return (self.cleaned_data.get("contact_name") or "").strip()

    def clean_contact_email(self) -> str:
        return (self.cleaned_data.get("contact_email") or "").strip().lower()

    def clean_phone(self) -> str:
        return (self.cleaned_data.get("phone") or "").strip()

    def clean_company_name(self) -> str:
        return (self.cleaned_data.get("company_name") or "").strip()

    def clean_tax_id(self) -> str:
        return (self.cleaned_data.get("tax_id") or "").strip()

    def clean_notes_from_customer(self) -> str:
        return (self.cleaned_data.get("notes_from_customer") or "").strip()

    def clean_destination_country(self) -> str:
        return str(self.cleaned_data.get("destination_country") or "").strip().upper()

    def clean_destination_region(self) -> str:
        return (self.cleaned_data.get("destination_region") or "").strip()

    def clean_destination_city(self) -> str:
        return (self.cleaned_data.get("destination_city") or "").strip()

    def clean_destination_postal_code(self) -> str:
        return (self.cleaned_data.get("destination_postal_code") or "").strip()

    def clean(self) -> dict:
        cleaned_data = super().clean()
        contact_name = cleaned_data.get("contact_name", "")
        contact_email = cleaned_data.get("contact_email", "")

        if self.user and self.user.is_authenticated:
            account_email = (self.user.email or "").strip().lower()
            if not contact_email and account_email:
                cleaned_data["contact_email"] = account_email

            if not contact_name:
                account_name = self.user.get_full_name().strip() or self.user.get_username()
                cleaned_data["contact_name"] = account_name

            if not cleaned_data.get("contact_email"):
                self.add_error(
                    "contact_email",
                    _("El email de contacto es obligatorio si su cuenta no tiene email."),
                )
            return cleaned_data

        if not contact_name:
            self.add_error("contact_name", _("El nombre de contacto es obligatorio."))
        if not contact_email:
            self.add_error("contact_email", _("El email de contacto es obligatorio."))

        return cleaned_data


class InquiryOfferPaymentDetailsForm(forms.ModelForm):
    class Meta:
        model = InquiryOfferPaymentDetails
        fields = (
            "shipping_recipient_name",
            "shipping_phone",
            "shipping_address_line_1",
            "shipping_address_line_2",
            "shipping_city",
            "shipping_region",
            "shipping_postal_code",
            "shipping_country",
            "billing_customer_type",
            "billing_same_as_shipping",
            "billing_name",
            "billing_tax_id",
            "billing_address_line_1",
            "billing_address_line_2",
            "billing_city",
            "billing_region",
            "billing_postal_code",
            "billing_country",
        )
        labels = {
            "shipping_recipient_name": _("Nombre completo del destinatario"),
            "shipping_phone": _("Teléfono del destinatario"),
            "shipping_address_line_1": _("Dirección, línea 1"),
            "shipping_address_line_2": _("Dirección, línea 2 (opcional)"),
            "shipping_city": _("Ciudad / localidad"),
            "shipping_region": _("Provincia / región / estado cotizado"),
            "shipping_postal_code": _("Código postal cotizado"),
            "shipping_country": _("País cotizado"),
            "billing_customer_type": _("Tipo de facturación"),
            "billing_same_as_shipping": _("La dirección de facturación coincide con la de envío"),
            "billing_name": _("Nombre de facturación / razón social"),
            "billing_tax_id": _("NIF/CIF/VAT"),
            "billing_address_line_1": _("Dirección de facturación, línea 1"),
            "billing_address_line_2": _("Dirección de facturación, línea 2 (opcional)"),
            "billing_city": _("Ciudad / localidad de facturación"),
            "billing_region": _("Provincia / región / estado de facturación"),
            "billing_postal_code": _("Código postal de facturación"),
            "billing_country": _("País de facturación"),
        }

    def __init__(self, *args, payment: InquiryOfferPayment, **kwargs):
        self.payment = payment
        super().__init__(*args, **kwargs)
        self.instance.payment = payment
        offer = payment.offer
        self.instance.shipping_country = offer.quoted_destination_country
        self.instance.shipping_city = offer.quoted_destination_city
        self.instance.shipping_region = offer.quoted_destination_region
        self.instance.shipping_postal_code = offer.quoted_destination_postal_code
        # ModelForm captures ``initial`` during ``super().__init__``. These locked
        # values are assigned afterwards from the commercial offer snapshot, so
        # explicitly refresh the form initial data as well as the model instance.
        self.initial.update(
            {
                "shipping_country": str(offer.quoted_destination_country or ""),
                "shipping_city": offer.quoted_destination_city,
                "shipping_region": offer.quoted_destination_region,
                "shipping_postal_code": offer.quoted_destination_postal_code,
            }
        )
        text_fields = set(self.fields) - {
            "billing_customer_type",
            "billing_same_as_shipping",
            "billing_country",
            "shipping_country",
        }
        for name, field in self.fields.items():
            if name in text_fields:
                field.widget.attrs.setdefault("class", "form-input")
            elif name in {"billing_customer_type", "billing_country", "shipping_country"}:
                field.widget.attrs.setdefault("class", "form-select")
            field.widget.attrs["aria-describedby"] = f"{name}-errors"
        for name in (
            "billing_address_line_1",
            "billing_city",
            "billing_region",
            "billing_postal_code",
            "billing_country",
        ):
            self.fields[name].required = False
        for name in (
            "shipping_city",
            "shipping_region",
            "shipping_postal_code",
            "shipping_country",
        ):
            self.fields[name].disabled = True
        inquiry = payment.offer.inquiry
        if not self.is_bound and not self.instance.pk:
            self.initial.update(
                {
                    "shipping_recipient_name": inquiry.guest_name or inquiry.requester_display,
                    "shipping_phone": inquiry.guest_phone,
                    "billing_customer_type": (
                        InquiryOfferPaymentDetails.BillingCustomerType.COMPANY
                        if inquiry.company_name
                        else InquiryOfferPaymentDetails.BillingCustomerType.PRIVATE
                    ),
                    "billing_name": (
                        inquiry.company_name or inquiry.guest_name or inquiry.requester_display
                    ),
                    "billing_tax_id": inquiry.tax_id,
                }
            )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("billing_same_as_shipping"):
            shipping_address_line_1 = cleaned.get("shipping_address_line_1")
            billing_address_line_1 = cleaned.get("billing_address_line_1")
            if billing_address_line_1 != shipping_address_line_1:
                self.add_error(
                    "billing_address_line_1",
                    _(
                        "La dirección de facturación debe coincidir con la dirección "
                        "de envío mientras esta opción esté seleccionada."
                    ),
                )
            cleaned.update(
                {
                    "billing_address_line_1": shipping_address_line_1,
                    "billing_address_line_2": cleaned.get("shipping_address_line_2"),
                    "billing_city": cleaned.get("shipping_city"),
                    "billing_region": cleaned.get("shipping_region"),
                    "billing_postal_code": cleaned.get("shipping_postal_code"),
                    "billing_country": cleaned.get("shipping_country"),
                }
            )
        else:
            for name in (
                "billing_address_line_1",
                "billing_city",
                "billing_region",
                "billing_postal_code",
                "billing_country",
            ):
                if not cleaned.get(name):
                    self.add_error(
                        name,
                        _("Este campo es obligatorio para una dirección distinta."),
                    )
        return cleaned

    def save(self, commit=True):
        details = super().save(commit=False)
        offer = self.payment.offer
        details.payment = self.payment
        details.shipping_country = offer.quoted_destination_country
        details.shipping_city = offer.quoted_destination_city
        details.shipping_region = offer.quoted_destination_region
        details.shipping_postal_code = offer.quoted_destination_postal_code
        details.completed_at = timezone.now()
        if commit:
            details.save()
        return details
