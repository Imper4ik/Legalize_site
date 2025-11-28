from django.db import models
from django.utils.translation import gettext_lazy as _


class DocumentType(models.TextChoices):
    PHOTOS = 'photos', _('4 zdjęcia (45x35 mm)')
    PAYMENT_CONFIRMATION = 'payment_confirmation', _('Potwierdzenie opłaty')
    STUDY_APPLICATION_FEE = 'study_application_fee', _('Opłata 340 zł + 17 zł pełnomocnictwo')
    WORK_PERMIT_FEE = 'work_permit_fee', _('Opłata 440 zł + 17 zł pełномocnictwo')
    PASSPORT = 'passport', _('Paszport')
    RESIDENCE_CARD = 'residence_card', _('Karta pobytu')
    ENROLLMENT_CERTIFICATE = 'enrollment_certificate', _('Zaświadczenie z uczelni o przyjęciu lub kontynuacji studiów')
    TUITION_FEE_STATEMENT = 'tuition_fee_statement', _('Zaświadczenie z uczelni o wysokości opłat za naukę')
    TUITION_FEE_PROOF = 'tuition_fee_proof', _('Dowód uiszczenia opłaty za naukę (czesne)')
    GRADES = 'grades', _('Oceny / świadectwa')
    HEALTH_INSURANCE = 'health_insurance', _('Polisa ubezpieczeniowa 30 000 EUR')
    ADDRESS_PROOF = 'address_proof', _('Dokumenty potwierdzające koszty zamieszkania (np. umowa najmu, rachunki)')
    FINANCIAL_PROOF = 'financial_proof', _('Środki finansowe na utrzymanie w Polsce')
    ZALACZNIK_NR_1 = 'załącznik_nr_1', _('Załącznik nr 1')
    EMPLOYMENT_CONTRACT = 'employment_contract', _('Oryginały umów o pracę / zlecenia')
    WORK_PERMISSION = 'work_permission', _('Oświadczenie o powierzeniu pracy lub zezwolenie na pracę')
    PIT_PROOF = 'pit_proof', _('PIT-37 cudzoziemca z potwierdzeniem złożenia')
    TAX_CLEARANCE_EMPLOYER = 'tax_clearance_employer', _('Zaświadczenie ZUS dot. braku zaległości pracodawcy')
    TAX_CLEARANCE_FOREIGNER = 'tax_clearance_foreigner', _('Zaświadczenie o niezaleganiu opłacania składek cudzoziemca')
    NO_DEPENDENTS_STATEMENT = 'no_dependents_statement', _('Oświadczenie o braku osób na utrzymaniu w Polsce')
    ZUS_RCA_OR_INSURANCE = 'zus_rca_or_insurance', _('ZUS RCA lub polisa ubezpieczeniowa')
    ZUS_CONTRIBUTION_HISTORY = 'zus_contribution_history', _('Zaświadczenie z ZUS o przebieгу ubezpieczenia cudzoziemca')
    EMPLOYER_TAX_RETURN = 'employer_tax_return', _('CIT lub PIT pracodawcy')
    ZUS_EMPLOYEE_COUNT = 'zus_employee_count', _('Zaświadczenie z ZUS o liczbie zgłoszonych pracowników i składkach')
    STATEMENT_X = 'statement_x', _('Oświadczenie „x”')
    MAINTENANCE_STATEMENT = 'maintenance_statement', _('Oświadczenie o utrzymaniu')
    WEZWANIE = 'wezwanie', _('Wezwanie')


def doc_entry(doc_type: DocumentType) -> tuple[str, str]:
    return doc_type.value, doc_type.label


# Dokumenty dla CELU: STUDIA
STUDY_DOCS = [
    doc_entry(DocumentType.PHOTOS),
    doc_entry(DocumentType.STUDY_APPLICATION_FEE),
    doc_entry(DocumentType.PASSPORT),
    doc_entry(DocumentType.ENROLLMENT_CERTIFICATE),
    doc_entry(DocumentType.TUITION_FEE_STATEMENT),
    doc_entry(DocumentType.TUITION_FEE_PROOF),
    doc_entry(DocumentType.GRADES),
    doc_entry(DocumentType.HEALTH_INSURANCE),
    doc_entry(DocumentType.ADDRESS_PROOF),
    doc_entry(DocumentType.FINANCIAL_PROOF),
]

# Dokumenty dla CELU: PRACA
WORK_DOCS = [
    doc_entry(DocumentType.PHOTOS),
    doc_entry(DocumentType.PASSPORT),
    doc_entry(DocumentType.RESIDENCE_CARD),
    doc_entry(DocumentType.WORK_PERMIT_FEE),
    doc_entry(DocumentType.ZALACZNIK_NR_1),
    doc_entry(DocumentType.WORK_PERMISSION),
    doc_entry(DocumentType.EMPLOYMENT_CONTRACT),
    doc_entry(DocumentType.ZUS_RCA_OR_INSURANCE),
    doc_entry(DocumentType.PIT_PROOF),
    doc_entry(DocumentType.ZUS_CONTRIBUTION_HISTORY),
    doc_entry(DocumentType.TAX_CLEARANCE_EMPLOYER),
    doc_entry(DocumentType.EMPLOYER_TAX_RETURN),
    doc_entry(DocumentType.ZUS_EMPLOYEE_COUNT),
    doc_entry(DocumentType.NO_DEPENDENTS_STATEMENT),
    doc_entry(DocumentType.MAINTENANCE_STATEMENT),
    doc_entry(DocumentType.STATEMENT_X),
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
