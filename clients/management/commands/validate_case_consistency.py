from __future__ import annotations

import logging
import sys
from django.core.management.base import BaseCommand
from django.db.models import Count, F, Q, Exists, OuterRef

from clients.models import (
    Case,
    CaseParticipant,
    Document,
    Payment,
    Reminder,
    StaffTask,
    MOSApplicationData,
    PeselApplication,
    CaseArchiveBatch
)

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

        # 7. child.case.client != child.client (семейный участник не должен совпадать с владельцем дела)
        bad_family_client = CaseParticipant.objects.exclude(
            role="principal"
        ).filter(client_id=F("case__client_id"))
        if bad_family_client.exists():
            errors_found = True
            self.stdout.write(self.style.ERROR(f"Найдено семейных участников, совпадающих с владельцем дела: {bad_family_client.count()}"))
            for part in bad_family_client:
                self.stdout.write(self.style.WARNING(f"  Участник ID={part.pk} (роль={part.role}) в деле ID={part.case_id} совпадает с основным клиентом дела."))

        # 8. Process object без Case
        docs_no_case = Document.objects.filter(case__isnull=True)
        if docs_no_case.exists():
            errors_found = True
            self.stdout.write(self.style.ERROR(f"Найдено документов без дела: {docs_no_case.count()}"))
            for d in docs_no_case:
                self.stdout.write(self.style.WARNING(f"  Документ ID={d.pk} не имеет привязки к делу."))

        payments_no_case = Payment.objects.filter(case__isnull=True)
        if payments_no_case.exists():
            errors_found = True
            self.stdout.write(self.style.ERROR(f"Найдено платежей без дела: {payments_no_case.count()}"))
            for p in payments_no_case:
                self.stdout.write(self.style.WARNING(f"  Платеж ID={p.pk} не имеет привязки к делу."))

        reminders_no_case = Reminder.objects.filter(case__isnull=True)
        if reminders_no_case.exists():
            errors_found = True
            self.stdout.write(self.style.ERROR(f"Найдено напоминаний без дела: {reminders_no_case.count()}"))
            for r in reminders_no_case:
                self.stdout.write(self.style.WARNING(f"  Напоминание ID={r.pk} не имеет привязки к делу."))

        tasks_no_case = StaffTask.objects.filter(case__isnull=True)
        if tasks_no_case.exists():
            errors_found = True
            self.stdout.write(self.style.ERROR(f"Найдено задач без дела: {tasks_no_case.count()}"))
            for t in tasks_no_case:
                self.stdout.write(self.style.WARNING(f"  Задача ID={t.pk} не имеет привязки к делу."))

        mos_no_case = MOSApplicationData.objects.filter(case__isnull=True)
        if mos_no_case.exists():
            errors_found = True
            self.stdout.write(self.style.ERROR(f"Найдено MOS анкет без дела: {mos_no_case.count()}"))
            for m in mos_no_case:
                self.stdout.write(self.style.WARNING(f"  MOS анкета ID={m.pk} не имеет привязки к делу."))

        pesel_no_case = PeselApplication.objects.filter(case__isnull=True)
        if pesel_no_case.exists():
            errors_found = True
            self.stdout.write(self.style.ERROR(f"Найдено PESEL анкет без дела: {pesel_no_case.count()}"))
            for p in pesel_no_case:
                self.stdout.write(self.style.WARNING(f"  PESEL анкета ID={p.pk} не имеет привязки к делу."))

        # 9. Case с некорректным archive state
        # a) Активные дела у архивных клиентов
        bad_active_cases_of_archived_clients = Case.all_objects.filter(
            archived_at__isnull=True,
            client__archived_at__isnull=False
        )
        if bad_active_cases_of_archived_clients.exists():
            errors_found = True
            self.stdout.write(self.style.ERROR(f"Найдено активных дел у заархивированных клиентов: {bad_active_cases_of_archived_clients.count()}"))
            for case in bad_active_cases_of_archived_clients:
                self.stdout.write(self.style.WARNING(f"  Дело ID={case.pk} активно, но его клиент заархивирован."))

        # b) Архивные дела без активного CaseArchiveBatch (status="archived")
        active_batch_exists = CaseArchiveBatch.objects.filter(case=OuterRef("pk"), status="archived")
        bad_archived_cases_no_batch = Case.all_objects.filter(
            archived_at__isnull=False
        ).annotate(has_batch=Exists(active_batch_exists)).filter(has_batch=False)
        if bad_archived_cases_no_batch.exists():
            errors_found = True
            self.stdout.write(self.style.ERROR(f"Найдено архивных дел без активного батча архивации: {bad_archived_cases_no_batch.count()}"))
            for case in bad_archived_cases_no_batch:
                self.stdout.write(self.style.WARNING(f"  Дело ID={case.pk} заархивировано, но активный CaseArchiveBatch отсутствует."))

        # c) Активные дела, у которых есть активный CaseArchiveBatch (status="archived")
        bad_active_cases_with_batch = Case.all_objects.filter(
            archived_at__isnull=True
        ).annotate(has_batch=Exists(active_batch_exists)).filter(has_batch=True)
        if bad_active_cases_with_batch.exists():
            errors_found = True
            self.stdout.write(self.style.ERROR(f"Найдено активных дел с активным батчом архивации: {bad_active_cases_with_batch.count()}"))
            for case in bad_active_cases_with_batch:
                self.stdout.write(self.style.WARNING(f"  Дело ID={case.pk} активно, но имеет активный CaseArchiveBatch."))

        if errors_found:
            self.stdout.write(self.style.ERROR("Проверка согласованности дел завершилась с ошибками."))
            sys.exit(1)
        else:
            self.stdout.write(self.style.SUCCESS("Все проверки согласованности дел успешно пройдены."))
