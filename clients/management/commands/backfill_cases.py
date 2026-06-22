import logging
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from clients.models import (
    Case, CaseParticipant, Document, DocumentVersion, Payment, Reminder, StaffTask,
    DocumentProcessingJob, ClientDocumentRequirement, WniosekSubmission,
    ClientFamilyMemberMOS, ClientOnboardingSession, PeselApplication, MOSApplicationData,
    ClientActivity, EmailLog, ClientArchiveBatch, CaseArchiveBatch, Client
)

logger = logging.getLogger(__name__)


class RollbackException(Exception):
    """Exception used to force rollback in dry-run mode."""
    pass


class Command(BaseCommand):
    help = "Идемпотентный перенос процессных полей из Client в Case и связывание дочерних объектов."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Запуск в режиме проверки без записи изменений в базу данных.",
        )
        parser.add_argument(
            "--resume",
            action="store_true",
            help="Продолжить прерванный перенос (пропускает клиентов с уже имеющимися делами backfill).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=0,
            help="Максимальное количество клиентов для обработки за один запуск (0 - без ограничений).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        resume = options["resume"]
        batch_size = options["batch_size"]

        User = get_user_model()
        actor_user = (
            User.objects.filter(is_superuser=True).first()
            or User.objects.filter(is_staff=True).first()
            or User.objects.first()
        )
        if not actor_user:
            self.stdout.write(self.style.ERROR("В системе нет пользователей для назначения автором архивации!"))
            return

        try:
            with transaction.atomic():
                self.run_backfill(dry_run, resume, batch_size, actor_user)
                if dry_run:
                    self.stdout.write(self.style.WARNING("DRY RUN: Откат изменений в базе данных..."))
                    raise RollbackException()
        except RollbackException:
            self.stdout.write(self.style.SUCCESS("DRY RUN: Все изменения успешно откачены."))

    def run_backfill(self, dry_run, resume, batch_size, actor_user):
        # Выбираем клиентов без привязанных дел
        clients_qs = Client.all_objects.all().order_by("id")
        if resume:
            clients_qs = clients_qs.exclude(cases__migration_origin="legacy_client_backfill")
        else:
            clients_qs = clients_qs.filter(cases__isnull=True)

        total_clients = clients_qs.count()
        self.stdout.write(self.style.SUCCESS(f"Найдено клиентов для миграции: {total_clients}"))

        if batch_size > 0:
            clients_to_process = clients_qs[:batch_size]
            self.stdout.write(self.style.SUCCESS(f"Обрабатываем батч размером {batch_size}"))
        else:
            clients_to_process = clients_qs

        processed_count = 0
        for client in clients_to_process:
            self.stdout.write(f"Миграция клиента ID={client.pk}: {client}")

            # Создаем основное дело
            case = Case.all_objects.create_from_client(client)
            case.migration_origin = "legacy_client_backfill"
            case.legacy_case_number = str(client.case_number or "")
            case.needs_manual_number_check = True

            if client.archived_at:
                case.archived_at = client.archived_at
                case.archived_by = client.archived_by or actor_user
            if client.deleted_at:
                case.deleted_at = client.deleted_at

            case.save()

            # Создаем участника дела с ролью principal
            CaseParticipant.objects.create(
                case=case,
                client=client,
                role="principal",
            )

            # Переносим архивные батчи
            if client.archived_at:
                client_batch = ClientArchiveBatch.objects.create(
                    client=client,
                    archived_by=client.archived_by or actor_user,
                    archived_at=client.archived_at,
                    status="archived",
                )
                CaseArchiveBatch.objects.create(
                    case=case,
                    client_archive_batch=client_batch,
                    archived_by=client.archived_by or actor_user,
                    archived_at=client.archived_at,
                    status="archived",
                )

            # Привязываем дочерние объекты к делу
            docs_updated = Document.all_objects.filter(client=client, case__isnull=True).update(case=case)
            doc_versions_updated = DocumentVersion.objects.filter(document__client=client, case__isnull=True).update(case=case)
            payments_updated = Payment.all_objects.filter(client=client, case__isnull=True).update(case=case)
            reminders_updated = Reminder.objects.filter(client=client, case__isnull=True).update(case=case)
            tasks_updated = StaffTask.objects.filter(client=client, case__isnull=True).update(case=case)
            reqs_updated = ClientDocumentRequirement.objects.filter(client=client, case__isnull=True).update(case=case)
            wniosek_updated = WniosekSubmission.objects.filter(client=client, case__isnull=True).update(case=case)
            family_mos_updated = ClientFamilyMemberMOS.objects.filter(client=client, case__isnull=True).update(case=case)
            
            # Для onboarding сессий обновляем также scope
            sessions_updated = ClientOnboardingSession.objects.filter(client=client, case__isnull=True).update(case=case, scope="case_link")
            
            pesel_updated = PeselApplication.objects.filter(client=client, case__isnull=True).update(case=case)
            mos_updated = MOSApplicationData.objects.filter(client=client, case__isnull=True).update(case=case)
            activities_updated = ClientActivity.objects.filter(client=client, case__isnull=True).update(case=case)
            emails_updated = EmailLog.objects.filter(client=client, case__isnull=True).update(case=case)
            jobs_updated = DocumentProcessingJob.objects.filter(document__client=client, case__isnull=True).update(case=case)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Успешно: документы={docs_updated}, версии_документов={doc_versions_updated}, "
                    f"платежи={payments_updated}, напоминания={reminders_updated}, задачи={tasks_updated}, "
                    f"onboarding={sessions_updated}, ocr_jobs={jobs_updated}"
                )
            )
            processed_count += 1

        self.stdout.write(self.style.SUCCESS(f"Завершено. Обработано клиентов: {processed_count}"))
