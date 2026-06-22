from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from clients.constants import DocumentType
from clients.models import Client, ClientOnboardingSession, Document, Payment
from clients.services.onboarding_tokens import generate_onboarding_token
from clients.services.roles import ensure_predefined_roles

TEST_EMAIL_DOMAIN = "@example.test"
TEST_USER_PREFIX = "test-center-"
TEST_USER_CREDENTIAL = f"{TEST_USER_PREFIX}pass"


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}{TEST_EMAIL_DOMAIN}"


def create_test_client(
    *,
    email: str | None = None,
    first_name: str = "Test",
    last_name: str = "Client",
    purpose: str = "work",
    workflow_stage: str = "document_collection",
    language: str = "en",
    assigned_staff: object | None = None,
) -> Client:
    return Client.objects.create(
        first_name=first_name,
        last_name=last_name,
        email=email or unique_email("client"),
        phone="+48000000000",
        application_purpose=purpose,
        workflow_stage=workflow_stage,
        language=language,
        assigned_staff=assigned_staff,
        is_test_data=True,
    )


def create_test_user(
    *,
    role: str = "Staff",
    email: str | None = None,
    is_superuser: bool = False,
):
    ensure_predefined_roles()
    user_model = get_user_model()
    user = user_model.objects.create_user(
        email=email or unique_email(f"{TEST_USER_PREFIX}{role.lower()}"),
        password=TEST_USER_CREDENTIAL,
        is_staff=True,
        is_superuser=is_superuser,
        is_active=True,
    )
    if role:
        user.groups.add(Group.objects.get(name=role))
    return user


def create_client_user(*, email: str | None = None):
    user_model = get_user_model()
    return user_model.objects.create_user(
        email=email or unique_email(f"{TEST_USER_PREFIX}client"),
        password=TEST_USER_CREDENTIAL,
        is_staff=False,
        is_active=True,
    )


def create_paid_payment(client: Client) -> Payment:
    return Payment.objects.create(
        client=client,
        service_description="work_service",
        total_amount=Decimal("1000.00"),
        amount_paid=Decimal("1000.00"),
        status="paid",
        payment_method="transfer",
        payment_date=timezone.localdate(),
        is_test_data=True,
    )


def create_pending_payment(client: Client, *, service_description: str = "work_service") -> Payment:
    return Payment.objects.create(
        client=client,
        service_description=service_description,
        total_amount=Decimal("1000.00"),
        amount_paid=Decimal("0.00"),
        status="pending",
        due_date=timezone.localdate() - timedelta(days=1),
        is_test_data=True,
    )


def build_pdf_upload(name: str = "test.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(
        name,
        b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n",
        content_type="application/pdf",
    )


def create_test_document(
    client: Client,
    *,
    doc_type: str = DocumentType.PASSPORT.value,
    verified: bool = False,
    awaiting_confirmation: bool = False,
    ocr_status: str = "skipped",
    zus_period_month: date | None = None,
    expiry_date: date | None = None,
    filename: str = "test.pdf",
    case: Any | None = None,
) -> Document:
    return Document.objects.create(
        client=client,
        case=case,
        document_type=doc_type,
        file=build_pdf_upload(filename),
        verified=verified,
        awaiting_confirmation=awaiting_confirmation,
        ocr_status=ocr_status,
        zus_period_month=zus_period_month,
        expiry_date=expiry_date,
        is_test_data=True,
    )


def create_onboarding_session(client: Client, *, days: int = 7) -> tuple[str, ClientOnboardingSession]:
    raw_token, token_hash = generate_onboarding_token()
    session = ClientOnboardingSession.objects.create(
        client=client,
        payment=client.payments.filter(status__in=["paid", "partial"]).first(),
        token_hash=token_hash,
        status="created",
        expires_at=timezone.now() + timedelta(days=days),
    )
    return raw_token, session
