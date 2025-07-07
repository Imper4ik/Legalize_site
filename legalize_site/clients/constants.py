# clients/constants.py

# Ключ словаря - это (цель_подачи, язык)
# Значение - это список кортежей (код_документа, название_документа)

DOCUMENT_CHECKLIST = {
    # --- УЧЁБА ---
    ('study', 'pl'): [
        ('passport', 'Паспорт'),
        ('certificate_enrolment', 'Справка о зачислении'),
        ('certificate_fees', 'Справка об оплате обучения'),
        ('health_insurance', 'Медицинская страховка'),
        ('rental_contract', 'Договор аренды'),
        ('financial_means', 'Документ о средствах на счету'),
    ],
    ('study', 'en'): [
        ('passport', 'Passport'),
        ('certificate_enrolment', 'Certificate of Enrolment'),
        ('certificate_fees', 'Proof of Tuition Fee Payment'),
        ('health_insurance', 'Health Insurance'),
        ('rental_contract', 'Rental Agreement'),
        ('financial_means', 'Proof of Financial Means'),
    ],

    # --- РАБОТА ---
    ('work', 'pl'): [
        ('passport', 'Паспорт'),
        ('work_permit', 'Разрешение на работу (Залончник №1)'),
        ('employment_contract', 'Трудовой договор'),
        ('health_insurance', 'Медицинская страховка (ZUS)'),
        ('rental_contract', 'Договор аренды'),
    ],
    # Добавьте другие комбинации по аналогии
}