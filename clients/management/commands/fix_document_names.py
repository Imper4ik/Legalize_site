from django.core.management.base import BaseCommand
from clients.models import DocumentRequirement

class Command(BaseCommand):
    help = 'Updates Russian translations for DocumentRequirements based on Polish names'

    def handle(self, *args, **options):
        # Map Polish (prefix/text) to Russian
        translations = {
            'oryginał oświadczenia o powierzeniu': 'Оригинал заявления о поручении выполнения работ или оригинал разрешения на работу',
            'oryginały umowy o pracę': 'Оригиналы трудового договора / договора поручения',
            'ZUS RCA potwierdzeniem': 'ZUS RCA с подтверждением отправки в ZUS или страховой полис',
            'potwierdzenie opłaty za zezwolenie': 'Подтверждение оплаты за разрешение (440 зл.) + 17 зл. за доверенность',
            'PIT-37 cudzoziemca': 'PIT-37 иностранца с подтверждением подачи в Налоговую инспекцию',
            'zaświadczenie z ZUS o dotychczasowym': 'Справка из ZUS о ходе страхования иностранца и об отсутствии задолженности по взносам',
            'zaświadczenie ZUS dot. braku': 'Справка из ZUS об отсутствии задолженности работодателя или другие документы',
            'CIT lub PIT pracodawcy': 'CIT или PIT работодателя',
        }

        updated_count = 0
        requirements = DocumentRequirement.objects.all()
        
        self.stdout.write(f"Checking {requirements.count()} requirements...")

        for req in requirements:
            # Check custom_name or custom_name_pl
            source_text = req.custom_name or req.custom_name_pl
            
            if not source_text:
                continue
                
            matched = False
            for pl_key, ru_text in translations.items():
                if pl_key in source_text:
                    if req.custom_name_ru != ru_text:
                        req.custom_name_ru = ru_text
                        req.save()
                        self.stdout.write(self.style.SUCCESS(f"Updated RU for: {source_text[:30]}..."))
                        updated_count += 1
                        matched = True
                    break
            
            if not matched and not req.custom_name_ru:
                # Optional: try to translate logic if needed, but for now specific list
                pass

        self.stdout.write(self.style.SUCCESS(f"Completed. Updated {updated_count} records."))
