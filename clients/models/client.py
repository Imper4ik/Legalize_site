import hashlib
from django.db import connection, models
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext, gettext_lazy as _
from django.conf import settings
from fernet_fields import EncryptedTextField

class Client(models.Model):
    # --- Списки для выбора ---
    APPLICATION_PURPOSE_CHOICES = [
        ('study', _('Учёба')),
        ('work', _('Работа')),
        ('family', _('Воссоединение семьи')),
    ]
    LANGUAGE_CHOICES = getattr(settings, "LANGUAGES", [
        ('pl', _('Польский')),
        ('en', _('Английский')),
        ('ru', _('Русский')),
    ])
    STATUS_CHOICES = [
        ('new', _('Новый')),
        ('pending', _('В ожидании')),
        ('approved', _('Одобрен')),
        ('rejected', _('Отклонён')),
    ]

    # --- Поля модели ---
    first_name = models.CharField(max_length=100, verbose_name=_("Имя"))
    last_name = models.CharField(max_length=100, verbose_name=_("Фамилия"))
    citizenship = models.CharField(max_length=100, verbose_name=_("Гражданство"))
    birth_date = models.DateField(null=True, blank=True, verbose_name=_("Дата рождения"))
    phone = models.CharField(max_length=20, verbose_name=_("Телефон"))
    email = models.EmailField(verbose_name="Email", unique=True)
    passport_num = EncryptedTextField(null=True, blank=True, verbose_name=_("Номер паспорта"))
    case_number = EncryptedTextField(blank=True, null=True, verbose_name=_("Номер дела"))
    case_number_hash = models.CharField(max_length=64, blank=True, null=True, db_index=True)
    application_purpose = models.CharField(
        max_length=64,
        default='study',
        verbose_name=_("Цель подачи"),
    )
    basis_of_stay = models.CharField(
        max_length=100, blank=True, null=True, verbose_name=_("Основание пребывания (виза, TRC и т.д.)")
    )
    language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES, default='pl', verbose_name=_("Язык документов"))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new', verbose_name=_("Статус"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))
    legal_basis_end_date = models.DateField(null=True, blank=True, verbose_name=_("Дата окончания основания"))
    submission_date = models.DateField(null=True, blank=True, verbose_name=_("Дата подачи (Złożone)"))
    employer_phone = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("Телефон работодателя"))
    fingerprints_date = models.DateField(null=True, blank=True, verbose_name=_("Дата сдачи отпечатков"))
    fingerprints_time = models.TimeField(null=True, blank=True, verbose_name=_("Время сдачи отпечатков"))
    fingerprints_location = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Место сдачи отпечатков"))
    decision_date = models.DateField(null=True, blank=True, verbose_name=_("Дата официальной децизии"))
    notes = models.TextField(blank=True, null=True, verbose_name=_("Uwagi / Заметки"))
    has_checklist_access = models.BooleanField(default=False, verbose_name=_("Доступ к чеклисту предоставлен"))

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='client_profile',
                                null=True, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @staticmethod
    def normalize_case_number(case_number: str) -> str:
        return case_number.strip().upper().replace(" ", "")

    @classmethod
    def hash_case_number(cls, case_number: str) -> str:
        normalized = cls.normalize_case_number(case_number)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def save(self, *args, **kwargs):
        if self.case_number:
            self.case_number_hash = self.hash_case_number(self.case_number)
        else:
            self.case_number_hash = None

        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "case_number" in update_fields:
            update_fields = set(update_fields)
            update_fields.add("case_number_hash")
            kwargs["update_fields"] = list(update_fields)

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('clients:client_detail', kwargs={'pk': self.id})

    def get_application_purpose_display(self):
        from submissions.models import Submission
        from .document import _submission_has_localized_fields

        if self.application_purpose:
            if _submission_has_localized_fields():
                submission = Submission.objects.filter(
                    slug=self.application_purpose
                ).first()
                if submission:
                    return submission.localized_name
            else:
                submission_name = Submission.objects.filter(
                    slug=self.application_purpose
                ).values_list("name", flat=True).first()
                if submission_name:
                    return submission_name

        return dict(self.APPLICATION_PURPOSE_CHOICES).get(
            self.application_purpose, self.application_purpose or ''
        )

    def get_document_checklist(self):
        from .document import DocumentRequirement
        current_language = translation.get_language() or self.language
        required_docs = DocumentRequirement.required_for(self.application_purpose, current_language)
        if not required_docs:
            return []

        uploaded_docs = self.documents.all().order_by('-uploaded_at')

        docs_map = {}
        for doc in uploaded_docs:
            if doc.document_type not in docs_map:
                docs_map[doc.document_type] = []
            docs_map[doc.document_type].append(doc)

        status_list = []
        for code, name in required_docs:
            documents = docs_map.get(code, [])
            status_list.append({
                'code': code,
                'name': str(name),
                'is_uploaded': bool(documents),
                'documents': documents
            })
        return status_list

    def get_document_name_by_code(self, doc_code):
        from .document import DocumentRequirement, get_available_document_types, resolve_document_label
        current_language = translation.get_language() or self.language
        catalog = DocumentRequirement.catalog_for(
            self.application_purpose,
            current_language,
            include_optional=True,
            include_fallback=True,
        )
        for item in catalog:
            if item["code"] == doc_code:
                return item["label"]
        if doc_code in get_available_document_types(self.application_purpose):
            return resolve_document_label(doc_code, language=current_language)
        return doc_code.replace('_', ' ').capitalize()
