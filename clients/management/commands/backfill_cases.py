from __future__ import annotations

import logging
import sys
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from clients.models import (
    Case,
    CaseArchiveBatch,
    CaseParticipant,
    Client,
    ClientActivity,
    ClientArchiveBatch,
    ClientDocumentRequirement,
    ClientFamilyMemberMOS,
    ClientOnboardingSession,
    Document,
    DocumentProcessingJob,
    DocumentVersion,
    EmailLog,
    MOSApplicationData,
    Payment,
    PeselApplication,
    Reminder,
    StaffTask,
    WniosekSubmission,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Идемпотентный перенос процессных полей из Client в Case и связывание дочерних объектов."

    def add_arguments(self, parser: CommandParser) -> None:
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
            default=200,
            help="Максимальное количество клиентов для обработки за один запуск (по умолчанию 200).",
        )
        parser.add_argument(
            "--client-id",
            type=int,
            default=None,
            help="Идентификатор конкретного клиента для обработки.",
        )
        parser.add_argument(
            "--report",
            action="store_true",
            help="Вывести подробный отчет о проделанной работе.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = options["dry_run"]
        resume = options["resume"]
        batch_size = options["batch_size"]
        client_id = options["client_id"]
        report = options["report"]

        User = get_user_model()
        actor_user = (
            User.objects.filter(is_superuser=True).first()
            or User.objects.filter(is_staff=True).first()
            or User.objects.first()
        )
        if not actor_user:
            self.stdout.write(self.style.ERROR("В системе нет пользователей для назначения автором архивации!"))
            sys.exit(1)

        try:
            self.run_backfill(dry_run, resume, batch_size, client_id, report, actor_user)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Критическая ошибка во время выполнения: {str(e)}"))
            sys.exit(1)

    def run_backfill(
        self,
        dry_run: bool,
        resume: bool,
        batch_size: int,
        client_id: int | None,
        report: bool,
        actor_user: Any,
    ) -> None:
        clients_qs = Client.all_objects.all().order_by("id")
        if client_id is not None:
            clients_qs = clients_qs.filter(pk=client_id)
        elif resume:
            clients_qs = clients_qs.exclude(cases__migration_origin="legacy_client_backfill")
        else:
            clients_qs = clients_qs.filter(cases__isnull=True)

        total_to_process = clients_qs.count()
        self.stdout.write(self.style.SUCCESS(f"Найдено клиентов для миграции: {total_to_process}"))

        if batch_size > 0 and client_id is None:
            clients_to_process = list(clients_qs[:batch_size])
        else:
            clients_to_process = list(clients_qs)

        processed_count = 0
        skipped_count = 0
        error_count = 0

        chunk_size = 50
        for i in range(0, len(clients_to_process), chunk_size):
            chunk = clients_to_process[i : i + chunk_size]
            try:
                with transaction.atomic():
                    for client in chunk:
                        if Case.all_objects.filter(client=client, migration_origin="legacy_client_backfill").exists():
                            skipped_count += 1
                            continue

                        # Создаем Case с legacy_case_number
                        case = Case.all_objects.create(
                            client=client,
                            legacy_case_number=str(getattr(client, "case_number", "") or ""),
                            needs_manual_number_check=True,
                            internal_number="",
                            authority_case_number="",
                            status=getattr(client, "status", "new") or "new",
                            workflow_stage=getattr(client, "workflow_stage", "new_client") or "new_client",
                            application_purpose=getattr(client, "application_purpose", "") or "",
                            basis_of_stay=getattr(client, "basis_of_stay", "") or "",
                            submission_date=getattr(client, "submission_date", None),
                            fingerprints_date=getattr(client, "fingerprints_date", None),
                            fingerprints_time=getattr(client, "fingerprints_time", None),
                            fingerprints_location=getattr(client, "fingerprints_location", "") or "",
                            fingerprints_ticket=getattr(client, "fingerprints_ticket", "") or "",
                            fingerprints_list=getattr(client, "fingerprints_list", "") or "",
                            fingerprints_info=getattr(client, "fingerprints_info", "") or "",
                            decision_date=getattr(client, "decision_date", None),
                            company=getattr(client, "company", None),
                            is_test_data=getattr(client, "is_test_data", False),
                            is_demo_data=getattr(client, "is_demo_data", False),
                        )
                        case.migration_origin = "legacy_client_backfill"
                        if client.archived_at:
                            case.archived_at = client.archived_at
                            case.archived_by = client.archived_by or actor_user
                        case.save()

                        # CaseParticipant
                        CaseParticipant.objects.get_or_create(
                            case=case,
                            client=client,
                            defaults={"role": "principal"},
                        )

                        # Переносим архивные батчи
                        if client.archived_at:
                            client_batch, _ = ClientArchiveBatch.objects.get_or_create(
                                client=client,
                                status="archived",
                                defaults={
                                    "archived_by": client.archived_by or actor_user,
                                    "archived_at": client.archived_at,
                                },
                            )
                            CaseArchiveBatch.objects.get_or_create(
                                case=case,
                                client_archive_batch=client_batch,
                                status="archived",
                                defaults={
                                    "archived_by": client.archived_by or actor_user,
                                    "archived_at": client.archived_at,
                                },
                            )

                        # Привязываем дочерние объекты к делу
                        Document.all_objects.filter(client=client, case__isnull=True).update(case=case)
                        DocumentVersion.objects.filter(document__client=client, case__isnull=True).update(case=case)
                        Payment.all_objects.filter(client=client, case__isnull=True).update(case=case)
                        Reminder.objects.filter(client=client, case__isnull=True).update(case=case)
                        StaffTask.objects.filter(client=client, case__isnull=True).update(case=case)
                        ClientDocumentRequirement.objects.filter(client=client, case__isnull=True).update(case=case)
                        WniosekSubmission.objects.filter(client=client, case__isnull=True).update(case=case)
                        ClientFamilyMemberMOS.objects.filter(client=client, case__isnull=True).update(case=case)
                        ClientOnboardingSession.objects.filter(client=client, case__isnull=True).update(case=case, scope="case_link")
                        PeselApplication.objects.filter(client=client, case__isnull=True).update(case=case)
                        MOSApplicationData.objects.filter(client=client, case__isnull=True).update(case=case)
                        ClientActivity.objects.filter(client=client, case__isnull=True).update(case=case)
                        EmailLog.objects.filter(client=client, case__isnull=True).update(case=case)
                        DocumentProcessingJob.objects.filter(document__client=client, case__isnull=True).update(case=case)

                        processed_count += 1

                    if dry_run:
                        raise transaction.TransactionManagementError("Dry run rollback")
            except transaction.TransactionManagementError:
                self.stdout.write(self.style.WARNING(f"DRY RUN: Откат пачки из {len(chunk)} клиентов."))
            except Exception as e:
                error_count += len(chunk)
                self.stdout.write(self.style.ERROR(f"Ошибка при обработке пачки клиентов: {str(e)}"))
                raise e

        if report:
            self.stdout.write(self.style.MIGRATE_HEADING("\n--- Отчет о переносе ---"))
            self.stdout.write(f"Всего клиентов для обработки: {total_to_process}")
            self.stdout.write(self.style.SUCCESS(f"Успешно обработано: {processed_count}"))
            self.stdout.write(self.style.WARNING(f"Пропущено (уже обработаны): {skipped_count}"))
            if error_count > 0:
                self.stdout.write(self.style.ERROR(f"Ошибок (клиентов не обработано): {error_count}"))
