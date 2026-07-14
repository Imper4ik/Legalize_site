"""Django admin registrations for the clients app, split by domain.

Importing the submodules performs the ``@admin.register`` calls; the shared
actions are re-exported for backwards compatibility.
"""
from clients.admin import compliance, core, onboarding, operations  # noqa: F401
from clients.admin.actions import (  # noqa: F401
    approve_selected_erasures,
    archive_selected,
    fulfill_erasure_requests,
    mask_json_pii,
    place_legal_hold_action,
    release_legal_hold_action,
    restore_selected,
)
