from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone
from typing import Any

from clients.constants import DocumentType
from clients.models import DocumentProcessingJob, EmailLog, Reminder
from clients.services.zus import missing_zus_months
from clients.demo.demo_factory import (
    create_demo_client,
    create_demo_payment,
    create_demo_document,
    create_demo_onboarding_session,
    create_demo_activity,
    create_demo_staff_audit,
)


def prepare_demo_scenarios(staff_user: Any) -> list[dict[str, Any]]:
    # Clear any previous demo data first to prevent duplicates
    from clients.demo.demo_cleanup import cleanup_demo_data
    cleanup_demo_data()

    results = []

    # 1. Jan Kowalski — work card — all documents OK
    jan = create_demo_client(
        email="jan.kowalski@example.demo",
        first_name="Jan",
        last_name="Kowalski",
        purpose="work",
        workflow_stage="application_submitted",
        language="pl",
        assigned_staff=staff_user,
    )
    create_demo_payment(jan, status="paid")
    token_jan, _ = create_demo_onboarding_session(jan)

    # Add all required work documents
    docs_jan = [
        (DocumentType.PHOTOS.value, "photos.pdf"),
        (DocumentType.PASSPORT.value, "passport.pdf"),
        (DocumentType.WORK_PERMIT_FEE.value, "fee.pdf"),
        (DocumentType.ZALACZNIK_NR_1.value, "zalacznik1.pdf"),
        (DocumentType.WORK_PERMISSION.value, "permission.pdf"),
        (DocumentType.EMPLOYMENT_CONTRACT.value, "contract.pdf"),
    ]
    for doc_type, filename in docs_jan:
        create_demo_document(jan, doc_type=doc_type, verified=True, filename=filename)

    # ZUS RCA correct monthly payments
    create_demo_document(
        jan,
        doc_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
        verified=True,
        zus_period_month=date(2026, 4, 1),
        filename="zus_rca_april.pdf",
    )

    create_demo_activity(jan, event_type="client_created", summary="Демо-клиент создан", actor=staff_user)
    create_demo_activity(jan, event_type="payment_created", summary="Платёж получен и подтвержден", actor=staff_user)
    create_demo_activity(jan, event_type="document_verified", summary="Все обязательные документы проверены и одобрены", actor=staff_user)

    results.append({"client": jan, "token": token_jan, "scenario": "Jan Kowalski (All Documents OK)"})

    # 2. Anna Nowak — missing documents
    anna = create_demo_client(
        email="anna.nowak@example.demo",
        first_name="Anna",
        last_name="Nowak",
        purpose="work",
        workflow_stage="document_collection",
        language="pl",
        assigned_staff=staff_user,
    )
    create_demo_payment(anna, status="paid")
    token_anna, _ = create_demo_onboarding_session(anna)

    # Upload only some documents
    create_demo_document(anna, doc_type=DocumentType.PHOTOS.value, verified=True, filename="photos.pdf")
    create_demo_document(anna, doc_type=DocumentType.PASSPORT.value, verified=True, filename="passport.pdf")

    create_demo_activity(anna, event_type="client_created", summary="Демо-клиент создан", actor=staff_user)
    create_demo_activity(anna, event_type="document_uploaded", summary="Загружен паспорт и фотографии", actor=staff_user)

    results.append({"client": anna, "token": token_anna, "scenario": "Anna Nowak (Missing Documents)"})

    # 3. Daria Testowa — ZUS RCA wrong month
    daria = create_demo_client(
        email="daria.testowa@example.demo",
        first_name="Daria",
        last_name="Testowa",
        purpose="work",
        workflow_stage="waiting_decision",
        language="pl",
        assigned_staff=staff_user,
    )
    # fingerprints on Feb 10, expected ZUS RCA for March and April (given today is May 15)
    daria.fingerprints_date = date(2026, 2, 10)
    daria.save(update_fields=["fingerprints_date"])

    create_demo_payment(daria, status="paid")
    token_daria, _ = create_demo_onboarding_session(daria)

    # Upload ZUS RCA for January (wrong month)
    create_demo_document(
        daria,
        doc_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
        verified=True,
        zus_period_month=date(2026, 1, 1),
        filename="zus_january_wrong.pdf",
    )

    # Simulate sending email log for wrong period
    EmailLog.objects.create(
        client=daria,
        subject="ZUS RCA za nieprawidłowy okres",
        body="Dzień dobry Daria Testowa,\n\nw przesłanych dokumentach brakuje prawidłowego dokumentu ZUS RCA za wymagany okres.\nProsimy o przesłanie poprawnego dokumentu przez portal klienta.\n\n[Otwórz portal klienta]",
        recipients=daria.email,
        template_type="zus_rca_wrong_period",
        delivery_status="sent",
        is_demo_data=True,
    )

    create_demo_activity(daria, event_type="client_created", summary="Демо-клиент создан", actor=staff_user)
    create_demo_activity(daria, event_type="document_uploaded", summary="Загружен ZUS RCA за январь (ожидались март и апрель)", actor=staff_user)
    create_demo_activity(daria, event_type="email_sent", summary="Отправлено уведомление о неверном периоде ZUS RCA", actor=staff_user)

    results.append({"client": daria, "token": token_daria, "scenario": "Daria Testowa (ZUS RCA Wrong Month)"})

    # 4. Ivan Demo — wezwanie + OCR + deadline
    ivan = create_demo_client(
        email="ivan.demo@example.demo",
        first_name="Ivan",
        last_name="Demo",
        purpose="work",
        workflow_stage="document_collection",
        language="ru",
        assigned_staff=staff_user,
    )
    create_demo_payment(ivan, status="paid")
    token_ivan, _ = create_demo_onboarding_session(ivan)

    # Create wezwanie document awaiting confirmation
    wezwanie = create_demo_document(
        ivan,
        doc_type=DocumentType.WEZWANIE.value,
        verified=False,
        awaiting_confirmation=True,
        ocr_status="completed",
        filename="wezwanie_scan.pdf",
        parsed_data={
            "detected_case_number": "WSC-IV-S.12345.DEMO.2026",
            "detected_deadline": "2026-06-28",
            "detected_required_documents": ["ZUS RCA", "employment_contract"],
            "confidence": 0.85
        }
    )

    # Create DocumentProcessingJob
    DocumentProcessingJob.objects.create(
        document=wezwanie,
        job_type=DocumentProcessingJob.JOB_TYPE_WEZWANIE_OCR,
        status=DocumentProcessingJob.STATUS_COMPLETED,
        source_file_name="wezwanie_scan.pdf",
        requires_confirmation=True,
        is_demo_data=True,
    )

    # Create a draft reminder/deadline task
    Reminder.objects.create(
        client=ivan,
        document=wezwanie,
        reminder_type="document",
        due_date=date(2026, 6, 28),
        title="Дедлайн по везванию: донести ZUS RCA и трудовой договор",
        notes="Требуется подтвердить дедлайн на основе OCR.",
        is_active=False,  # inactive until staff confirmation
    )

    create_demo_activity(ivan, event_type="client_created", summary="Демо-клиент создан", actor=staff_user)
    create_demo_activity(ivan, event_type="document_uploaded", summary="Загружено везвание (судебное требование)", actor=staff_user)
    create_demo_activity(ivan, event_type="task_created", summary="Запущено распознавание OCR для извлечения дедлайна и требований", actor=staff_user)

    results.append({"client": ivan, "token": token_ivan, "scenario": "Ivan Demo (Wezwanie + OCR + Deadline)"})

    # 5. Maria Student — waiting after fingerprints
    maria = create_demo_client(
        email="maria.student@example.demo",
        first_name="Maria",
        last_name="Student",
        purpose="study",
        workflow_stage="waiting_decision",
        language="ru",
        assigned_staff=staff_user,
    )
    maria.fingerprints_date = date(2026, 5, 20)
    maria.save(update_fields=["fingerprints_date"])

    create_demo_payment(maria, status="paid")
    token_maria, _ = create_demo_onboarding_session(maria)

    # Add all study documents verified
    docs_maria = [
        (DocumentType.PHOTOS.value, "photos.pdf"),
        (DocumentType.PASSPORT.value, "passport.pdf"),
        (DocumentType.STUDY_APPLICATION_FEE.value, "fee.pdf"),
        (DocumentType.ENROLLMENT_CERTIFICATE.value, "enrollment.pdf"),
        (DocumentType.TUITION_FEE_STATEMENT.value, "tuition_statement.pdf"),
        (DocumentType.TUITION_FEE_PROOF.value, "tuition_proof.pdf"),
        (DocumentType.GRADES.value, "grades.pdf"),
        (DocumentType.HEALTH_INSURANCE.value, "insurance.pdf"),
        (DocumentType.ADDRESS_PROOF.value, "address.pdf"),
        (DocumentType.FINANCIAL_PROOF.value, "financial.pdf"),
    ]
    for doc_type, filename in docs_maria:
        create_demo_document(maria, doc_type=doc_type, verified=True, filename=filename)

    create_demo_activity(maria, event_type="client_created", summary="Демо-клиент создан", actor=staff_user)
    create_demo_activity(maria, event_type="workflow_changed", summary="Сданы отпечатки пальцев, дело переведено в статус ожидания решения", actor=staff_user)

    results.append({"client": maria, "token": token_maria, "scenario": "Maria Student (Waiting after Fingerprints)"})

    create_demo_staff_audit(staff_user, event_type="demo_center_run", summary="Набор 5-минутного демо успешно подготовлен")

    return results
