# clients

## Purpose

`clients` is the main business app of the project. It owns client records,
documents, payments, reminders, staff workflow, and the related operational UI.

## Main Areas

- Client profile and workflow state.
- Document upload, verification, checklist, OCR, and document history.
- Payments, payment reminders, and finance-related status.
- Email flows, previews, campaigns, and notification history.
- Staff tasks, timeline, audit events, and admin visibility.

## Structure

- `models/` stores domain entities and their relations.
- `views/` handles HTTP concerns: permissions, forms, redirects, JSON payloads,
  and template rendering.
- `use_cases/` contains explicit business scenarios that can be called from
  views, cron endpoints, or management commands.
- `services/` contains reusable domain and infrastructure helpers that are not
  tied to a specific HTTP response.
- `management/commands/` contains background and operator commands.
- `templates/clients/` contains the app UI.
- `tests/` covers end-to-end flows, regressions, and focused business logic.

## Layer Boundaries

- Keep `views/` thin. They should coordinate request handling, not own long
  chains of domain mutations.
- Put multi-step business actions into `use_cases/` when the same flow may be
  needed from more than one entry point.
- Keep `services/` lower-level than `use_cases/`: services provide helpers,
  use cases assemble a full scenario.
- Prefer testing critical business behavior both through the HTTP layer and
  directly through `use_cases/` when the scenario is important on its own.

## Entry Point

The app routes are mounted through `clients.urls` under the `/staff/` prefix.
