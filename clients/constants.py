from django.db import models
from django.utils.translation import gettext_lazy as _


class DocumentType(models.TextChoices):
    PHOTOS = 'photos', _('Фотографии')
    PAYMENT_CONFIRMATION = 'payment_confirmation', _('Подтверждение оплаты')
    PASSPORT = 'passport', _('Паспорт')
    ENROLLMENT_CERTIFICATE = 'enrollment_certificate', _('Справка о зачислении')
    TUITION_FEE_PROOF = 'tuition_fee_proof', _('Справка об оплате обучения')
    HEALTH_INSURANCE = 'health_insurance', _('Медицинская страховка')
    ADDRESS_PROOF = 'address_proof', _('Подтверждение адреса')
    FINANCIAL_PROOF = 'financial_proof', _('Подтверждение финансов')
    ZALACZNIK_NR_1 = 'załącznik_nr_1', _('Załącznik nr 1')
    EMPLOYMENT_CONTRACT = 'employment_contract', _('Трудовой договор')
    PIT_PROOF = 'pit_proof', _('PIT-37 / Zaświadczenie o niezaleganiu')
    TAX_CLEARANCE_EMPLOYER = 'tax_clearance_employer', _('Справка об отсутствии налоговой задолженности работодателя')
    TAX_CLEARANCE_FOREIGNER = 'tax_clearance_foreigner', _('Справка об отсутствии налоговой задолженности иностранца')
    NO_DEPENDENTS_STATEMENT = 'no_dependents_statement', _('Заявление об отсутствии иждивенцев в Польше')


def doc_entry(doc_type: DocumentType) -> tuple[str, str]:
    return doc_type.value, doc_type.label


# Dokumenty dla CELU: STUDIA
STUDY_DOCS = [
    doc_entry(DocumentType.PHOTOS),
    doc_entry(DocumentType.PAYMENT_CONFIRMATION),
    doc_entry(DocumentType.PASSPORT),
    doc_entry(DocumentType.ENROLLMENT_CERTIFICATE),
    doc_entry(DocumentType.TUITION_FEE_PROOF),
    doc_entry(DocumentType.HEALTH_INSURANCE),
    doc_entry(DocumentType.ADDRESS_PROOF),
    doc_entry(DocumentType.FINANCIAL_PROOF),
]

# Dokumenty dla CELU: PRACA
WORK_DOCS = [
    doc_entry(DocumentType.PHOTOS),
    doc_entry(DocumentType.PASSPORT),
    doc_entry(DocumentType.PAYMENT_CONFIRMATION),
    doc_entry(DocumentType.ZALACZNIK_NR_1),
    doc_entry(DocumentType.TAX_CLEARANCE_EMPLOYER),
    doc_entry(DocumentType.TAX_CLEARANCE_FOREIGNER),
    doc_entry(DocumentType.NO_DEPENDENTS_STATEMENT),
    doc_entry(DocumentType.HEALTH_INSURANCE),
    doc_entry(DocumentType.EMPLOYMENT_CONTRACT),
    doc_entry(DocumentType.PIT_PROOF),
]

# Główna lista kontrolna.
# Django automatycznie użyje odpowiedniego tłumaczenia w zależności od wybranego języka.
DOCUMENT_CHECKLIST = {
    # Klucz to ('cel_złożenia', 'język_dokumentów_w_systemie')
    # Ale ponieważ wszystkie nazwy są teraz oznaczone do tłumaczenia,
    # możemy używać jednej listy dla wszystkich języków.
    ('study', 'pl'): STUDY_DOCS,
    ('study', 'en'): STUDY_DOCS,
    ('study', 'ru'): STUDY_DOCS,
    ('work', 'pl'): WORK_DOCS,
    ('work', 'en'): WORK_DOCS,
    ('work', 'ru'): WORK_DOCS,
}
