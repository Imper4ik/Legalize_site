from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.db import transaction

from clients.models import Client, Payment
from clients.services.activity import changed_field_labels, log_client_activity

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

PAYMENT_MUTABLE_FIELDS = (
    "service_description",
    "total_amount",
    "amount_paid",
    "status",
    "payment_method",
    "payment_date",
    "due_date",
    "transaction_id",
)


@dataclass(frozen=True)
class PaymentScenarioResult:
    client: Client
    payment: Payment | None = None
    changed_fields: tuple[str, ...] = field(default_factory=tuple)
    deleted_payment_id: int | None = None


def _set_payment_fields(payment: Payment, cleaned_data: Mapping[str, Any]) -> tuple[str, ...]:
    changed_fields: list[str] = []
    for field_name in PAYMENT_MUTABLE_FIELDS:
        if field_name not in cleaned_data:
            continue
        new_value = cleaned_data[field_name]
        if getattr(payment, field_name) != new_value:
            setattr(payment, field_name, new_value)
            changed_fields.append(field_name)
    return tuple(changed_fields)


def create_payment_for_client(
    *,
    client: Client,
    actor: AbstractBaseUser | AnonymousUser | None,
    cleaned_data: Mapping[str, Any],
) -> PaymentScenarioResult:
    with transaction.atomic():
        payment = Payment(client=client)
        _set_payment_fields(payment, cleaned_data)
        payment.save()

        log_client_activity(
            client=client,
            actor=actor,
            event_type="payment_created",
            summary=f"Создан платёж: {payment.get_service_description_display()}",
            metadata={
                "payment_id": payment.id,
                "status": payment.status,
                "total_amount": str(payment.total_amount),
            },
            payment=payment,
        )
    return PaymentScenarioResult(client=client, payment=payment)


def update_payment_for_client(
    *,
    payment: Payment,
    actor: AbstractBaseUser | AnonymousUser | None,
    cleaned_data: Mapping[str, Any],
) -> PaymentScenarioResult:
    changed_fields = _set_payment_fields(payment, cleaned_data)
    if changed_fields:
        with transaction.atomic():
            payment.save()
            log_client_activity(
                client=payment.client,
                actor=actor,
                event_type="payment_updated",
                summary=f"Обновлён платёж: {payment.get_service_description_display()}",
                details=", ".join(changed_field_labels(payment, list(changed_fields))),
                metadata={"payment_id": payment.id, "changed_fields": list(changed_fields)},
                payment=payment,
            )

    return PaymentScenarioResult(
        client=payment.client,
        payment=payment,
        changed_fields=changed_fields,
    )


def delete_payment_for_client(*, payment: Payment, actor: AbstractBaseUser | AnonymousUser | None) -> PaymentScenarioResult:
    client = payment.client
    payment_id = payment.pk

    with transaction.atomic():
        log_client_activity(
            client=client,
            actor=actor,
            event_type="payment_deleted",
            summary=f"Удалён платёж: {payment.get_service_description_display()}",
            metadata={"payment_id": payment_id, "status": payment.status},
            payment=payment,
        )
        payment.archive()

    return PaymentScenarioResult(
        client=client,
        payment=payment,
        deleted_payment_id=payment_id,
    )
