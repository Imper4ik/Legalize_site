"""spec §12: ClientActivity summary/details/metadata must never carry PII.

Exercises the mutation use-cases (documents, payments, tasks, reminders,
email) with deliberately identifiable PII and asserts none of it lands in the
activity log's summary, details or metadata.
"""
from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from clients.models import ClientActivity, EmailLog, Reminder
from clients.testing.factories import (
    create_test_client,
    create_test_document,
    create_test_user,
)
from clients.use_cases.documents import (
    delete_client_document,
    record_document_download,
)
from clients.use_cases.payments import (
    create_payment_for_client,
    delete_payment_for_client,
)
from clients.use_cases.reminders import delete_reminder
from clients.use_cases.tasks import complete_task_for_client, create_task_for_client

# Strings that must never appear anywhere in the audit log.
PII_NEEDLES = [
    "Zlatan",
    "Piison",
    "SECRET-TASK-TITLE",
    "secret task description",
    "Consultation about the secret deportation case",
    "Confidential reminder note",
    "Top secret email subject",
    "client.pii@example.test",
]


@pytest.mark.django_db
def test_mutation_use_cases_log_no_pii():
    staff = create_test_user(role="Staff")
    client = create_test_client(
        first_name="Zlatan",
        last_name="Piison",
        email="client.pii@example.test",
    )
    case = client.cases.get()

    # Document delete + download
    doc = create_test_document(client, case=case, filename="zlatan-passport.pdf")
    record_document_download(document=doc, actor=staff)
    delete_client_document(document=doc, actor=staff)

    # Payment create + delete (PII in the service description display)
    pay_res = create_payment_for_client(
        client=client,
        actor=staff,
        cleaned_data={
            "service_description": "consultation",
            "total_amount": Decimal("100.00"),
            "amount_paid": Decimal("0.00"),
            "status": "pending",
            "payment_method": "cash",
        },
    )
    delete_payment_for_client(payment=pay_res.payment, actor=staff)

    # Task create + complete (PII in title/description)
    task_res = create_task_for_client(
        client=client,
        actor=staff,
        cleaned_data={
            "title": "SECRET-TASK-TITLE",
            "description": "secret task description",
            "status": "open",
            "priority": "high",
        },
    )
    complete_task_for_client(task=task_res.task, actor=staff)

    # Reminder delete (PII in title)
    reminder = Reminder.objects.create(
        client=client,
        case=case,
        reminder_type="custom",
        title="Confidential reminder note",
        due_date=timezone.localdate() + timedelta(days=3),
    )
    delete_reminder(reminder=reminder, actor=staff)

    # Email sent signal (PII in subject)
    EmailLog.objects.create(
        client=client,
        case=case,
        subject="Top secret email subject",
        recipients="client.pii@example.test",
        template_type="custom",
        delivery_status=EmailLog.DELIVERY_STATUS_SENT,
    )

    activities = ClientActivity.objects.filter(client=client)
    assert activities.exists()
    for activity in activities:
        blob = " ".join(
            [
                activity.summary or "",
                activity.details or "",
                json.dumps(activity.metadata, ensure_ascii=False, default=str),
            ]
        )
        for needle in PII_NEEDLES:
            assert needle not in blob, (
                f"PII '{needle}' leaked into activity {activity.event_type}: {blob!r}"
            )
