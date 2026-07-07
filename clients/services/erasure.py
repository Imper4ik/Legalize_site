"""RODO art. 17 erasure request workflow.

Erasure is irreversible, so a single subject request must never auto-destroy
data. The lifecycle is:

    requested  → (staff verifies identity + reviews) → approved → fulfilled
                                                      → rejected

A ``legal_hold`` blocks both approval and the automatic retention sweep, so
material still needed for an active case, accounting, or the firm's legal
defence cannot be erased on request or by age alone.

Identity verification is a human act the system cannot perform itself; it is
part of the staff review that precedes :func:`approve_erasure`, recorded via the
decision reason.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone

if TYPE_CHECKING:
    from datetime import datetime

    from django.contrib.auth.models import AbstractBaseUser

    from clients.models import Client


class ErasureWorkflowError(RuntimeError):
    """Invalid erasure state transition."""


class LegalHoldError(ErasureWorkflowError):
    """The client is under a legal hold, so erasure cannot proceed."""


def request_erasure(client: Client, *, at: datetime | None = None) -> None:
    """Record a subject-initiated erasure request (art. 17). Idempotent."""
    from clients.models import Client as ClientModel

    status = ClientModel.ErasureStatus
    if client.erasure_status == status.FULFILLED:
        return

    updated: list[str] = []
    if client.erasure_requested_at is None:
        client.erasure_requested_at = at or timezone.now()
        updated.append("erasure_requested_at")
    # A fresh request re-opens a previously rejected one; an already
    # requested/approved case is left in place.
    if client.erasure_status in (status.NONE, status.REJECTED):
        client.erasure_status = status.REQUESTED
        updated.append("erasure_status")
    if updated:
        client.save(update_fields=updated)


def approve_erasure(client: Client, *, actor: AbstractBaseUser | None, reason: str = "") -> None:
    """Staff approve a reviewed request for fulfilment."""
    from clients.models import Client as ClientModel

    status = ClientModel.ErasureStatus
    if client.legal_hold:
        raise LegalHoldError(
            f"Client {client.id} is under a legal hold and cannot be approved for erasure."
        )
    if client.erasure_status != status.REQUESTED:
        raise ErasureWorkflowError(
            f"Cannot approve erasure from status '{client.erasure_status}'; expected 'requested'."
        )
    client.erasure_status = status.APPROVED
    client.erasure_approved_at = timezone.now()
    client.erasure_approved_by = actor  # type: ignore[assignment]
    client.erasure_decision_reason = (reason or "")[:500]
    client.save(update_fields=[
        "erasure_status", "erasure_approved_at", "erasure_approved_by", "erasure_decision_reason",
    ])


def reject_erasure(client: Client, *, actor: AbstractBaseUser | None, reason: str) -> None:
    """Staff decline a request (e.g. ongoing case, retention obligation)."""
    from clients.models import Client as ClientModel

    status = ClientModel.ErasureStatus
    if client.erasure_status not in (status.REQUESTED, status.APPROVED):
        raise ErasureWorkflowError(
            f"Cannot reject erasure from status '{client.erasure_status}'."
        )
    if not (reason or "").strip():
        raise ErasureWorkflowError("A reason is required to reject an erasure request.")
    client.erasure_status = status.REJECTED
    client.erasure_approved_at = None
    client.erasure_approved_by = actor  # type: ignore[assignment]
    client.erasure_decision_reason = reason[:500]
    client.save(update_fields=[
        "erasure_status", "erasure_approved_at", "erasure_approved_by", "erasure_decision_reason",
    ])


def place_legal_hold(client: Client, *, reason: str) -> None:
    if not (reason or "").strip():
        raise ErasureWorkflowError("A reason is required to place a legal hold.")
    client.legal_hold = True
    client.legal_hold_reason = reason[:500]
    client.save(update_fields=["legal_hold", "legal_hold_reason"])


def release_legal_hold(client: Client) -> None:
    client.legal_hold = False
    client.legal_hold_reason = ""
    client.save(update_fields=["legal_hold", "legal_hold_reason"])
