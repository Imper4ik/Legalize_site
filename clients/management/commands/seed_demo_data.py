from __future__ import annotations

from datetime import date, time, timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from clients.constants import DocumentType
from clients.models import Client, Document, DocumentProcessingJob, EmailLog, Payment, Reminder
from clients.services.roles import ensure_predefined_roles

DEMO_PDF_BYTES = b"%PDF-1.4\n% Legalize demo placeholder\n1 0 obj<<>>endobj\n%%EOF\n"


class Command(BaseCommand):
    help = "Seed safe fake demo data for thesis defense and product demos."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required safety flag. Demo data should never be created accidentally.",
        )
        parser.add_argument(
            "--allow-production",
            action="store_true",
            help="Allow running with production settings. Intended only for isolated demo deployments.",
        )
        parser.add_argument(
            "--password",
            default="DemoPass123!",
            help="Password for demo-staff@example.test.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not options["confirm"]:
            raise CommandError("Refusing to seed demo data without --confirm.")

        if getattr(settings, "IS_PRODUCTION", False) and not options["allow_production"]:
            raise CommandError(
                "Refusing to seed demo data in production without --allow-production."
            )

        today = timezone.localdate()
        with transaction.atomic():
            ensure_predefined_roles()
            user = self._upsert_demo_staff(options["password"])

            new_client = self._upsert_client(
                email="demo.new@example.test",
                first_name="Demo",
                last_name="Nowak",
                workflow_stage="document_collection",
                application_purpose="work",
                assigned_staff=user,
            )
            waiting_client = self._upsert_client(
                email="demo.waiting@example.test",
                first_name="Alex",
                last_name="Kowalski",
                workflow_stage="waiting_decision",
                application_purpose="work",
                assigned_staff=user,
                fingerprints_date=today - timedelta(days=35),
                fingerprints_time=time(10, 30),
                fingerprints_location="Mazowiecki Urzad Wojewodzki, demo room",
            )
            self._upsert_client(
                email="demo.decision@example.test",
                first_name="Maria",
                last_name="Zielinska",
                workflow_stage="decision_received",
                application_purpose="study",
                status="approved",
                assigned_staff=user,
                decision_date=today - timedelta(days=2),
            )

            self._ensure_document(
                client=new_client,
                document_type=DocumentType.PASSPORT.value,
                filename="demo-passport.pdf",
                expiry_date=today + timedelta(days=365),
                verified=True,
            )
            self._ensure_document(
                client=waiting_client,
                document_type=DocumentType.PASSPORT.value,
                filename="demo-expired-passport.pdf",
                expiry_date=today - timedelta(days=5),
                verified=False,
            )
            ocr_doc = self._ensure_document(
                client=waiting_client,
                document_type=DocumentType.WEZWANIE.value,
                filename="demo-wezwanie-awaiting-review.pdf",
                awaiting_confirmation=True,
                ocr_status="success",
                parsed_data={
                    "full_name": "Alex Kowalski",
                    "case_number": "WSC-II-P.DEMO.2026",
                    "fingerprints_date": today.isoformat(),
                    "fingerprints_date_display": today.strftime("%d.%m.%Y"),
                    "fingerprints_time": "10:30",
                    "fingerprints_location": "Mazowiecki Urzad Wojewodzki, demo room",
                    "ticket_number": "D1",
                    "list_name": "Lista D",
                    "application_status_code": "P",
                    "required_documents": [DocumentType.PHOTOS.value],
                },
            )
            DocumentProcessingJob.objects.update_or_create(
                document=ocr_doc,
                job_type=DocumentProcessingJob.JOB_TYPE_WEZWANIE_OCR,
                defaults={
                    "created_by": user,
                    "status": DocumentProcessingJob.STATUS_COMPLETED,
                    "source_file_name": "demo",
                    "requires_confirmation": True,
                    "completed_at": timezone.now(),
                },
            )

            Payment.objects.update_or_create(
                client=waiting_client,
                service_description="work_service",
                defaults={
                    "total_amount": Decimal("2500.00"),
                    "amount_paid": Decimal("1000.00"),
                    "status": "partial",
                    "due_date": today - timedelta(days=7),
                },
            )
            Reminder.objects.update_or_create(
                client=waiting_client,
                title="Demo: waiting after fingerprints",
                defaults={
                    "reminder_type": "other",
                    "notes": "Safe demo reminder for the thesis workflow.",
                    "due_date": today,
                    "is_active": True,
                },
            )
            EmailLog.objects.update_or_create(
                idempotency_key="demo:missing-documents",
                defaults={
                    "client": waiting_client,
                    "subject": "Demo missing documents",
                    "body": "Safe demo email body without real PII.",
                    "recipients": waiting_client.email,
                    "template_type": "missing_documents",
                    "delivery_status": EmailLog.DELIVERY_STATUS_SENT,
                    "sent_by": user,
                },
            )

        self.stdout.write(self.style.SUCCESS("Demo data created/updated."))
        self.stdout.write("Login: demo-staff@example.test")
        self.stdout.write(f"Password: {options['password']}")

    def _upsert_demo_staff(self, password: str) -> Any:
        user_model = get_user_model()
        user, _created = user_model.objects.update_or_create(
            email="demo-staff@example.test",
            defaults={"is_staff": True, "is_active": True},
        )
        user.set_password(password)
        user.save(update_fields=["password", "is_staff", "is_active"])
        user.groups.add(Group.objects.get(name="Staff"))
        return user

    def _upsert_client(self, *, email: str, first_name: str, last_name: str, **defaults: Any) -> Client:
        payload = {
            "first_name": first_name,
            "last_name": last_name,
            "citizenship": "DEMO",
            "phone": "+48000000000",
            "language": "en",
            **defaults,
        }
        client, _created = Client.objects.update_or_create(email=email, defaults=payload)
        return client

    def _ensure_document(
        self,
        *,
        client: Client,
        document_type: str,
        filename: str,
        expiry_date: date | None = None,
        verified: bool = False,
        awaiting_confirmation: bool = False,
        ocr_status: str = "skipped",
        parsed_data: dict[str, Any] | None = None,
    ) -> Document:
        document, created = Document.objects.get_or_create(
            client=client,
            document_type=document_type,
            defaults={
                "expiry_date": expiry_date,
                "verified": verified,
                "awaiting_confirmation": awaiting_confirmation,
                "ocr_status": ocr_status,
                "parsed_data": parsed_data,
            },
        )
        if created or not document.file:
            document.file.save(filename, ContentFile(DEMO_PDF_BYTES), save=False)
        document.expiry_date = expiry_date
        document.verified = verified
        document.awaiting_confirmation = awaiting_confirmation
        document.ocr_status = ocr_status
        document.parsed_data = parsed_data or {}
        document.save()
        return document
