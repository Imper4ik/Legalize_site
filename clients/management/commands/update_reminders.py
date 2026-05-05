from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from clients.models import Client, Document, Payment, Reminder
from clients.services.notifications import (
    _get_missing_documents_context,
    send_expiring_documents_email,
    send_missing_documents_email,
)
from clients.services.zus import format_zus_months, missing_zus_months


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Create daily document, payment, ZUS RCA, and missing-document reminders safely."

    SECTIONS = ("payments", "documents", "zus", "missing-docs")

    def add_arguments(self, parser):
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

    def handle(self, *args, **options):
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
                self.check_zus_rca_missing_months()

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

            self.stdout.write(self.style.SUCCESS("--- Reminder update completed ---"))
        except Exception as exc:
            logger.exception("update_reminders failed")
            self.stdout.write(self.style.ERROR(f"update_reminders failed: {exc}"))
            raise CommandError("update_reminders failed") from exc

    def send_missing_document_notifications(self, *, dry_run: bool = False):
        today = timezone.localdate()
        clients = Client.objects.filter(
            workflow_stage="waiting_decision",
            fingerprints_date__isnull=False,
            fingerprints_date__lte=today,
            decision_date__isnull=True,
        ).exclude(email="")

        sent_count = 0
        skipped_count = 0
        iso_year, iso_week, _iso_weekday = today.isocalendar()
        for client in clients.iterator():
            weekly_key = f"waiting_decision_missing_docs:{client.pk}:{iso_year}-W{iso_week:02d}"
            if dry_run:
                sent = 1 if _get_missing_documents_context(client) else 0
            else:
                sent = send_missing_documents_email(client, weekly_key=weekly_key)

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

    def check_zus_rca_missing_months(self):
        today = timezone.localdate()
        clients = Client.objects.filter(
            workflow_stage="waiting_decision",
            fingerprints_date__isnull=False,
            fingerprints_date__lte=today,
            decision_date__isnull=True,
        )
        affected = 0
        for client in clients.iterator():
            missing = missing_zus_months(client, today=today)
            if missing:
                affected += 1
                message = f"ZUS RCA missing months: client_id={client.pk}, months={format_zus_months(missing)}"
                logger.info(message)
                self.stdout.write(message)
        if affected == 0:
            self.stdout.write("ZUS RCA missing months logs: none.")

    def send_expiring_document_notifications(self, *, dry_run: bool = False):
        today = timezone.localdate()
        cutoff = today + timedelta(days=7)
        expiring_docs = Document.objects.select_related("client").filter(
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

    def create_document_reminders(self, *, dry_run: bool = False):
        today = timezone.localdate()
        reminder_period_end = today + timedelta(days=30)
        expiring_email_cutoff = today + timedelta(days=7)

        expiring_docs = Document.objects.select_related("client").filter(
            expiry_date__isnull=False,
            expiry_date__gte=today,
            expiry_date__lte=reminder_period_end,
            reminder__isnull=True,
        )

        if not expiring_docs.exists():
            self.stdout.write("No expiring documents need reminders.")
            return

        expiring_soon: dict[int, list[Document]] = defaultdict(list)
        count = 0
        for document in expiring_docs.iterator():
            count += 1
            if dry_run:
                continue

            Reminder.objects.create(
                client=document.client,
                document=document,
                title=f"Document expires: {document.display_name}",
                notes=f"Document for client_id={document.client_id} expires on {document.expiry_date:%d.%m.%Y}.",
                due_date=document.expiry_date,
                reminder_type="document",
            )
            if document.expiry_date <= expiring_email_cutoff:
                expiring_soon[document.client_id].append(document)

        prefix = "DRY RUN: would create" if dry_run else "Created"
        self.stdout.write(self.style.SUCCESS(f"{prefix} {count} document reminders."))

        if dry_run:
            return

        for documents in expiring_soon.values():
            send_expiring_documents_email(documents[0].client, documents)

    def create_payment_reminders(self, *, dry_run: bool = False):
        today = timezone.localdate()
        due_payments = Payment.objects.select_related("client").filter(
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
                    "title": f"Payment overdue: {payment.get_service_description_display()}",
                    "notes": (
                        f"Payment total={payment.total_amount}; amount_due={payment.amount_due}; "
                        f"client_id={payment.client_id}."
                    ),
                    "due_date": payment.due_date,
                    "reminder_type": "payment",
                    "is_active": True,
                },
            )

        prefix = "DRY RUN: would create" if dry_run else "Created"
        self.stdout.write(self.style.SUCCESS(f"{prefix} {count} payment reminders."))
