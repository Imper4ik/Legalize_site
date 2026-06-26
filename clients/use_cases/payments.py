from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.db import transaction

from clients.models import Client, Payment
from clients.services.activity import log_client_activity

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


def _validate_payment(payment: Payment) -> None:
    payment.full_clean()


def create_payment_for_client(
    *,
    client: Client,
    actor: AbstractBaseUser | AnonymousUser | None,
    cleaned_data: Mapping[str, Any],
    case: Any = None,
) -> PaymentScenarioResult:
    with transaction.atomic():
        # When created from a Case screen the concrete case is passed in and used
        # directly (spec §6); otherwise the model resolves the client's single
        # active case (or rejects an ambiguous multi-case client).
        payment = Payment(client=client, case=case)
        _set_payment_fields(payment, cleaned_data)
        _validate_payment(payment)
        payment.save()

        log_client_activity(
            client=client,
            actor=actor,
            event_type="payment_created",
            summary="Платёж создан",
            metadata={
                "payment_id": payment.id,
                "status": payment.status,
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
        _validate_payment(payment)
        with transaction.atomic():
            payment.save()
            log_client_activity(
                client=payment.client,
                actor=actor,
                event_type="payment_updated",
                summary="Платёж обновлён",
                details="",
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
            summary="Платёж удалён",
            metadata={"payment_id": payment_id},
            payment=payment,
        )
        payment.archive()

    return PaymentScenarioResult(
        client=client,
        payment=payment,
        deleted_payment_id=payment_id,
    )
