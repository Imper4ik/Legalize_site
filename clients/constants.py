# clients/constants.py

from django.utils.translation import gettext_lazy as _


# Dokumenty dla CELU: STUDIA
STUDY_DOCS = [
    ('photos', _('Фотографии')),
    ('payment_confirmation', _('Подтверждение оплаты')),
    ('passport', _('Паспорт')),
    ('enrollment_certificate', _('Справка о зачислении')),
    ('tuition_fee_proof', _('Справка об оплате обучения')),
    ('health_insurance', _('Медицинская страховка')),
    ('address_proof', _('Подтверждение адреса')),
    ('financial_proof', _('Подтверждение финансов')),
]

# Dokumenty dla CELU: PRACA
WORK_DOCS = [
    ('photos', _('Фотографии')),
    ('passport', _('Паспорт')),
    ('payment_confirmation', _('Подтверждение оплаты')),
    ('załącznik_nr_1', _('Załącznik nr 1')),
    ('starosta_info', _('Informacja starosty')),
    ('health_insurance', _('Медицинская страховка')),
    ('employment_contract', _('Трудовой договор')),
    ('pit_proof', _('PIT-37 / Zaświadczenie o niezaleganiu')),
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