from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from django import forms
from django.contrib.auth import get_user_model
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from clients.constants import INTERNAL_DOCS, DocumentType
from clients.models import (
    Client,
    Document,
    DocumentRequirement,
    FamilyGroup,
    get_fallback_document_checklist,
    resolve_document_label,
)
from clients.use_cases.document_requirements import (
    build_document_requirement_code,
    create_document_requirement_for_purpose,
    sync_document_checklist_for_purpose,
    update_document_requirement_record,
)
from clients.validators import FILE_INPUT_ACCEPT, validate_uploaded_document

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
User = get_user_model()


def _label_for_document_type(code: str) -> str:
    try:
        return str(DocumentType(code).label)
    except ValueError:
        return code.replace('_', ' ').capitalize()


class DocumentUploadForm(forms.ModelForm):
    def __init__(self, *args: Any, doc_type: str | None = None, client: Client | None = None, case: Any = None, **kwargs: Any) -> None:
        self.doc_type = doc_type
        self.client = client
        super().__init__(*args, **kwargs)
        # Bind the client (and case when known) onto the instance so the model's
        # case-first validation can resolve a case for single-case clients and
        # reject ambiguous multi-case uploads (spec section 5).
        if client is not None:
            self.instance.client = client
        if case is not None:
            self.instance.case = case
        self.fields["zus_period_month"].help_text = _(
            "Для ZUS RCA укажите месяц отчёта. Если загружаете страховой полис, добавьте его как отдельный документ «Polisa ubezpieczeniowa / Health insurance»."
        )

    def clean_file(self) -> Any:
        return validate_uploaded_document(self.cleaned_data.get("file"))

    def clean_zus_period_month(self) -> Any:
        value = self.cleaned_data.get("zus_period_month")
        if self.doc_type != DocumentType.ZUS_RCA_OR_INSURANCE.value:
            return None
        if not value:
            return None
        normalized = value.replace(day=1)
        if self.client is not None:
            duplicate_query = Document.objects.filter(
                client=self.client,
                document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
                zus_period_month=normalized,
                archived_at__isnull=True,
            )
            case = self.client.cases.order_by("opened_at", "id").first()
            if case is not None:
                duplicate_query = duplicate_query.filter(case=case)
            if duplicate_query.exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError(_("ZUS RCA for this month is already uploaded for this case."))
        return normalized

    class Meta:
        model = Document
        fields = ['file', 'expiry_date', 'zus_period_month']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'form-control', 'accept': FILE_INPUT_ACCEPT}),
            'expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'zus_period_month': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }


class ClientDocumentRequirementForm(forms.ModelForm):
    class Meta:
        from clients.models import ClientDocumentRequirement
        model = ClientDocumentRequirement
        fields = ["name", "description", "is_required", "due_date"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_required": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "due_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }

    def __init__(self, *args: Any, client: Client | None = None, case: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if client is not None:
            self.instance.client = client
        if case is not None:
            self.instance.case = case

    def clean_name(self) -> str:
        return str(self.cleaned_data["name"]).strip()


class FamilyGroupFinanceForm(forms.ModelForm):
    class Meta:
        model = FamilyGroup
        fields = [
            "sponsor_monthly_income",
            "monthly_support_per_person",
            "monthly_housing_cost",
            "meldunek_free_housing",
        ]
        widgets = {
            "sponsor_monthly_income": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0"}
            ),
            "monthly_support_per_person": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0"}
            ),
            "monthly_housing_cost": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0"}
            ),
            "meldunek_free_housing": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class DocumentRequirementEditForm(forms.ModelForm):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not self.instance.custom_name:
            self.initial.setdefault('custom_name', _label_for_document_type(self.instance.document_type))
        self.fields['position'].required = False

    class Meta:
        model = DocumentRequirement
        fields = ['custom_name', 'custom_name_pl', 'custom_name_en', 'custom_name_ru', 'position', 'is_required']
        widgets = {
            'custom_name': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'custom_name_pl': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'custom_name_en': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'custom_name_ru': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'position': forms.NumberInput(attrs={'class': 'form-control form-control-sm'}),
            'is_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def save(self, commit: bool = True) -> DocumentRequirement:
        instance = self.instance
        result = update_document_requirement_record(
            requirement=instance,
            cleaned_data=self.cleaned_data,
        )
        if result.requirement is None:
            raise RuntimeError("Document requirement update did not return a record")
        return result.requirement


class DocumentRequirementAddForm(forms.Form):
    name = forms.CharField(
        label=_('Название документа'),
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    def __init__(self, *args: Any, purpose: str | None = None, **kwargs: Any) -> None:
        self.purpose = purpose
        super().__init__(*args, **kwargs)
        self.fields['name'].widget.attrs.setdefault('autofocus', 'autofocus')

    def clean_name(self) -> str:
        name = (self.cleaned_data.get('name') or '').strip()
        self.cleaned_data['slug'] = build_document_requirement_code(
            purpose=self.purpose or "",
            name=name,
        )
        return name

    def save(self) -> DocumentRequirement:
        if not hasattr(self, 'cleaned_data'):
            raise RuntimeError("Call is_valid() before save()")
        result = create_document_requirement_for_purpose(
            purpose=self.purpose or "",
            name=self.cleaned_data['name'],
            slug=self.cleaned_data['slug'],
        )
        if result.requirement is None:
            raise RuntimeError("Document requirement creation did not return a record")
        return result.requirement


class DocumentChecklistForm(forms.Form):
    required_documents = forms.MultipleChoiceField(
        label=_('Необходимые документы'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        choices=DocumentType.choices,
    )

    def __init__(self, *args: Any, purpose: str | None = None, **kwargs: Any) -> None:
        self.purpose = purpose
        super().__init__(*args, **kwargs)
        existing_requirements = list(
            DocumentRequirement.objects.filter(application_purpose=self.purpose)
            .order_by('position', 'id')
        )

        choices: list[tuple[str, str]] = []

        if existing_requirements:
            for requirement in existing_requirements:
                if requirement.document_type in INTERNAL_DOCS:
                    continue
                label = resolve_document_label(
                    requirement.document_type,
                    requirement.custom_name,
                    requirement.custom_name_pl,
                    requirement.custom_name_en,
                    requirement.custom_name_ru,
                    translation.get_language(),
                )
                choices.append((requirement.document_type, label))
        else:
            fallback_docs = get_fallback_document_checklist(self.purpose or "")
            if fallback_docs:
                choices.extend([(str(doc[0]), str(doc[1])) for doc in fallback_docs if doc[0] not in INTERNAL_DOCS])
            else:
                choices.extend([(str(c[0]), str(c[1])) for c in DocumentType.choices if c[0] not in INTERNAL_DOCS])

        cast(forms.MultipleChoiceField, self.fields['required_documents']).choices = choices

        if 'required_documents' not in self.initial:
            self.initial['required_documents'] = self._initial_documents()

    @staticmethod
    def _label_for_code(code: str) -> str:
        return _label_for_document_type(code)

    def _initial_documents(self) -> list[str]:
        existing = (
            DocumentRequirement.objects.filter(application_purpose=self.purpose, is_required=True)
            .exclude(document_type__in=INTERNAL_DOCS)
            .order_by('position', 'id')
            .values_list('document_type', flat=True)
        )
        if existing:
            return list(existing)

        if DocumentRequirement.objects.filter(application_purpose=self.purpose).exists():
            return []

        fallback_docs = get_fallback_document_checklist(self.purpose or "")
        if fallback_docs:
            return [str(code) for code, _ in fallback_docs if code not in INTERNAL_DOCS]
        return []

    def save(self, *, doc_order: list[str] | None = None) -> int:
        selected_codes = list(self.cleaned_data.get('required_documents', []))
        if doc_order:
            # Re-order selected codes according to the D&D ordering.
            ordered = [code for code in doc_order if code in selected_codes]
            remaining = [code for code in selected_codes if code not in ordered]
            selected_codes = ordered + remaining
        result = sync_document_checklist_for_purpose(
            purpose=self.purpose or "",
            selected_codes=selected_codes,
        )
        return result.updated_count
