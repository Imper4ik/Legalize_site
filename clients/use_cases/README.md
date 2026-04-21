# clients/use_cases

## Purpose

This package contains explicit business scenarios for the `clients` domain.
Each module should describe one meaningful action flow without being coupled to
HTML rendering, redirects, or a specific JSON contract.

## When To Add A Use Case

- A view starts changing several domain objects in one action.
- The same business flow is needed from a view, cron endpoint, worker, or
  management command.
- The operation deserves a stable name in the codebase, such as "create payment"
  or "deactivate reminder".

## Current Coverage

- `documents.py` handles note updates, document deletion, verification flows,
  download audit, and `wniosek` attachment deletion.
- `client_records.py` handles create/update side effects for client cards.
- `document_requirements.py` handles checklist requirement add/edit/delete and
  required-document synchronization for a purpose.
- `exports.py` handles export audit events and document version restore.
- `payments.py` handles payment creation, update, and deletion.
- `reminders.py` handles reminder deletion, reminder deactivation, and sending
  document reminder emails.
- `tasks.py` handles task creation and completion.

## Rules

- Accept domain objects and normalized inputs, not raw `request` objects.
- Return a small result object when the caller needs structured outcome data.
- Keep UI messaging outside the use case unless the text is itself domain data.
- Prefer dependency injection for side effects such as email sending when it
  improves testability.
