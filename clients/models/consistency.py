from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


def resolve_required_case(client_id: int, model_name: str) -> Any:
    """Resolve the client's single active case for a case-scoped write.

    Case-scoped rows are created against a concrete case and every production
    caller passes it explicitly. This resolver is the model-level backstop for
    legacy rows and direct ORM writes: it succeeds only when the client has
    exactly one active case; with zero or several active cases the write is
    ambiguous and raises instead of guessing or binding to an archived case.
    """
    from clients.models.case import Case

    logger.debug("Model-level case resolution for %s, client_id=%s", model_name, client_id)
    # Case.objects excludes archived cases, so this only returns an active one.
    active_cases = list(Case.objects.filter(client_id=client_id)[:2])
    if len(active_cases) == 1:
        return active_cases[0]
    raise ValidationError("Для этой операции необходимо выбрать дело.")


def assert_case_client_consistent(instance: Any) -> None:
    """Enforce the Client↔Case invariant on the write path.

    Every case-scoped model (Document, Payment, StaffTask, Reminder, the MOS/
    PESEL/onboarding records, …) validates ``case.client_id == client_id`` in
    ``clean()``. But ``clean()`` is never called by ``save()`` /
    ``objects.create()`` / bulk paths / data migrations, so that guard alone is
    bypassable. This helper mirrors the check so a record of one client can never
    be persisted against another client's case through raw ORM access.

    The FK pair is checked even for partial ``save(update_fields=...)`` calls, so
    direct ``case_id`` or ``client_id`` edits cannot persist a mismatched pair.
    """

    case_id = getattr(instance, "case_id", None)
    client_id = getattr(instance, "client_id", None)
    if not case_id or not client_id:
        return

    case = None
    state = getattr(instance, "_state", None)
    fields_cache = getattr(state, "fields_cache", {}) if state is not None else {}
    if "case" in fields_cache:
        case = instance.case
        case_client_id = case.client_id if case is not None else None
    else:
        from django.apps import apps

        Case = apps.get_model("clients", "Case")
        case_client_id = Case.all_objects.filter(pk=case_id).values_list("client_id", flat=True).first()

    if case_client_id is not None and case_client_id != client_id:
        raise ValidationError("Клиент и дело не согласованы.")
