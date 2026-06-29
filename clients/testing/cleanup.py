from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from clients.models import Client, Document, EmailLog, Payment, TestRun, TestScenarioResult
from clients.testing.factories import TEST_EMAIL_DOMAIN, TEST_USER_PREFIX


@dataclass
class CleanupReport:
    deleted: dict[str, int] = field(default_factory=dict)
    files_deleted: int = 0
    file_errors: list[str] = field(default_factory=list)

    def add(self, label: str, count: int) -> None:
        self.deleted[label] = self.deleted.get(label, 0) + count

    def as_dict(self) -> dict[str, Any]:
        return {
            "deleted": self.deleted,
            "files_deleted": self.files_deleted,
            "file_errors": self.file_errors,
        }


def _delete_document_files(report: CleanupReport, *, extra_media_roots: list[str] | None = None) -> None:
    extra_roots = [Path(root) for root in (extra_media_roots or []) if root]
    configured_root = str(getattr(settings, "TEST_CENTER_MEDIA_ROOT", "") or "").strip()
    if configured_root:
        extra_roots.append(Path(configured_root))

    for document in Document.all_objects.filter(is_test_data=True).only("id", "file"):
        file_field = document.file
        if not file_field or not file_field.name:
            continue
        file_name = file_field.name
        deleted_names: set[str] = set()
        try:
            if file_field.storage.exists(file_name):
                file_field.delete(save=False)
                deleted_names.add(file_name)
                report.files_deleted += 1
        except Exception as exc:
            report.file_errors.append(f"document_id={document.pk}: {type(exc).__name__}")

        for root in extra_roots:
            candidate = root / file_name
            if file_name in deleted_names or not candidate.exists():
                continue
            try:
                candidate.unlink()
                deleted_names.add(file_name)
                report.files_deleted += 1
            except Exception as exc:
                report.file_errors.append(f"document_id={document.pk}: {type(exc).__name__}")


def cleanup_test_data(
    *,
    include_test_runs: bool = False,
    include_users: bool = True,
    extra_media_roots: list[str] | None = None,
) -> CleanupReport:
    report = CleanupReport()
    _delete_document_files(report, extra_media_roots=extra_media_roots)

    from clients.models import (
        Case,
        CaseArchiveBatch,
        ClientArchiveBatch,
        ClientDocumentRequirement,
        ClientFamilyMemberMOS,
        ClientOnboardingSession,
        DocumentProcessingJob,
        MOSApplicationData,
        PeselApplication,
        Reminder,
        StaffTask,
    )

    with transaction.atomic():
        # Case-scoped rows PROTECT-reference Case, and Case PROTECT-references
        # Client, so a test client can only be deleted after every case-scoped
        # child and the cases themselves are removed first. (Each Client gets an
        # auto-created primary Case via post_save, so this path is always hit.)
        test_client_ids = list(
            Client.all_objects.filter(is_test_data=True).values_list("pk", flat=True)
        )

        document_count, _ = Document.all_objects.filter(is_test_data=True).hard_delete()
        report.add("documents", document_count)

        payment_count, _ = Payment.all_objects.filter(is_test_data=True).hard_delete()
        report.add("payments", payment_count)

        email_count, _ = EmailLog.objects.filter(is_test_data=True).delete()
        report.add("email_logs", email_count)

        if test_client_ids:
            # Remaining PROTECT-to-Case children (documents/payments already gone).
            Reminder.objects.filter(client_id__in=test_client_ids).delete()
            StaffTask.objects.filter(client_id__in=test_client_ids).delete()
            ClientDocumentRequirement.objects.filter(client_id__in=test_client_ids).delete()
            ClientOnboardingSession.objects.filter(client_id__in=test_client_ids).delete()
            PeselApplication.objects.filter(client_id__in=test_client_ids).delete()
            ClientFamilyMemberMOS.objects.filter(client_id__in=test_client_ids).delete()
            DocumentProcessingJob.objects.filter(case__client_id__in=test_client_ids).delete()
            CaseArchiveBatch.objects.filter(case__client_id__in=test_client_ids).delete()
            # MOSApplicationData/CaseParticipant cascade from Case; delete the
            # cases, then the client-level archive batches.
            MOSApplicationData.objects.filter(client_id__in=test_client_ids).delete()
            # Case is a SoftDeleteModel: its queryset .delete() archives instead
            # of removing, so use hard_delete() to actually drop the rows.
            case_count, _ = Case.all_objects.filter(client_id__in=test_client_ids).hard_delete()
            report.add("cases", case_count)
            ClientArchiveBatch.objects.filter(client_id__in=test_client_ids).delete()

        client_count, _ = Client.all_objects.filter(is_test_data=True).hard_delete()
        report.add("clients", client_count)

        if include_test_runs:
            result_count, _ = TestScenarioResult.objects.filter(is_test_data=True).delete()
            run_count, _ = TestRun.objects.filter(is_test_data=True).delete()
            report.add("test_scenario_results", result_count)
            report.add("test_runs", run_count)

        if include_users:
            user_model = get_user_model()
            users = user_model.objects.filter(
                email__startswith=TEST_USER_PREFIX,
                email__endswith=TEST_EMAIL_DOMAIN,
            )
            user_count, _ = users.delete()
            report.add("users", user_count)

    return report
