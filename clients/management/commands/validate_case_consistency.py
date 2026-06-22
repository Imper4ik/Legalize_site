from __future__ import annotations

import logging
import sys

from django.core.management.base import BaseCommand
from django.db.models import Count, F, Q

from clients.models import Case, CaseParticipant

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Проверяет согласованность дел и участников, находит нарушения без вывода PII."

    def handle(self, *args: object, **options: object) -> None:
        errors_found = False

        # 1. Cases без principal
        cases_without_principal = Case.all_objects.filter(
            ~Q(participants__role="principal")
        ).distinct()
        if cases_without_principal.exists():
            errors_found = True
            self.stdout.write(self.style.ERROR(f"Найдено дел без principal participant: {cases_without_principal.count()}"))
            for case in cases_without_principal:
                self.stdout.write(self.style.WARNING(f"  Дело ID={case.pk} (UUID={case.uuid}) не имеет главного заявителя."))

        # 2. Несколько principal в одном Case
        duplicate_principals = (
            CaseParticipant.objects.filter(role="principal")
            .values("case_id")
            .annotate(cnt=Count("id"))
            .filter(cnt__gt=1)
        )
        if duplicate_principals.exists():
            errors_found = True
            self.stdout.write(self.style.ERROR(f"Найдено дел с несколькими principal participants: {duplicate_principals.count()}"))
            for item in duplicate_principals:
                self.stdout.write(self.style.WARNING(f"  Дело ID={item['case_id']} имеет {item['cnt']} главных заявителей."))

        # 3. Principal имеет sponsor
        bad_principals_with_sponsor = CaseParticipant.objects.filter(role="principal", sponsor_participant__isnull=False)
        if bad_principals_with_sponsor.exists():
            errors_found = True
            self.stdout.write(self.style.ERROR(f"Найдено главных заявителей со спонсором: {bad_principals_with_sponsor.count()}"))
            for part in bad_principals_with_sponsor:
                self.stdout.write(self.style.WARNING(f"  Участник ID={part.pk} в деле ID={part.case_id} является principal, но имеет спонсора."))

        # 4. Sponsor принадлежит другому делу
        bad_sponsors_different_case = CaseParticipant.objects.filter(
            sponsor_participant__isnull=False
        ).exclude(sponsor_participant__case_id=F("case_id"))
        if bad_sponsors_different_case.exists():
            errors_found = True
            self.stdout.write(self.style.ERROR(f"Найдено спонсоров из других дел: {bad_sponsors_different_case.count()}"))
            for part in bad_sponsors_different_case:
                self.stdout.write(self.style.WARNING(f"  Участник ID={part.pk} в деле ID={part.case_id} имеет спонсора из другого дела."))

        # 5. Sponsor равен самому себе
        bad_self_sponsor = CaseParticipant.objects.filter(sponsor_participant=F("id"))
        if bad_self_sponsor.exists():
            errors_found = True
            self.stdout.write(self.style.ERROR(f"Найдено участников, являющихся спонсорами самих себя: {bad_self_sponsor.count()}"))
            for part in bad_self_sponsor:
                self.stdout.write(self.style.WARNING(f"  Участник ID={part.pk} в деле ID={part.case_id} ссылается на себя как на спонсора."))

        # 6. Case.client совпадает с Client principal participant
        bad_principal_client = CaseParticipant.objects.filter(
            role="principal"
        ).exclude(client_id=F("case__client_id"))
        if bad_principal_client.exists():
            errors_found = True
            self.stdout.write(self.style.ERROR(f"Найдено несоответствий клиента дела и главного заявителя: {bad_principal_client.count()}"))
            for part in bad_principal_client:
                self.stdout.write(self.style.WARNING(f"  Участник ID={part.pk} в деле ID={part.case_id} имеет client_id={part.client_id}, но у дела client_id={part.case.client_id}."))

        if errors_found:
            self.stdout.write(self.style.ERROR("Проверка согласованности дел завершилась с ошибками."))
            sys.exit(1)
        else:
            self.stdout.write(self.style.SUCCESS("Все проверки согласованности дел успешно пройдены."))
