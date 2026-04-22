from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from clients.models import Client, Document, Payment
from clients.services.activity import log_client_activity


@dataclass(frozen=True)
class RestoreScenarioResult:
    client: Client
    restored_object_id: int
    restored_object_type: str


def restore_client_record(*, client: Client, actor) -> RestoreScenarioResult:
    with transaction.atomic():
        client.restore()
        log_client_activity(
            client=client,
            actor=actor,
            event_type="client_updated",
            summary="Клиент восстановлен из архива",
            metadata={"restored_object": "client", "restored_object_id": client.pk},
        )
    return RestoreScenarioResult(client=client, restored_object_id=client.pk, restored_object_type="client")


def restore_client_document(*, document: Document, actor) -> RestoreScenarioResult:
    with transaction.atomic():
        document.restore()
        log_client_activity(
            client=document.client,
            actor=actor,
            event_type="client_updated",
            summary=f"Документ восстановлен из архива: {document.display_name}",
            metadata={"restored_object": "document", "restored_object_id": document.pk},
            document=document,
        )
    return RestoreScenarioResult(
        client=document.client,
        restored_object_id=document.pk,
        restored_object_type="document",
    )


def restore_client_payment(*, payment: Payment, actor) -> RestoreScenarioResult:
    with transaction.atomic():
        payment.restore()
        log_client_activity(
            client=payment.client,
            actor=actor,
            event_type="payment_updated",
            summary=f"Платёж восстановлен из архива: {payment.get_service_description_display()}",
            metadata={"restored_object": "payment", "restored_object_id": payment.pk},
            payment=payment,
        )
    return RestoreScenarioResult(
        client=payment.client,
        restored_object_id=payment.pk,
        restored_object_type="payment",
    )
