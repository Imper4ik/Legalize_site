import logging

from cryptography.fernet import InvalidToken
from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connection, models

from fernet_fields.fields import EncryptedFieldDecryptionError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Читает raw-данные через курсор и тестирует расшифровку Fernet для проверки целостности ключей."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Запуск проверки зашифрованных данных..."))

        total_checked = 0
        total_failed = 0
        total_plaintext = 0

        # Получаем все модели проекта
        all_models = apps.get_models()

        for model in all_models:
            # Находим зашифрованные поля на модели
            encrypted_fields = []
            for field in model._meta.get_fields():
                if isinstance(field, models.Field):
                    # Проверяем по имени класса или наследованию
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
                        rows = cursor.fetchall()
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f"Не удалось прочитать таблицу {table_name}: {str(e)}")
                        )
                        continue

                for pk, raw_val in rows:
                    if raw_val is None or raw_val == "":
                        continue

                    total_checked += 1
                    status = "Unknown"
                    is_success = False

                    # Проверяем структуру токена
                    is_token = isinstance(raw_val, str) and raw_val.startswith("gAAAA")

                    if not is_token:
                        status = "Legacy/Plaintext"
                        total_plaintext += 1
                        is_success = True
                    else:
                        try:
                            # Пробуем расшифровать
                            fernet_obj = getattr(field, "_fernet", None)
                            if fernet_obj is not None:
                                fernet_obj.decrypt(raw_val.encode("utf-8"))
                                status = "Decrypted"
                                is_success = True
                            else:
                                status = "No Fernet Object"
                        except (InvalidToken, EncryptedFieldDecryptionError):
                            status = "Decryption Failed"
                            total_failed += 1
                        except Exception as ex:
                            status = f"Error: {str(ex)}"
                            total_failed += 1

                    log_msg = f"{model.__name__} | ID: {pk} | Field: {field_name} | Status: {status}"
                    if is_success:
                        self.stdout.write(self.style.SUCCESS(log_msg))
                    else:
                        self.stdout.write(self.style.ERROR(log_msg))

        self.stdout.write(self.style.MIGRATE_HEADING("\n--- Итог проверки ---"))
        self.stdout.write(f"Всего проверено записей: {total_checked}")
        self.stdout.write(self.style.SUCCESS(f"Успешно расшифровано или plaintext: {total_checked - total_failed}"))
        self.stdout.write(self.style.WARNING(f"Из них Plaintext (не зашифровано): {total_plaintext}"))
        if total_failed > 0:
            self.stdout.write(self.style.ERROR(f"Ошибок расшифровки (неверный ключ!): {total_failed}"))
        else:
            self.stdout.write(self.style.SUCCESS("Ошибок расшифровки не обнаружено."))
