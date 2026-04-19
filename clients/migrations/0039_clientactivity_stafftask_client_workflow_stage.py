from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0038_add_wniosek_submission"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="workflow_stage",
            field=models.CharField(
                choices=[
                    ("new_client", "Новый клиент"),
                    ("document_collection", "Сбор документов"),
                    ("application_submitted", "Подача"),
                    ("fingerprints", "Отпечатки"),
                    ("waiting_decision", "Ожидание решения"),
                    ("decision_received", "Децизия"),
                    ("closed", "Закрыто"),
                ],
                default="new_client",
                max_length=32,
                verbose_name="Этап workflow",
            ),
        ),
        migrations.CreateModel(
            name="StaffTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255, verbose_name="Задача")),
                ("description", models.TextField(blank=True, verbose_name="Описание")),
                ("due_date", models.DateField(blank=True, null=True, verbose_name="Срок")),
                (
                    "priority",
                    models.CharField(
                        choices=[
                            ("low", "Низкий"),
                            ("medium", "Средний"),
                            ("high", "Высокий"),
                            ("urgent", "Срочный"),
                        ],
                        default="medium",
                        max_length=20,
                        verbose_name="Приоритет",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "Открыта"),
                            ("in_progress", "В работе"),
                            ("done", "Завершена"),
                            ("cancelled", "Отменена"),
                        ],
                        default="open",
                        max_length=20,
                        verbose_name="Статус",
                    ),
                ),
                ("completed_at", models.DateTimeField(blank=True, null=True, verbose_name="Завершена")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создана")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлена")),
                (
                    "assignee",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assigned_client_tasks",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Ответственный",
                    ),
                ),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_tasks",
                        to="clients.client",
                        verbose_name="Клиент",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_client_tasks",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Создал",
                    ),
                ),
                (
                    "document",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="staff_tasks",
                        to="clients.document",
                        verbose_name="Документ",
                    ),
                ),
                (
                    "payment",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="staff_tasks",
                        to="clients.payment",
                        verbose_name="Платёж",
                    ),
                ),
            ],
            options={
                "verbose_name": "Задача сотрудника",
                "verbose_name_plural": "Задачи сотрудников",
                "ordering": ["status", "due_date", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ClientActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("client_viewed", "Карточка клиента открыта"),
                            ("client_created", "Клиент создан"),
                            ("client_updated", "Данные клиента изменены"),
                            ("workflow_changed", "Этап workflow изменён"),
                            ("document_uploaded", "Документ загружен"),
                            ("document_downloaded", "Документ открыт"),
                            ("document_deleted", "Документ удалён"),
                            ("document_verified", "Статус документа изменён"),
                            ("email_sent", "Письмо отправлено"),
                            ("payment_created", "Платёж создан"),
                            ("payment_updated", "Платёж обновлён"),
                            ("payment_deleted", "Платёж удалён"),
                            ("task_created", "Задача создана"),
                            ("task_completed", "Задача завершена"),
                            ("note_updated", "Заметка обновлена"),
                        ],
                        max_length=50,
                        verbose_name="Тип события",
                    ),
                ),
                ("summary", models.CharField(max_length=255, verbose_name="Краткое описание")),
                ("details", models.TextField(blank=True, verbose_name="Детали")),
                ("metadata", models.JSONField(blank=True, default=dict, verbose_name="Метаданные")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="client_activities",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Сотрудник",
                    ),
                ),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="activities",
                        to="clients.client",
                        verbose_name="Клиент",
                    ),
                ),
                (
                    "document",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="activities",
                        to="clients.document",
                        verbose_name="Документ",
                    ),
                ),
                (
                    "payment",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="activities",
                        to="clients.payment",
                        verbose_name="Платёж",
                    ),
                ),
                (
                    "task",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="activities",
                        to="clients.stafftask",
                        verbose_name="Задача",
                    ),
                ),
            ],
            options={
                "verbose_name": "Событие клиента",
                "verbose_name_plural": "События клиентов",
                "ordering": ["-created_at"],
            },
        ),
    ]
