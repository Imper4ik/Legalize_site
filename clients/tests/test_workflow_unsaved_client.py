from __future__ import annotations

import pytest

from clients.forms import ClientForm
from clients.services.workflow import validate_client_workflow_transition


def client_form_data(**overrides):
    defaults = {
        "first_name": "Ira",
        "last_name": "Kowalska",
        "email": "ira-unsaved@example.com",
        "phone": "+48123123123",
        "citizenship": "UA",
        "application_purpose": "work",
        "language": "pl",
        "status": "new",
        "workflow_stage": "application_submitted",
        "family_role": "",
        "sponsor_client": "",
        "notes": "",
    }
    defaults.update(overrides)
    return defaults


@pytest.mark.django_db
def test_unsaved_client_form_ignores_workflow_stage_without_500():
    # The workflow stage moved to the case (CaseForm), so the client form no
    # longer exposes or validates it: passing one is ignored gracefully and can
    # never crash on an unsaved client (spec §4).
    form = ClientForm(data=client_form_data())

    assert "workflow_stage" not in form.fields
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_workflow_validation_rejects_unsaved_application_submitted_client():
    from django.utils import translation
    with translation.override("ru"):
        form = ClientForm(data=client_form_data(workflow_stage="new_client"))
        assert form.is_valid(), form.errors
        client = form.save(commit=False)

        result = validate_client_workflow_transition(
            client=client,
            previous_stage="document_collection",
            next_stage="application_submitted",
        )

        assert not result.allowed
        assert "Сначала сохраните клиента" in result.message
