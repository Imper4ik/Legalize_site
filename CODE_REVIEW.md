# Code Review Summary

## 1. Account onboarding flow can crash for new users
*Files: `portal/forms.py`, `portal/views.py`*

`CustomSignupForm.signup()` only links a user account to an existing `Client` record if it finds one with a matching email. When there is no pre-created client entry, the method simply returns without creating a profile.【F:portal/forms.py†L25-L64】 Subsequently, `ProfileDetailView` always calls `get_object_or_404(Client, user=self.request.user)`, which raises a 404 for such users, effectively breaking the newly created account right after signup.【F:portal/views.py†L19-L52】 Consider creating a minimal `Client` instance (filling required fields with temporary placeholders), redirecting the user to complete their profile, or presenting a friendlier page instead of an error.

## 2. Document uploads accept arbitrary document codes
*Files: `portal/views.py`, `clients/models.py`*

In `portal_document_upload` the document type is taken directly from the URL parameter and written to the model without any validation.【F:portal/views.py†L61-L92】 Because the `Document` model's `document_type` field is just a `CharField`, Django will happily persist any arbitrary string that reaches this point; the `choices` list is only enforced when the field is validated through a form.【F:clients/models.py†L73-L101】 This allows a malicious client (or buggy front-end) to create inconsistent checklist entries and makes it difficult to reason about uploaded files. Introduce server-side validation that restricts uploads to the document types relevant to the client's current checklist before saving.

## 3. Committed virtual environment inflates the repository
*Files: `legalize_site/venv/*`*

The repository contains a complete Python virtual environment under `legalize_site/venv/` (for example, `pyvenv.cfg`).【F:legalize_site/venv/pyvenv.cfg†L1-L3】 Committing generated interpreter files bloats the repo and risks platform-specific incompatibilities. It's better to remove this directory from version control and add it to `.gitignore` so each developer (and Render) can build the environment locally.

## 4. Duplicate AJAX detection logic
*File: `portal/views.py`*

`portal_document_upload` computes `expects_json = request_is_ajax(request)` but never uses the result, and then calls the bespoke `_is_ajax()` helper instead.【F:portal/views.py†L53-L92】 Maintaining two different code paths for the same concern invites divergence and subtle bugs. Prefer a single well-tested helper (the shared `request_is_ajax`) and drop the unused code.

## 5. Username generation lacks a fallback
*File: `portal/adapters.py`*

`CustomAccountAdapter.populate_username()` slugifies the local part of the email and loops until the slug is unique, but it never handles the case where slugification returns an empty string (e.g. emails whose local part contains only punctuation).【F:portal/adapters.py†L7-L23】 Saving a user with an empty username will violate database constraints. Add a fallback—such as a random suffix or the user's ID—to guarantee a non-empty username.
