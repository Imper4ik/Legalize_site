from __future__ import annotations

import pytest

from clients.forms import ClientForm


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

