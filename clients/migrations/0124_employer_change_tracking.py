import re
import unicodedata

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


def _normalize(value):
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char)).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def backfill_employers(apps, schema_editor):
    Company = apps.get_model("clients", "Company")
    Case = apps.get_model("clients", "Case")
    Assignment = apps.get_model("clients", "CaseEmployerAssignment")
    for company in Company.objects.all().iterator():
        company.normalized_name = _normalize(company.name)
        company.save(update_fields=["normalized_name"])
    for case in Case._base_manager.filter(company_id__isnull=False, archived_at__isnull=True).iterator():
        Assignment.objects.get_or_create(case_id=case.pk, defaults={"company_id": case.company_id, "source": "migration"})


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("clients", "0123_document_confirms_submission"),
    ]

    operations = [
        migrations.AddField(model_name="company", name="krs", field=models.CharField(blank=True, db_index=True, default="", max_length=10, verbose_name="KRS")),
        migrations.AddField(model_name="company", name="nip", field=models.CharField(blank=True, db_index=True, default="", max_length=10, verbose_name="NIP")),
        migrations.AddField(model_name="company", name="normalized_name", field=models.CharField(blank=True, db_index=True, default="", max_length=255)),
        migrations.AddField(model_name="company", name="regon", field=models.CharField(blank=True, db_index=True, default="", max_length=14, verbose_name="REGON")),
        migrations.CreateModel(
            name="CaseEmployerAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("started_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("effective_from", models.DateField(blank=True, null=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("source", models.CharField(blank=True, default="manual", max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("case", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="employer_assignments", to="clients.case")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="case_assignments", to="clients.company")),
                ("confirmed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="confirmed_employer_assignments", to=settings.AUTH_USER_MODEL)),
                ("source_document", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="employer_assignments", to="clients.document")),
            ],
            options={"ordering": ["-started_at", "-id"]},
        ),
        migrations.CreateModel(
            name="EmployerChangeCandidate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("proposed_name", models.CharField(blank=True, default="", max_length=255)),
                ("proposed_nip", models.CharField(blank=True, default="", max_length=10)),
                ("proposed_regon", models.CharField(blank=True, default="", max_length=14)),
                ("proposed_krs", models.CharField(blank=True, default="", max_length=10)),
                ("effective_from", models.DateField(blank=True, null=True)),
                ("source", models.CharField(blank=True, default="document_ocr", max_length=32)),
                ("confidence", models.CharField(blank=True, default="", max_length=16)),
                ("fingerprint", models.CharField(max_length=64, unique=True)),
                ("status", models.CharField(choices=[("pending", "Ожидает проверки"), ("confirmed", "Новый работодатель подтверждён"), ("same", "Тот же работодатель"), ("ocr_error", "Ошибка распознавания"), ("needs_info", "Нужна информация"), ("deferred", "Отложено")], db_index=True, default="pending", max_length=16)),
                ("review_note", models.TextField(blank=True, default="")),
                ("detected_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("case", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="employer_change_candidates", to="clients.case")),
                ("current_company", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="employer_change_candidates_as_current", to="clients.company")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_employer_changes", to=settings.AUTH_USER_MODEL)),
                ("source_document", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="employer_change_candidates", to="clients.document")),
            ],
            options={"ordering": ["-detected_at", "-id"]},
        ),
        migrations.AddConstraint(model_name="caseemployerassignment", constraint=models.UniqueConstraint(condition=Q(("ended_at__isnull", True)), fields=("case",), name="one_active_employer_per_case")),
        migrations.AddIndex(model_name="employerchangecandidate", index=models.Index(fields=["case", "status"], name="employer_case_status_idx")),
        migrations.AlterField(
            model_name="stafftask",
            name="task_type",
            field=models.CharField(
                choices=[
                    ("document_review", "Проверка документов"), ("missing_document", "Недостающий документ"),
                    ("zus_update", "Обновление ZUS"), ("case_number_missing", "Отсутствует номер дела"),
                    ("fingerprints_followup", "Контроль после отпечатков"), ("payment_followup", "Контроль оплаты"),
                    ("client_question", "Вопрос клиента"), ("internal_note", "Внутренняя заметка"),
                    ("deadline_check", "Контроль дедлайна"), ("employer_review", "Проверка работодателя"),
                ],
                default="internal_note", max_length=50, verbose_name="Тип задачи",
            ),
        ),
        migrations.RunPython(backfill_employers, migrations.RunPython.noop),
    ]
