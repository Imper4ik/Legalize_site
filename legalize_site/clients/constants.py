# legalize_site/legalize_site/clients/constants.py

# Ключ словаря - это (цель_подачи, язык)
# Значение - это список кортежей (код_документа, название_документа)

DOCUMENT_CHECKLIST = {
    # --- УЧЁБА (ПОЛЬСКИЙ) ---
    ('study', 'pl'): [
        ('photos', '4 zdjęcia biometryczne'),
        ('payment_confirmation', 'Potwierdzenie opłaty skarbowej (340 + 17 zł)'),
        ('passport', 'Paszport (wszystkie strony)'),
        ('enrollment_certificate', 'Zaświadczenie o przyjęciu lub kontynuacji studiów'),
        ('tuition_fee_proof', 'Dowód uiszczenia opłaty za naukę'),
        ('health_insurance', 'Ubezpieczenie zdrowotne (polisa na 30 000 EUR)'),
        ('address_proof', 'Dokumenty potwierdzające zamieszkanie (np. umowa najmu)'),
        ('financial_proof', 'Dokumenty potwierdzające posiadanie środków finansowych'),
    ],
    # --- УЧЁБА (АНГЛИЙСКИЙ) ---
    ('study', 'en'): [
        ('photos', '4 biometric photographs (3.5cm x 4.5cm)'),
        ('payment_confirmation', 'Confirmation of the application fee (340 + 17 PLN)'),
        ('passport', 'Passport (all pages)'),
        ('enrollment_certificate', 'Certificate of enrolment from the university'),
        ('tuition_fee_proof', 'Proof of tuition fee payment'),
        ('health_insurance', 'Health insurance policy (coverage of €30,000)'),
        ('address_proof', 'Documents confirming accommodation (e.g. rental contract)'),
        ('financial_proof', 'Documents confirming sufficient financial means'),
    ],

    # --- РАБОТА (ПОЛЬСКИЙ) ---
    ('work', 'pl'): [
        ('photos', '4 aktualne kolorowe fotografie'),
        ('passport', 'Paszport / karta pobytu'),
        ('payment_confirmation', 'Potwierdzenie opłaty za zezwolenie (440 zł) + 17zł'),
        ('załącznik_nr_1', 'Załącznik nr 1 do wniosku'),
        ('starosta_info', 'Informacja starosty'),
        ('health_insurance', 'Zgłoszenie do ubezpieczenia zdrowotnego (ZUS RCA)'),
        ('employment_contract', 'Umowa o pracę / umowa zlecenia'),
        ('pit_proof', 'Zaświadczenie o niezaleganiu w podatkach lub PIT-37'),
    ],
    # Добавьте другие комбинации по аналогии
}