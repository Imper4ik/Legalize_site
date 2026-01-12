# Generated migration - populate all document types with translations
from django.db import migrations


def populate_document_translations(apps, schema_editor):
    """Populate custom_name_pl/ru/en for all DocumentRequirements."""
    DocumentRequirement = apps.get_model('clients', 'DocumentRequirement')
    
    # Complete translations for all document types
    translations = {
        # Standard documents
        'photos': {
            'pl': '4 zdjęcia (45x35 mm)',
            'ru': '4 фотографии (45x35 мм)',
            'en': '4 photos (45x35 mm)'
        },
        'passport': {
            'pl': 'Paszport',
            'ru': 'Паспорт',
            'en': 'Passport'
        },
        'residence_card': {
            'pl': 'Karta pobytu',
            'ru': 'Карта пребывания',
            'en': 'Residence card'
        },
        'payment_confirmation': {
            'pl': 'Potwierdzenie opłaty',
            'ru': 'Подтверждение оплаты',
            'en': 'Payment confirmation'
        },
        'study_application_fee': {
            'pl': 'Opłata 340 zł + 17 zł pełnomocnictwo',
            'ru': 'Оплата 340 zł + 17 zł за доверенность',
            'en': 'Fee 340 PLN + 17 PLN power of attorney'
        },
        'work_permit_fee': {
            'pl': 'Opłata 440 zł + 17 zł pełnomocnictwo',
            'ru': 'Оплата 440 zł + 17 zł за доверенность',
            'en': 'Fee 440 PLN + 17 PLN power of attorney'
        },
        'enrollment_certificate': {
            'pl': 'Zaświadczenie z uczelni o przyjęciu lub kontynuacji studiów',
            'ru': 'Справка из вуза о приеме или продолжении учебы',
            'en': 'University certificate of admission or continuation of studies'
        },
        'tuition_fee_statement': {
            'pl': 'Zaświadczenie z uczelni o wysokości opłat za naukę',
            'ru': 'Справка из вуза о размере оплаты за обучение',
            'en': 'University certificate of tuition fees'
        },
        'tuition_fee_proof': {
            'pl': 'Dowód uiszczenia opłaty za naukę (czesne)',
            'ru': 'Подтверждение оплаты за обучение',
            'en': 'Proof of tuition payment'
        },
        'grades': {
            'pl': 'Oceny / świadectwa',
            'ru': 'Оценки / аттестаты',
            'en': 'Grades / certificates'
        },
        'health_insurance': {
            'pl': 'Polisa ubezpieczeniowa 30 000 EUR',
            'ru': 'Страховой полис (30 000 евро)',
            'en': 'Health insurance 30,000 EUR'
        },
        'address_proof': {
            'pl': 'Dokumenty potwierdzające koszty zamieszkania (np. umowa najmu, rachunki)',
            'ru': 'Документы, подтверждающие стоимость проживания (договор аренды, счета)',
            'en': 'Proof of address (rental agreement, bills)'
        },
        'financial_proof': {
            'pl': 'Środki finansowe na utrzymanie w Polsce',
            'ru': 'Финансовые средства на содержание в Польше',
            'en': 'Financial means for maintenance in Poland'
        },
        'załącznik_nr_1': {
            'pl': 'Załącznik nr 1',
            'ru': 'Приложение № 1',
            'en': 'Attachment No 1'
        },
        'employment_contract': {
            'pl': 'Oryginały umów o pracę / zlecenia',
            'ru': 'Оригиналы трудовых договоров',
            'en': 'Original employment contracts'
        },
        'work_permission': {
            'pl': 'Oświadczenie o powierzeniu pracy lub zezwolenie na pracę',
            'ru': 'Заявление о поручении работы или разрешение на работу',
            'en': 'Work assignment statement or work permit'
        },
        'pit_proof': {
            'pl': 'PIT-37 cudzoziemca z potwierdzeniem złożenia',
            'ru': 'PIT-37 иностранца с подтверждением подачи',
            'en': 'PIT-37 foreigner with submission confirmation'
        },
        'tax_clearance_employer': {
            'pl': 'Zaświadczenie ZUS dot. braku zaległości pracodawcy',
            'ru': 'Справка ZUS об отсутствии задолженности работодателя',
            'en': 'ZUS certificate - no employer arrears'
        },
        'tax_clearance_foreigner': {
            'pl': 'Zaświadczenie o niezaleganiu opłacania składek cudzoziemca',
            'ru': 'Справка об отсутствии задолженности по взносам иностранца',
            'en': 'Certificate of no contribution arrears for foreigner'
        },
        'no_dependents_statement': {
            'pl': 'Oświadczenie o braku osób na utrzymaniu w Polsce',
            'ru': 'Заявление об отсутствии иждивенцев в Польше',
            'en': 'Statement of no dependents in Poland'
        },
        'zus_rca_or_insurance': {
            'pl': 'ZUS RCA lub polisa ubezpieczeniowa',
            'ru': 'ZUS RCA или страховой полис',
            'en': 'ZUS RCA or insurance policy'
        },
        'zus_contribution_history': {
            'pl': 'Zaświadczenie z ZUS o przebiegu ubezpieczenia cudzoziemca',
            'ru': 'Справка из ZUS о ходе страхования иностранца',
            'en': 'ZUS certificate on insurance history of foreigner'
        },
        'employer_tax_return': {
            'pl': 'CIT lub PIT pracodawcy',
            'ru': 'CIT или PIT работодателя',
            'en': 'CIT or PIT of employer'
        },
        'zus_employee_count': {
            'pl': 'Zaświadczenie z ZUS o liczbie zgłoszonych pracowników i składkach',
            'ru': 'Справка из ZUS о количестве работников и взносах',
            'en': 'ZUS certificate on number of employees and contributions'
        },
        'statement_x': {
            'pl': 'Oświadczenie „x"',
            'ru': 'Заявление „x"',
            'en': 'Statement "x"'
        },
        'maintenance_statement': {
            'pl': 'Oświadczenie o utrzymaniu',
            'ru': 'Заявление о содержании',
            'en': 'Maintenance statement'
        },
        'wezwanie': {
            'pl': 'Wezwanie',
            'ru': 'Вызов (Wezwanie)',
            'en': 'Summons'
        },
    }
    
    # Update all existing DocumentRequirements
    updated_count = 0
    for doc_req in DocumentRequirement.objects.all():
        if doc_req.document_type in translations:
            tr = translations[doc_req.document_type]
            doc_req.custom_name_pl = tr['pl']
            doc_req.custom_name_ru = tr['ru']
            doc_req.custom_name_en = tr['en']
            doc_req.save(update_fields=['custom_name_pl', 'custom_name_ru', 'custom_name_en'])
            updated_count += 1
    
    print(f"Updated {updated_count} document requirements with translations")


def reverse_translations(apps, schema_editor):
    """Clear custom translations."""
    DocumentRequirement = apps.get_model('clients', 'DocumentRequirement')
    DocumentRequirement.objects.all().update(
        custom_name_pl=None,
        custom_name_ru=None,
        custom_name_en=None
    )


class Migration(migrations.Migration):
    dependencies = [
        ('clients', '0031_add_decision_date'),
    ]

    operations = [
        migrations.RunPython(populate_document_translations, reverse_translations),
    ]
