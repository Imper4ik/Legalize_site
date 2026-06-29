from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError


def assert_case_client_consistent(instance: Any) -> None:
    """Enforce the Client↔Case invariant on the write path.

    Every case-scoped model (Document, Payment, StaffTask, Reminder, the MOS/
    PESEL/onboarding records, …) validates ``case.client_id == client_id`` in
    ``clean()``. But ``clean()`` is never called by ``save()`` /
    ``objects.create()`` / bulk paths / data migrations, so that guard alone is
    bypassable. This helper mirrors the check so a record of one client can never
    be persisted against another client's case through raw ORM access.

    To keep routine partial updates cheap, the FK is only inspected when the row
    is being inserted or the ``case`` relation is already loaded — an
    already-validated row updated via ``update_fields`` triggers no extra query.
    """

    case_id = getattr(instance, "case_id", None)
    client_id = getattr(instance, "client_id", None)
    if not case_id or not client_id:
        return

    state = getattr(instance, "_state", None)
    adding = getattr(state, "adding", True) if state is not None else True
    fields_cache = getattr(state, "fields_cache", {}) if state is not None else {}
    if not adding and "case" not in fields_cache:
        return

    case = instance.case
    if case is not None and case.client_id != client_id:
        raise ValidationError("Клиент и дело не согласованы.")
