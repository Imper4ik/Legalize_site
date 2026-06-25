from __future__ import annotations

import logging
import sys
from typing import Any

from cryptography.fernet import InvalidToken
from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connection, models

from fernet_fields.fields import EncryptedFieldDecryptionError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Читает raw-данные через курсор и тестирует расшифровку Fernet для проверки целостности ключей."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--model",
            type=str,
            help="Имя модели для проверки (например, clients.Document или Document)",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Размер пакета выборки",
        )

    def handle(self, *args: object, **options: Any) -> None:
        model_filter = options.get("model")
        batch_size = options.get("batch_size", 1000)

        self.stdout.write(self.style.SUCCESS("Запуск проверки зашифрованных данных..."))

        total_checked = 0
        total_ok = 0
        total_not_encrypted = 0
        total_failed = 0
        total_errors = 0

        # Получаем все модели проекта
        all_models = apps.get_models()

        for model in all_models:
            model_name_full = f"{model._meta.app_label}.{model.__name__}"
            if model_filter:
                if model_filter not in (model.__name__, model_name_full):
                    continue

            # Находим зашифрованные поля на модели
            encrypted_fields = []
            for field in model._meta.get_fields():
                if isinstance(field, models.Field):
                    class_name = field.__class__.__name__
                    if "Encrypted" in class_name or hasattr(field, "_fernet"):
                        encrypted_fields.append(field)

            if not encrypted_fields:
                continue

            table_name = model._meta.db_table
            pk_field = model._meta.pk
            pk_col = pk_field.column

            for field in encrypted_fields:
                field_name = field.name
                field_col = field.column

                self.stdout.write(
                    self.style.HTTP_INFO(f"Проверка {model.__name__}.{field_name} (таблица: {table_name})...")
                )

                # Выполняем raw SQL запрос через курсор для получения сырых зашифрованных значений
                query = f'SELECT "{pk_col}", "{field_col}" FROM "{table_name}"'
                with connection.cursor() as cursor:
                    try:
                        cursor.execute(query)
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(
                                f"Не удалось прочитать таблицу {table_name}: {e.__class__.__name__}"
                            )
                        )
                        total_errors += 1
                        continue

                    while True:
                        rows = cursor.fetchmany(batch_size)
                        if not rows:
                            break

                        for pk, raw_val in rows:
                            if raw_val is None or raw_val == "":
                                # NULL/пустое значение допустимо
                                continue

                            total_checked += 1
                            status = "Unknown"

                            # Проверяем структуру токена
                            is_token = isinstance(raw_val, str) and raw_val.startswith("gAAAA")

                            if not is_token:
                                status = "NOT_ENCRYPTED"
                                total_not_encrypted += 1
                            else:
                                try:
                                    fernet_obj = getattr(field, "_fernet", None)
                                    if fernet_obj is not None:
                                        # Пробуем расшифровать (MultiFernet rotation тестируется автоматически)
                                        fernet_obj.decrypt(raw_val.encode("utf-8"))
                                        status = "OK"
                                        total_ok += 1
                                    else:
                                        status = "ERROR"
                                        total_errors += 1
                                except (InvalidToken, EncryptedFieldDecryptionError):
                                    status = "DECRYPTION_FAILED"
                                    total_failed += 1
                                except Exception:
                                    status = "ERROR"
                                    total_errors += 1

                            log_msg = f"{model.__name__} | ID: {pk} | Field: {field_name} | Status: {status}"
                            if status in ("OK", "NOT_ENCRYPTED"):
                                self.stdout.write(self.style.SUCCESS(log_msg))
                            else:
                                self.stdout.write(self.style.ERROR(log_msg))

        self.stdout.write(self.style.MIGRATE_HEADING("\n--- Итог проверки ---"))
        self.stdout.write(f"Всего проверено зашифрованных полей/записей (не пустых): {total_checked}")
        self.stdout.write(self.style.SUCCESS(f"OK (успешно расшифровано): {total_ok}"))
        self.stdout.write(self.style.WARNING(f"NOT_ENCRYPTED (открытый текст): {total_not_encrypted}"))
        self.stdout.write(self.style.ERROR(f"DECRYPTION_FAILED (ошибка расшифровки): {total_failed}"))
        self.stdout.write(self.style.ERROR(f"ERROR (критическая ошибка): {total_errors}"))

        # Plaintext after migration (NOT_ENCRYPTED), failed decryption and
        # critical errors are all failures and must yield a non-zero exit code.
        if total_failed > 0 or total_errors > 0 or total_not_encrypted > 0:
            sys.exit(1)
