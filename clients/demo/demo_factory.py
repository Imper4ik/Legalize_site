from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from clients.constants import DocumentType
from clients.models import (
    Client,
    ClientActivity,
    ClientOnboardingSession,
    Document,
    Payment,
    StaffAuditEvent,
)

DEMO_EMAIL_DOMAIN = "@example.demo"


def unique_demo_email(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}{DEMO_EMAIL_DOMAIN}"


def create_demo_client(
    *,
    email: str | None = None,
    first_name: str = "Demo",
    last_name: str = "Client",
    purpose: str = "work",
    workflow_stage: str = "new_client",
    language: str = "pl",
    assigned_staff: Any = None,  # noqa: ARG001 - accepted but ignored; staff is not assigned to clients (spec §2)
) -> Client:
    return Client.objects.create(
        first_name=first_name,
        last_name=last_name,
        email=email or unique_demo_email("demo-client"),
        phone="+48777888999",
        application_purpose=purpose,
        workflow_stage=workflow_stage,
        language=language,
        is_demo_data=True,
        is_test_data=False,
    )


def _single_case_of(client: Client):
    """Explicit case for demo records (shim-exit, spec §4)."""
    from clients.services.cases import resolve_single_active_case

    return resolve_single_active_case(client)


def create_demo_payment(
    client: Client,
    *,
    service_description: str = "work_service",
    total_amount: Decimal = Decimal("1500.00"),
    amount_paid: Decimal = Decimal("1500.00"),
    status: str = "paid",
    due_date: date | None = None,
) -> Payment:
    return Payment.objects.create(
        client=client,
        case=_single_case_of(client),
        service_description=service_description,
        total_amount=total_amount,
        amount_paid=amount_paid,
        status=status,
        payment_method="transfer" if status == "paid" else None,
        payment_date=timezone.localdate() if status == "paid" else None,
        due_date=due_date or (timezone.localdate() + timedelta(days=14)),
        is_demo_data=True,
        is_test_data=False,
    )


def build_demo_pdf(name: str = "demo.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(
        name,
        b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n",
        content_type="application/pdf",
    )


def create_demo_document(
    client: Client,
    *,
    doc_type: str = DocumentType.PASSPORT.value,
    verified: bool = False,
    awaiting_confirmation: bool = False,
    ocr_status: str = "skipped",
    zus_period_month: date | None = None,
    expiry_date: date | None = None,
    filename: str = "demo-document.pdf",
    parsed_data: dict[str, Any] | None = None,
) -> Document:
    return Document.objects.create(
        client=client,
        case=_single_case_of(client),
        document_type=doc_type,
        file=build_demo_pdf(filename),
        verified=verified,
        awaiting_confirmation=awaiting_confirmation,
        ocr_status=ocr_status,
        zus_period_month=zus_period_month,
        expiry_date=expiry_date,
        parsed_data=parsed_data or {},
        is_demo_data=True,
        is_test_data=False,
    )


def get_demo_token_for_client(client: Client) -> str:
    import hashlib

    from django.conf import settings
    h = hashlib.sha256(f"{client.pk}-{settings.SECRET_KEY}".encode()).hexdigest()[:16]
    return f"demo-token-{client.pk}-{h}"


def create_demo_onboarding_session(
    client: Client,
    *,
    days: int = 30,
) -> tuple[str, ClientOnboardingSession]:
    from clients.services.onboarding_tokens import hash_onboarding_token
    raw_token = get_demo_token_for_client(client)
    token_hash = hash_onboarding_token(raw_token)
    session = ClientOnboardingSession.objects.create(
        client=client,
        case=_single_case_of(client),
        payment=client.payments.filter(status__in=["paid", "partial"]).first(),
        token_hash=token_hash,
        status="active",
        expires_at=timezone.now() + timedelta(days=days),
        is_demo_data=True,
    )
    return raw_token, session


def create_demo_activity(
    client: Client,
    *,
    event_type: str,
    summary: str,
    actor: Any = None,
    metadata: dict[str, Any] | None = None,
) -> ClientActivity:
    return ClientActivity.objects.create(
        client=client,
        event_type=event_type,
        summary=summary,
        actor=actor,
        metadata=metadata or {},
        is_demo_data=True,
    )


def create_demo_staff_audit(
    actor: Any,
    *,
    event_type: str,
    summary: str,
    metadata: dict[str, Any] | None = None,
) -> StaffAuditEvent:
    return StaffAuditEvent.objects.create(
        actor=actor,
        target=actor,
        event_type=event_type,
        summary=summary,
        metadata=metadata or {},
        is_demo_data=True,
    )
