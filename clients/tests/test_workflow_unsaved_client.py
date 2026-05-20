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
def test_unsaved_client_cannot_move_to_application_submitted_without_500():
    form = ClientForm(data=client_form_data())

    assert not form.is_valid()
    assert "workflow_stage" in form.errors
    assert "Сначала сохраните клиента" in str(form.errors["workflow_stage"])


@pytest.mark.django_db
def test_workflow_validation_rejects_unsaved_application_submitted_client():
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
