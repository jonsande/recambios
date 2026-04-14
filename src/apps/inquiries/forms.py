from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _


class PublicInquirySubmissionForm(forms.Form):
    contact_name = forms.CharField(
        label=_("Nombre de contacto"),
        max_length=150,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": (
                    "mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm "
                    "text-slate-900 focus:outline-none focus-visible:ring-2 "
                    "focus-visible:ring-slate-700 focus-visible:ring-offset-2"
                ),
            }
        ),
    )
    contact_email = forms.EmailField(
        label=_("Email de contacto"),
        required=False,
        widget=forms.EmailInput(
            attrs={
                "class": (
                    "mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm "
                    "text-slate-900 focus:outline-none focus-visible:ring-2 "
                    "focus-visible:ring-slate-700 focus-visible:ring-offset-2"
                ),
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
                "class": (
                    "mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm "
                    "text-slate-900 focus:outline-none focus-visible:ring-2 "
                    "focus-visible:ring-slate-700 focus-visible:ring-offset-2"
                ),
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
                "class": (
                    "mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm "
                    "text-slate-900 focus:outline-none focus-visible:ring-2 "
                    "focus-visible:ring-slate-700 focus-visible:ring-offset-2"
                ),
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
                "class": (
                    "mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm "
                    "text-slate-900 focus:outline-none focus-visible:ring-2 "
                    "focus-visible:ring-slate-700 focus-visible:ring-offset-2"
                ),
            }
        ),
    )
    notes_from_customer = forms.CharField(
        label=_("Notas de la solicitud"),
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "class": (
                    "mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm "
                    "text-slate-900 focus:outline-none focus-visible:ring-2 "
                    "focus-visible:ring-slate-700 focus-visible:ring-offset-2"
                ),
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
                    _("El email de contacto es obligatorio si tu cuenta no tiene email."),
                )
            return cleaned_data

        if not contact_name:
            self.add_error("contact_name", _("El nombre de contacto es obligatorio."))
        if not contact_email:
            self.add_error("contact_email", _("El email de contacto es obligatorio."))

        return cleaned_data
