from __future__ import annotations

import logging
import sys
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Exists, OuterRef

from clients.models import Case, CaseParticipant

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Заполняет отсутствующих главных участников (principal) для дел без вывода PII."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--batch-size", type=int, default=200, help="Размер пакета")
        parser.add_argument("--resume", action="store_true", help="Продолжить с прерванного места")
        parser.add_argument("--dry-run", action="store_true", help="Не сохранять изменения")
        parser.add_argument("--case-id", type=int, help="Идентификатор конкретного дела")

    def handle(self, *args: object, **options: Any) -> None:
        batch_size = options.get("batch_size", 200)
        dry_run = options.get("dry_run", False)
        case_id = options.get("case_id")
        resume = options.get("resume", False)

        self.stdout.write(
            f"Параметры: batch-size={batch_size}, dry-run={dry_run}, case-id={case_id}, resume={resume}"
        )

        try:
            # Находим дела без principal
            principal_exists = CaseParticipant.objects.filter(
                case=OuterRef("pk"),
                role="principal"
            )
            queryset = Case.all_objects.annotate(
                has_principal=Exists(principal_exists)
            ).filter(has_principal=False)

            if case_id:
                queryset = queryset.filter(pk=case_id)

            queryset = queryset.order_by("pk")

            total_to_process = queryset.count()
            self.stdout.write(f"Найдено дел без principal: {total_to_process}")

            if total_to_process == 0:
                self.stdout.write(self.style.SUCCESS("Нет дел для обработки."))
                return

            processed = 0
            created_count = 0

            # Обрабатываем батчами
            while True:
                # Берем первую пачку
                batch = list(queryset[:batch_size])
                if not batch:
                    break

                with transaction.atomic():
                    for case in batch:
                        self.stdout.write(f"Обработка дела ID={case.pk} (UUID={case.uuid})")
                        if not dry_run:
                            # Проверяем еще раз для надежности
                            if not CaseParticipant.objects.filter(case=case, role="principal").exists():
                                CaseParticipant.objects.create(
                                    case=case,
                                    client=case.client,
                                    role="principal"
                                )
                                created_count += 1
                        processed += 1

                self.stdout.write(f"Обработано в текущем пакете: {len(batch)} дел.")

                if dry_run or processed >= total_to_process:
                    break

            self.stdout.write(
                self.style.SUCCESS(
                    f"Завершено. Обработано дел: {processed}, создано участников: {created_count}"
                )
            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Критическая ошибка: {e.__class__.__name__}"))
            sys.exit(1)
