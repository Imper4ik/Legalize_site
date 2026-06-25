from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta
from typing import Any, cast

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from clients.models import Client, ClientDocumentRequirement, Document, Payment, Reminder
from clients.services.custom_document_requirements import sync_custom_document_requirement_reminder
from clients.services.notifications import (
    _get_missing_documents_context,
    send_expiring_documents_email,
    send_legal_stay_email,
    send_missing_documents_email,
)
from clients.services.zus import format_zus_months, missing_zus_months

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Create daily document, payment, ZUS RCA, and missing-document reminders safely."

    SECTIONS = ("payments", "documents", "zus", "missing-docs", "legal-stay", "custom-documents")

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created or sent without mutating data.",
        )
        parser.add_argument(
            "--only",
            action="append",
            choices=self.SECTIONS,
            help="Run only one reminder section. Can be passed multiple times.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = bool(options.get("dry_run"))
        selected_sections = set(options.get("only") or self.SECTIONS)

        self.stdout.write(self.style.SUCCESS("--- Starting reminder update ---"))
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN: no reminders or emails will be created."))

        try:
            if "missing-docs" in selected_sections:
                self.stdout.write(self.style.HTTP_INFO("-> Checking waiting-decision missing documents..."))
                self.send_missing_document_notifications(dry_run=dry_run)

            if "zus" in selected_sections:
                self.stdout.write(self.style.HTTP_INFO("-> Checking missing ZUS RCA months..."))
                self.check_zus_rca_missing_months(
                    dry_run=dry_run,
                    send_email="missing-docs" not in selected_sections,
                )

            if "documents" in selected_sections:
                self.stdout.write(self.style.HTTP_INFO("-> Checking expiring document emails..."))
                self.send_expiring_document_notifications(dry_run=dry_run)
                if dry_run:
                    self.create_document_reminders(dry_run=True)
                else:
                    with transaction.atomic():
                        self.create_document_reminders()

            if "payments" in selected_sections:
                if dry_run:
                    self.create_payment_reminders(dry_run=True)
                else:
                    with transaction.atomic():
                        self.create_payment_reminders()

            if "legal-stay" in selected_sections:
                self.stdout.write(self.style.HTTP_INFO("-> Checking legal stay expiration..."))
                self.send_legal_stay_notifications(dry_run=dry_run)
                if dry_run:
                    self.create_legal_stay_reminders(dry_run=True)
                else:
                    with transaction.atomic():
                        self.create_legal_stay_reminders()
            if "custom-documents" in selected_sections:
                self.sync_custom_document_requirement_reminders(dry_run=dry_run)

            self.stdout.write(self.style.SUCCESS("--- Reminder update completed ---"))
        except Exception as exc:
            logger.exception("update_reminders failed")
            self.stdout.write(self.style.ERROR(f"update_reminders failed: {exc}"))
            raise CommandError("update_reminders failed") from exc

    def send_missing_document_notifications(self, *, dry_run: bool = False) -> None:
        today = timezone.localdate()
        from clients.models import Case
        cases = Case.objects.active().filter(
            workflow_stage="waiting_decision",
            fingerprints_date__isnull=False,
            fingerprints_date__lte=today,
            decision_date__isnull=True,
        ).exclude(client__email="")

        sent_count = 0
        skipped_count = 0
        iso_year, iso_week, _iso_weekday = today.isocalendar()
        for case in cases.iterator():
            client = case.client
            weekly_key = f"waiting_decision_missing_docs:{case.pk}:{iso_year}-W{iso_week:02d}"
            if dry_run:
                sent = 1 if _get_missing_documents_context(case) else 0
            else:
                sent = send_missing_documents_email(case, weekly_key=weekly_key)

            sent_count += sent
            if dry_run and sent:
                logger.info("notification would send: template=missing_documents client_id=%s", client.pk)
            elif sent:
                logger.info("notification sent: template=missing_documents client_id=%s", client.pk)
            else:
                skipped_count += 1
                logger.info("notification skipped: template=missing_documents client_id=%s", client.pk)

        prefix = "DRY RUN: would send" if dry_run else "Sent"
        self.stdout.write(f"{prefix} {sent_count} missing-document emails. skipped={skipped_count}")

    def check_zus_rca_missing_months(self, *, dry_run: bool = False, send_email: bool = True) -> None:
        today = timezone.localdate()
        from clients.models import Case
        cases = Case.objects.active().filter(
            workflow_stage="waiting_decision",
            fingerprints_date__isnull=False,
            fingerprints_date__lte=today,
            decision_date__isnull=True,
        )
        affected = 0
        sent_count = 0
        skipped_count = 0
        iso_year, iso_week, _iso_weekday = today.isocalendar()
        for case in cases.iterator():
            client = case.client
            missing = missing_zus_months(case, today=today)
            if missing:
                affected += 1
                months = format_zus_months(missing)
                message = f"ZUS RCA missing months: case_id={case.pk}, client_id={client.pk}, months={months}"
                logger.info(message)
                self.stdout.write(message)

                if not send_email:
                    skipped_count += 1
                    logger.info(
                        "notification skipped: template=missing_documents reason=zus_rca_missing "
                        "case_id=%s covered_by=missing_docs_section",
                        case.pk,
                    )
                    continue

                weekly_key = f"zus_rca_missing:{case.pk}:{iso_year}-W{iso_week:02d}"
                if dry_run:
                    sent = 1 if client.email and _get_missing_documents_context(case, today=today) else 0
                else:
                    sent = send_missing_documents_email(case, weekly_key=weekly_key, today=today)

                sent_count += sent
                if dry_run and sent:
                    logger.info("notification would send: template=missing_documents reason=zus_rca_missing client_id=%s", client.pk)
                elif sent:
                    logger.info("notification sent: template=missing_documents reason=zus_rca_missing client_id=%s", client.pk)
                else:
                    skipped_count += 1
                    logger.info("notification skipped: template=missing_documents reason=zus_rca_missing client_id=%s", client.pk)
        if affected == 0:
            self.stdout.write("ZUS RCA missing months logs: none.")

        prefix = "DRY RUN: would send" if dry_run else "Sent"
        self.stdout.write(f"{prefix} {sent_count} ZUS RCA missing-month emails. skipped={skipped_count}")

    def send_expiring_document_notifications(self, *, dry_run: bool = False) -> None:
        today = timezone.localdate()
        cutoff = today + timedelta(days=7)
        expiring_docs = Document.objects.for_active_cases().select_related("client", "case").filter(
            expiry_date__isnull=False,
            expiry_date__gte=today,
            expiry_date__lte=cutoff,
        )

        if not expiring_docs.exists():
            self.stdout.write("No documents expire within the email window.")
            return

        docs_by_client: dict[int, list[Document]] = defaultdict(list)
        for document in expiring_docs.iterator():
            docs_by_client[document.client_id].append(document)

        sent_count = 0
        for documents in docs_by_client.values():
            client = documents[0].client
            if dry_run:
                sent_count += 1
                self.stdout.write(
                    f"DRY RUN: would send expiring documents email client_id={client.pk} documents={len(documents)}"
                )
                continue

            sent_count += send_expiring_documents_email(client, documents)

        if not dry_run:
            self.stdout.write(f"Sent {sent_count} expiring-document emails.")

    def create_document_reminders(self, *, dry_run: bool = False) -> None:
        today = timezone.localdate()
        reminder_period_start = today - timedelta(days=30)
        reminder_period_end = today + timedelta(days=30)

        expiring_docs = Document.objects.for_active_cases().select_related("client").filter(
            expiry_date__isnull=False,
            expiry_date__gte=reminder_period_start,
            expiry_date__lte=reminder_period_end,
            reminder__isnull=True,
        )

        if not expiring_docs.exists():
            self.stdout.write("No expiring documents need reminders.")
            return

        count = 0
        for document in expiring_docs.iterator():
            if dry_run:
                count += 1
                continue

            count += 1

            Reminder.objects.create(
                client=document.client,
                case=document.case,
                document=document,
                title=f"Document validity check: {document.display_name}",
                notes=f"Document validity date for client_id={document.client_id}: {document.expiry_date:%d.%m.%Y}.",
                due_date=cast(Any, document.expiry_date),
                reminder_type="document",
            )

        prefix = "DRY RUN: would create" if dry_run else "Created"
        self.stdout.write(self.style.SUCCESS(f"{prefix} {count} document reminders."))

    def create_payment_reminders(self, *, dry_run: bool = False) -> None:
        today = timezone.localdate()
        due_payments = Payment.objects.for_active_cases().select_related("client", "case").filter(
            due_date__lte=today,
            status__in=["pending", "partial"],
        ).exclude(reminder__is_active=True)

        if not due_payments.exists():
            self.stdout.write("No due payments need reminders.")
            return

        count = 0
        for payment in due_payments.iterator():
            count += 1
            if dry_run:
                continue

            Reminder.objects.update_or_create(
                payment=payment,
                defaults={
                    "client": payment.client,
                    "case": payment.case,
                    "title": f"Payment due: {payment.get_service_description_display()}",
                    "notes": (
                        f"Payment total={payment.total_amount}; amount_due={payment.amount_due}; "
                        f"client_id={payment.client_id}."
                    ),
                    "due_date": cast(Any, payment.due_date),
                    "reminder_type": "payment",
                    "is_active": True,
                },
            )

        prefix = "DRY RUN: would create" if dry_run else "Created"
        self.stdout.write(self.style.SUCCESS(f"{prefix} {count} payment reminders."))

    def create_legal_stay_reminders(self, *, dry_run: bool = False) -> None:
        from clients.models import MOSApplicationData
        today = timezone.localdate()
        cutoff = today + timedelta(days=45)

        mos_data_list = MOSApplicationData.objects.select_related("client", "case").filter(
            legal_stay_until__isnull=False,
            legal_stay_until__gte=today,
            legal_stay_until__lte=cutoff,
            case__workflow_stage__in=["new_client", "document_collection"],
            case__archived_at__isnull=True,
        )

        count = 0
        for mos in mos_data_list.iterator():
            if mos.legal_stay_until is None:
                continue

            legal_stay_until = mos.legal_stay_until
            due_date = legal_stay_until

            # Weekend adjustment logic
            if due_date.weekday() == 5:  # Saturday
                due_date = due_date - timedelta(days=1)
            elif due_date.weekday() == 6:  # Sunday
                due_date = due_date - timedelta(days=2)

            defaults = {
                "case": mos.case,
                "title": f"Срок подачи по легальному пребыванию: {due_date.strftime('%d.%m.%Y')}",
                "notes": (
                    f"Легальное пребывание до: {mos.legal_stay_until.strftime('%d.%m.%Y')}. "
                    f"Рекомендуемый срок подачи с учетом выходных: {due_date.strftime('%d.%m.%Y')}."
                ),
                "due_date": cast(Any, due_date),
                "is_active": True,
            }

            existing = Reminder.objects.filter(
                client=mos.client,
                case=mos.case,
                reminder_type="legal_stay",
                is_active=True,
            ).first()
            if dry_run:
                if existing is None or any(getattr(existing, key) != value for key, value in defaults.items()):
                    count += 1
                continue

            _reminder, created = Reminder.objects.update_or_create(
                client=mos.client,
                case=mos.case,
                reminder_type="legal_stay",
                is_active=True,
                defaults=defaults,
            )
            if created or existing is None or any(getattr(existing, key) != value for key, value in defaults.items()):
                count += 1

        prefix = "DRY RUN: would upsert" if dry_run else "Upserted"
        self.stdout.write(self.style.SUCCESS(f"{prefix} {count} legal stay reminders."))

    def sync_custom_document_requirement_reminders(self, *, dry_run: bool = False) -> None:
        counts = defaultdict(int)
        for requirement in ClientDocumentRequirement.objects.select_related("client", "case").filter(case__archived_at__isnull=True).iterator():
            outcome = sync_custom_document_requirement_reminder(requirement, dry_run=dry_run)
            counts[outcome] += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Custom requirements synced: upserted={counts['upserted']} deactivated={counts['deactivated']} "
                f"would_upsert={counts['would_upsert']} would_deactivate={counts['would_deactivate']} noop={counts['noop']}"
            )
        )

    def send_legal_stay_notifications(self, *, dry_run: bool = False) -> None:
        from clients.models import MOSApplicationData
        today = timezone.localdate()
        cutoff = today + timedelta(days=45)

        mos_data_list = MOSApplicationData.objects.select_related("client", "case").filter(
            legal_stay_until__isnull=False,
            legal_stay_until__gte=today,
            legal_stay_until__lte=cutoff,
            case__workflow_stage__in=["new_client", "document_collection"],
            case__archived_at__isnull=True,
        )

        if not mos_data_list.exists():
            self.stdout.write("No legal stay expirations within the email window.")
            return

        sent_count = 0
        skipped_count = 0
        for mos in mos_data_list.iterator():
            client = mos.client
            if not client.email:
                skipped_count += 1
                continue

            legal_stay_until = mos.legal_stay_until
            due_date = legal_stay_until

            # Weekend adjustment logic
            if due_date.weekday() == 5:  # Saturday
                due_date = due_date - timedelta(days=1)
            elif due_date.weekday() == 6:  # Sunday
                due_date = due_date - timedelta(days=2)

            if dry_run:
                sent_count += 1
                self.stdout.write(
                    f"DRY RUN: would send legal_stay email client_id={client.pk} "
                    f"legal_stay_until={legal_stay_until} due_date={due_date}"
                )
                continue

            sent = send_legal_stay_email(client, legal_stay_until, due_date)
            if sent:
                sent_count += 1
                logger.info(
                    "notification sent: template=legal_stay_expiring client_id=%s legal_stay_until=%s",
                    client.pk, legal_stay_until,
                )
            else:
                skipped_count += 1
                logger.info(
                    "notification skipped: template=legal_stay_expiring client_id=%s (duplicate or no email)",
                    client.pk,
                )

        prefix = "DRY RUN: would send" if dry_run else "Sent"
        self.stdout.write(f"{prefix} {sent_count} legal-stay emails. skipped={skipped_count}")
