from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction

from clients.models import Client, Document, Payment
from clients.services.activity import log_client_activity

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser


@dataclass(frozen=True)
class RestoreScenarioResult:
    client: Client
    restored_object_id: int
    restored_object_type: str


def restore_client_record(*, client: Client, actor: AbstractBaseUser | AnonymousUser | None) -> RestoreScenarioResult:
    from clients.models import ClientArchiveBatch
    from clients.services.archive import restore_client_with_all_cases

    with transaction.atomic():
        open_batch = (
            ClientArchiveBatch.objects.filter(client=client, status="archived")
            .order_by("-archived_at")
            .first()
        )
        if open_batch is not None:
            # Proper batch-based restore with actor attribution and audit entry.
            restore_client_with_all_cases(client=client, actor=actor, batch=open_batch)
        else:
            # Legacy client archived without a batch.
            client.restore()
            log_client_activity(
                client=client,
                actor=actor,
                event_type="client_restored",
                summary="Клиент восстановлен",
                metadata={"status_tag": "restored"},
            )
    return RestoreScenarioResult(client=client, restored_object_id=client.pk, restored_object_type="client")


def restore_client_document(*, document: Document, actor: AbstractBaseUser | AnonymousUser | None) -> RestoreScenarioResult:
    with transaction.atomic():
        document.restore()
        log_client_activity(
            client=document.client,
            actor=actor,
            event_type="client_updated",
            summary="Документ восстановлен из архива",
            metadata={"document_id": document.pk},
            document=document,
        )
    return RestoreScenarioResult(
        client=document.client,
        restored_object_id=document.pk,
        restored_object_type="document",
    )


def restore_client_payment(*, payment: Payment, actor: AbstractBaseUser | AnonymousUser | None) -> RestoreScenarioResult:
    with transaction.atomic():
        payment.restore()
        log_client_activity(
            client=payment.client,
            actor=actor,
            event_type="payment_updated",
            summary="Платёж восстановлен из архива",
            metadata={"payment_id": payment.pk},
            payment=payment,
        )
    return RestoreScenarioResult(
        client=payment.client,
        restored_object_id=payment.pk,
        restored_object_type="payment",
    )
