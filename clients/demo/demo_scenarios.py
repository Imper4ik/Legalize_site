from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from clients.constants import DocumentType
from clients.demo.demo_factory import (
    create_demo_activity,
    create_demo_client,
    create_demo_document,
    create_demo_onboarding_session,
    create_demo_payment,
    create_demo_staff_audit,
)
from clients.models import DocumentProcessingJob, EmailLog, MOSApplicationData, StaffTask


def prepare_demo_scenarios(staff_user: Any) -> list[dict[str, Any]]:
    # Clear any previous demo data first to prevent duplicates
    from clients.demo.demo_cleanup import cleanup_demo_data
    cleanup_demo_data()

    results = []

    # 1. Идеальный клиент (Jan Kowalski) — все документы приняты, заявление готово, оплачен
    jan = create_demo_client(
        email="jan.kowalski@example.demo",
        first_name="Jan",
        last_name="Kowalski",
        purpose="work",
        workflow_stage="mos_package_ready",
        language="pl",
        assigned_staff=staff_user,
    )
    MOSApplicationData.objects.update_or_create(
        client=jan,
        defaults={
            "status": "client_completed",
            "mos_purpose": "work",
        },
    )
    create_demo_payment(jan, status="paid")
    token_jan, _ = create_demo_onboarding_session(jan)

    # Добавляем все обязательные документы
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

    # ZUS RCA correct
    create_demo_document(
        jan,
        doc_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
        verified=True,
        zus_period_month=date(2026, 4, 1),
        filename="zus_rca_april.pdf",
    )

    create_demo_activity(jan, event_type="client_created", summary="Демо-клиент создан", actor=staff_user)
    create_demo_activity(jan, event_type="document_verified", summary="Все обязательные документы проверены и одобрены", actor=staff_user)
    results.append({"client": jan, "token": token_jan, "scenario": "1. Идеальный клиент (All Documents OK)"})

    # 2. Не хватает документов (Anna Nowak) — нет договора, ZUS RCA, подтверждения адреса
    anna = create_demo_client(
        email="anna.nowak@example.demo",
        first_name="Anna",
        last_name="Nowak",
        purpose="work",
        workflow_stage="document_collection",
        language="pl",
        assigned_staff=staff_user,
    )
    anna.family_role = "family_spouse"
    anna.save(update_fields=["family_role"])
    MOSApplicationData.objects.update_or_create(
        client=anna,
        defaults={
            "status": "client_filling",
            "mos_purpose": "work",
        },
    )
    create_demo_payment(anna, status="paid")
    token_anna, _ = create_demo_onboarding_session(anna)

    # Загружаем только часть документов
    create_demo_document(anna, doc_type=DocumentType.PHOTOS.value, verified=True, filename="photos.pdf")
    create_demo_document(anna, doc_type=DocumentType.PASSPORT.value, verified=True, filename="passport.pdf")
    create_demo_document(anna, doc_type=DocumentType.WORK_PERMIT_FEE.value, verified=True, filename="fee.pdf")
    create_demo_document(anna, doc_type=DocumentType.ZALACZNIK_NR_1.value, verified=True, filename="zalacznik1.pdf")
    create_demo_document(anna, doc_type=DocumentType.WORK_PERMISSION.value, verified=True, filename="permission.pdf")

    # Договор (employment_contract), ZUS RCA, подтверждение адреса (address_proof) отсутствуют
    create_demo_activity(anna, event_type="client_created", summary="Демо-клиент создан", actor=staff_user)
    results.append({"client": anna, "token": token_anna, "scenario": "2. Не хватает документов (Missing contract, ZUS RCA, address proof)"})

    # 3. Новая подача с номером дела (Piotr Wisniewski) — статус: подано, дата и номер дела есть, подтверждение загружено
    piotr = create_demo_client(
        email="piotr.wisniewski@example.demo",
        first_name="Piotr",
        last_name="Wisniewski",
        purpose="work",
        workflow_stage="submitted_in_mos",
        language="pl",
        assigned_staff=staff_user,
    )
    MOSApplicationData.objects.update_or_create(
        client=piotr,
        defaults={
            "status": "client_completed",
            "mos_purpose": "work",
            "new_residence_card_application_status": "yes",
            "new_residence_card_case_number": "WSC-99999-2026",
            "new_residence_card_submitted_at": date(2026, 6, 1),
            "new_residence_card_comment": "Подано через почту, получен штамп",
        },
    )
    create_demo_payment(piotr, status="paid")
    token_piotr, _ = create_demo_onboarding_session(piotr)

    # Подтверждение подачи загружено
    create_demo_document(
        piotr,
        doc_type=DocumentType.NEW_RESIDENCE_CARD_APPLICATION_CONFIRMATION.value,
        verified=True,
        filename="confirmation_stamp.pdf"
    )

    create_demo_activity(piotr, event_type="client_created", summary="Демо-клиент создан", actor=staff_user)
    results.append({"client": piotr, "token": token_piotr, "scenario": "3. Новая подача с номером дела (Submitted with Case Number)"})

    # 4. Новая подача без номера дела (Elena Petrova) — статус: подано, дата есть, подтверждение загружено, номер пуст. Авто-задача: запросить номер дела
    elena = create_demo_client(
        email="elena.petrova@example.demo",
        first_name="Elena",
        last_name="Petrova",
        purpose="work",
        workflow_stage="submitted_in_mos",
        language="ru",
        assigned_staff=staff_user,
    )
    MOSApplicationData.objects.update_or_create(
        client=elena,
        defaults={
            "status": "client_completed",
            "mos_purpose": "work",
            "new_residence_card_application_status": "yes",
            "new_residence_card_case_number": "",
            "new_residence_card_submitted_at": date(2026, 6, 10),
        },
    )
    create_demo_payment(elena, status="paid")
    token_elena, _ = create_demo_onboarding_session(elena)

    # Подтверждение подачи загружено
    create_demo_document(
        elena,
        doc_type=DocumentType.NEW_RESIDENCE_CARD_APPLICATION_CONFIRMATION.value,
        verified=True,
        filename="confirmation_no_number.pdf"
    )

    # Авто-задача: запросить номер дела у клиента
    StaffTask.objects.create(
        client=elena,
        title="Запросить номер дела у клиента (Elena Petrova)",
        description="Клиент указал подачу на карту, но оставил номер дела пустым.",
        status="todo",
        task_type="case_number_missing",
        is_auto_created=True,
    )

    create_demo_activity(elena, event_type="client_created", summary="Демо-клиент создан", actor=staff_user)
    results.append({"client": elena, "token": token_elena, "scenario": "4. Новая подача без номера дела (Submitted without Case Number)"})

    # 5. После отпечатков без решения (Dmitry Sidorov) — отпечатки сданы 4 месяца назад, решения нет. Alert: проверить статус
    dmitry = create_demo_client(
        email="dmitry.sidorov@example.demo",
        first_name="Dmitry",
        last_name="Sidorov",
        purpose="work",
        workflow_stage="fingerprints",
        language="ru",
        assigned_staff=staff_user,
    )
    dmitry.fingerprints_date = date.today() - timedelta(days=120)
    dmitry.save(update_fields=["fingerprints_date"])

    MOSApplicationData.objects.update_or_create(
        client=dmitry,
        defaults={
            "status": "client_completed",
            "mos_purpose": "work",
        },
    )
    create_demo_payment(dmitry, status="paid")
    token_dmitry, _ = create_demo_onboarding_session(dmitry)

    # Все документы по делу
    docs_dmitry = [
        (DocumentType.PHOTOS.value, "photos.pdf"),
        (DocumentType.PASSPORT.value, "passport.pdf"),
        (DocumentType.ZALACZNIK_NR_1.value, "zalacznik1.pdf"),
        (DocumentType.EMPLOYMENT_CONTRACT.value, "contract.pdf"),
    ]
    for doc_type, filename in docs_dmitry:
        create_demo_document(dmitry, doc_type=doc_type, verified=True, filename=filename)

    create_demo_activity(dmitry, event_type="client_created", summary="Демо-клиент создан", actor=staff_user)
    results.append({"client": dmitry, "token": token_dmitry, "scenario": "5. После отпечатков без решения (Fingerprints 4 months ago, no decision)"})

    # 6. Плохой документ (Aliaksandr Ivanov) — загружен паспорт, статус: отклонён, комментарий: фото размыто
    aliaksandr = create_demo_client(
        email="aliaksandr.ivanov@example.demo",
        first_name="Aliaksandr",
        last_name="Ivanov",
        purpose="work",
        workflow_stage="document_collection",
        language="ru",
        assigned_staff=staff_user,
    )
    MOSApplicationData.objects.update_or_create(
        client=aliaksandr,
        defaults={
            "status": "client_filling",
            "mos_purpose": "work",
        },
    )
    create_demo_payment(aliaksandr, status="paid")
    token_aliaksandr, _ = create_demo_onboarding_session(aliaksandr)

    # Плохой документ
    create_demo_document(
        aliaksandr,
        doc_type=DocumentType.PASSPORT.value,
        verified=False,
        filename="passport_blurry.pdf",
    )
    # Установим причину отклонения прямо в документе
    passport_doc = aliaksandr.documents.filter(document_type=DocumentType.PASSPORT.value).first()
    passport_doc.rejection_reason = "Фото паспорта размыто, не видны буквы серии и номера. Пожалуйста, переделайте фото при хорошем освещении."
    passport_doc.save(update_fields=["rejection_reason"])

    # Создадим запись в очереди OCR для полноты сценария
    DocumentProcessingJob.objects.create(
        document=passport_doc,
        job_type=DocumentProcessingJob.JOB_TYPE_PASSPORT_OCR,
        status=DocumentProcessingJob.STATUS_FAILED,
        source_file_name="passport_blurry.pdf",
        error_message="OCR failed: image quality too low (blurry)",
        is_demo_data=True,
    )

    # Создадим авто-задачу
    StaffTask.objects.create(
        client=aliaksandr,
        title="Проверить отклонённый документ: passport",
        description="У клиента Aliaksandr Ivanov отклонён документ passport. Причина: Фото паспорта размыто.",
        status="todo",
        task_type="document_review",
        is_auto_created=True,
    )

    # Имитация отправки email-лога
    EmailLog.objects.create(
        client=aliaksandr,
        subject="Отклонённый документ: passport",
        body="Действие требуется: фото паспорта размыто.",
        recipients=aliaksandr.email,
        is_demo_data=True,
    )

    create_demo_activity(aliaksandr, event_type="client_created", summary="Демо-клиент создан", actor=staff_user)
    results.append({"client": aliaksandr, "token": token_aliaksandr, "scenario": "6. Плохой документ (Passport rejected, blurry photo)"})

    # 7. ZUS RCA устарел (Volodymyr Shevchenko) — последний ZUS за 04.2026, требуется 05.2026. Задача: запросить новый
    volodymyr = create_demo_client(
        email="volodymyr.shevchenko@example.demo",
        first_name="Volodymyr",
        last_name="Shevchenko",
        purpose="work",
        workflow_stage="fingerprints",
        language="ru",
        assigned_staff=staff_user,
    )
    volodymyr.fingerprints_date = date.today() - timedelta(days=60)
    volodymyr.save(update_fields=["fingerprints_date"])

    MOSApplicationData.objects.update_or_create(
        client=volodymyr,
        defaults={
            "status": "client_completed",
            "mos_purpose": "work",
        },
    )
    create_demo_payment(volodymyr, status="paid")
    token_volodymyr, _ = create_demo_onboarding_session(volodymyr)

    # Устаревший ZUS RCA
    create_demo_document(
        volodymyr,
        doc_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
        verified=True,
        zus_period_month=date(2026, 4, 1),
        filename="zus_rca_april.pdf",
    )

    # Задача: запросить новый ZUS RCA за май 2026
    StaffTask.objects.create(
        client=volodymyr,
        title="Запросить новый ZUS RCA за май 2026",
        description="Последний ZUS RCA у Volodymyr Shevchenko за апрель 2026. Требуется обновление.",
        status="todo",
        task_type="zus_update",
        is_auto_created=True,
    )

    create_demo_activity(volodymyr, event_type="client_created", summary="Демо-клиент создан", actor=staff_user)
    results.append({"client": volodymyr, "token": token_volodymyr, "scenario": "7. ZUS RCA устарел (Last ZUS RCA is 04.2026, requires 05.2026)"})

    # 8. Клиент с платежом (Yuki Tanaka) — консультация оплачена, доступ оплачен, есть долг/остаток
    yuki = create_demo_client(
        email="yuki.tanaka@example.demo",
        first_name="Yuki",
        last_name="Tanaka",
        purpose="work",
        workflow_stage="new_client",
        language="pl",
        assigned_staff=staff_user,
    )
    MOSApplicationData.objects.update_or_create(
        client=yuki,
        defaults={
            "status": "draft",
            "mos_purpose": "work",
        },
    )

    # 1. Консультация оплачена
    create_demo_payment(
        yuki,
        service_description="consultation",
        total_amount=Decimal("150.00"),
        amount_paid=Decimal("150.00"),
        status="paid",
    )
    # 2. Доступ к порталу оплачен частично или имеет долг
    create_demo_payment(
        yuki,
        service_description="legalization_portal_access",
        total_amount=Decimal("1800.00"),
        amount_paid=Decimal("800.00"),
        status="partially_paid",
    )

    token_yuki, _ = create_demo_onboarding_session(yuki)

    create_demo_activity(yuki, event_type="client_created", summary="Демо-клиент создан", actor=staff_user)
    results.append({"client": yuki, "token": token_yuki, "scenario": "8. Клиент с платежом (Portal partially paid, consultation paid)"})

    create_demo_staff_audit(staff_user, event_type="demo_center_run", summary="Набор из 8 демо-сценариев успешно подготовлен")

    return results
