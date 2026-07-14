# CSP A3 — inline style inventory

Status of the strict `style-src` migration (GO_LIVE item A3).

Already done:
- every `<style>` block (19 files) carries `nonce="{{ request.csp_nonce }}"`;
- the strict Report-Only policy binds the per-request nonce to `style-src`,
  so with `LEGALIZE_CSP_STRICT_REPORT_ONLY=True` the only remaining violation
  class is inline `style="..."` attributes listed below.

Remaining: migrate the attributes to utility/static CSS classes, verify pages
visually on staging, then flip `style-src` to `'self' 'nonce-…'` (drop
`'unsafe-inline'`).

**Totals: 201 attributes, 93 unique, 39 files.**

## Most repeated values (best candidates for utility classes)

| count | style |
|---|---|
| 25 | `font-size: 0.75rem;` |
| 13 | `font-size: 0.8rem;` |
| 8 | `max-width: 220px;` |
| 7 | `z-index: 2; width: 12%;` |
| 6 | `background-color: #e7f3ff;` |
| 5 | `font-size: 0.7rem;` |
| 5 | `max-width: 600px; background-color: rgba(255, 255, 255, 0.05);` |
| 5 | `font-size: 0.95rem; list-style: none;` |
| 4 | `display: none;` |
| 4 | `height: 360px;` |
| 4 | `width: 72px; height: 72px;` |
| 3 | `font-size: 0.75rem; letter-spacing: 0.5px;` |
| 3 | `cursor: pointer;` |
| 3 | `opacity: 0.6;` |
| 3 | `font-size: 0.65rem; border: 1px solid rgba(220,53,69,0.15)` |

## Per-file breakdown

### clients/templates/clients/onboarding/start_contact.html (66)
- `background-color: rgba(255, 255, 255, 0.01);`
- `font-size: 0.65rem; border: 1px solid rgba(220,53,69,0.15)` ×3
- `font-size: 0.75rem;` ×24
- `font-size: 0.75rem; letter-spacing: 0.5px;`
- `font-size: 0.7rem;` ×5
- `font-size: 0.8rem;` ×13
- `font-size: 0.8rem; line-height: 1.4;` ×3
- `height: 360px;` ×2
- `max-width: 220px;` ×7
- `max-width: 600px;`
- `opacity: 0.6;` ×3
- `width: 52px; height: 52px; flex-shrink: 0;` ×2
- `width: {% widthratio case_step|add:'-1' 9 100 %}%;`

### clients/templates/clients/onboarding/base_onboarding.html (34)
- `background: var(--glass-bg); backdrop-filter: blur(20px); border: 1px solid var(--glass-border); min-width: 80px;`
- `background: var(--glass-bg); backdrop-filter: blur(20px); border: 1px solid var(--glass-border); z-index: 1050;`
- `border-bottom: 1px solid var(--glass-border);`
- `border: 1px solid var(--glass-border);`
- `color: var(--fg); font-size: 1.15rem; letter-spacing: -0.02em;` ×2
- `color: var(--fg); font-size: 1.1rem; letter-spacing: -0.02em;` ×2
- `font-size: 0.55rem; opacity: 0.7;`
- `font-size: 0.75rem;`
- `font-size: 0.75rem; letter-spacing: 0.5px;` ×2
- `font-size: 0.75rem; transition: all 0.2s;`
- `font-size: 0.7rem; letter-spacing: 0.5px; border-bottom: 1px solid var(--glass-border);`
- `font-size: 1.1rem; color: var(--brand-1);`
- `font-size: 1rem;` ×2
- `height: 6px; border-radius: 3px; background-color: var(--bs-secondary-bg);`
- `line-height: 1.3;` ×2
- `padding: 0 10px;`
- `position: absolute; top: 16px; left: 0; right: 0; height: 3px; background-color: var(--border); z-index: 1; border-radius: 4px;`
- `width: 280px; max-width: 85vw; background: var(--glass-bg); backdrop-filter: blur(20px); border: 1px solid var(--glass-border); z-index: 1050; border-radius: 16px;`
- `width: 290px; max-width: 90vw; background: var(--glass-bg); backdrop-filter: blur(20px); border: 1px solid var(--glass-border); z-index: 1050;` ×2
- `width: {% widthratio onboarding_step_num|add:'-1' onboarding_step_total|add:'-1' 100 %}%; height: 100%; background-color: var(--brand-1); transition: width 0.4s ease; border-radius: 4px;`
- `width: {{ onboarding_step_percent }}%; transition: width 0.6s ease;`
- `z-index: 2; width: 12%;` ×7

### clients/templates/clients/partials/document_checklist.html (10)
- `font-size: 0.95rem; list-style: none;` ×5
- `max-width: 600px; background-color: rgba(255, 255, 255, 0.05);` ×5

### clients/templates/clients/admin_panel.html (9)
- `--ops-icon-color:#0891b2;--ops-icon-bg:rgba(8,145,178,.1);` ×2
- `--ops-icon-color:#16a34a;--ops-icon-bg:rgba(22,163,74,.1);` ×2
- `--ops-icon-color:#2563eb;--ops-icon-bg:rgba(37,99,235,.1);`
- `--ops-icon-color:#475569;--ops-icon-bg:rgba(71,85,105,.12);`
- `--ops-icon-color:#7c3aed;--ops-icon-bg:rgba(124,58,237,.1);`
- `--ops-icon-color:#d97706;--ops-icon-bg:rgba(217,119,6,.1);`
- `--ops-icon-color:#dc2626;--ops-icon-bg:rgba(220,38,38,.1);`

### clients/templates/clients/documents/mazowiecki_application.html (8)
- `border-bottom: 1px dotted black; display: inline-block; width: 150px;`
- `border-top: 1px dotted black; width: 250px;`
- `font-weight: bold;`
- `margin-bottom: 10px;`
- `margin-top: 20px;`
- `position: absolute; right: 8mm; bottom: 6mm; text-align: center; opacity: 0.55;`
- `text-align: right; margin-top: 20px;`
- `width: 15mm; height: 15mm; display: block;`

### clients/templates/clients/client_wsc_print.html (6)
- `background-color: #e8efff;`
- `background-color: #f4f8ff;`
- `background: white;`
- `color: var(--primary-color); font-weight: bold;`
- `font-size: 0.9em; color: #666;`
- `padding: 5px; border: none;`

### clients/templates/clients/clients_list.html (6)
- `display: none; position: absolute; top: 100%; left: 0; z-index: 1000; max-height: 300px; overflow-y: auto;`
- `display: none; width: 150px; height: 150px;`
- `display:none;`
- `max-height: 300px; overflow-y: auto;`
- `white-space: pre-wrap; font-size: 0.9rem; word-break: break-all; color: #333;`
- `width: 166px; height: 166px;`

### clients/templates/clients/client_printable.html (5)
- `background-color: #e8efff;`
- `background-color: #f4f8ff;`
- `background: white;`
- `color: var(--primary-color); font-weight: bold;`
- `padding: 5px; border: none;`

### clients/templates/clients/client_add.html (4)
- `background-color: #e7f3ff;` ×3
- `height: 120px;`

### clients/templates/clients/client_edit.html (4)
- `background-color: #e7f3ff;` ×3
- `height: 120px;`

### templates/admin/base_site.html (4)
- `display:inline-block; margin-right: 15px; padding: 5px 10px; background-color: #0284c7; color: white; border-radius: 4px; text-decoration: none; font-weight: bold;`
- `display:inline-block; margin-right: 15px; padding: 5px 10px; background-color: #4CAF50; color: white; border-radius: 4px; text-decoration: none; font-weight: bold;`
- `display:inline-block; margin-right: 15px; padding: 5px 10px; background-color: #dc2626; color: white; border-radius: 4px; text-decoration: none; font-weight: bold;`
- `opacity: .85;`

### templates/admin/login.html (4)
- `display:inline-flex;align-items:center;gap:0.5rem;padding:0.4rem 0.9rem;border-radius:9999px;background:rgba(15,23,42,0.25);border:1px solid rgba(248,250,252,0.25);font-weight:600;`
- `margin-right:0.5rem;`
- `margin-top:0.75rem;` ×2

### clients/templates/clients/onboarding/start.html (3)
- `height: 360px;` ×2
- `width: {% widthratio case_step|add:'-1' 9 100 %}%;`

### clients/templates/clients/onboarding/travel.html (3)
- `display: none;` ×3

### templates/account/email.html (3)
- `max-width: 800px;`
- `opacity: 0.15;`
- `width: 72px; height: 72px;`

### clients/templates/clients/calculator.html (2)
- `max-width: 100px;`
- `top: 20px;`

### clients/templates/clients/onboarding/expired.html (2)
- `font-size: 5.5rem; filter: drop-shadow(0 4px 6px rgba(0, 0, 0, 0.08));`
- `max-width: 520px; font-size: 1.05rem; line-height: 1.6;`

### clients/templates/clients/onboarding/locked.html (2)
- `font-size: 5.5rem; filter: drop-shadow(0 4px 6px rgba(0, 0, 0, 0.08));`
- `max-width: 520px; font-size: 1.05rem; line-height: 1.6;`

### clients/templates/clients/partials/email_history.html (2)
- `cursor: pointer;`
- `white-space: pre-wrap; font-size: 0.9em; background-color: rgba(128, 128, 128, 0.05);`

### clients/templates/clients/partials/workflow_panel.html (2)
- `max-width: 55%; font-size: 0.75rem;` ×2

### clients/templates/clients/privacy_policy.html (2)
- `white-space: pre-line;` ×2

### clients/templates/clients/staff_manage.html (2)
- `min-width: 220px;`
- `min-width: 320px;`

### templates/account/password_reset_from_key_done.html (2)
- `color: inherit;`
- `width: 76px; height: 76px;`

### clients/templates/clients/admin_dashboard.html (1)
- `max-width: 220px;`

### clients/templates/clients/case_detail.html (1)
- `max-width: 280px;`

### clients/templates/clients/mos_review.html (1)
- `top: 20px;`

### clients/templates/clients/onboarding/partials/new_card_application_block.html (1)
- `letter-spacing: .04em;`

### clients/templates/clients/onboarding/passport.html (1)
- `font-size: 0.85rem;`

### clients/templates/clients/onboarding/select_case.html (1)
- `cursor: pointer;`

### clients/templates/clients/onboarding/set_password.html (1)
- `display: none;`

### clients/templates/clients/partials/activity_timeline.html (1)
- `cursor: pointer;`

### clients/templates/clients/service_price_manage.html (1)
- `width: 220px;`

### clients/templates/clients/submission_manage.html (1)
- `min-width: 180px;`

### templates/account/auth_base.html (1)
- `font-size: 0.85rem;`

### templates/account/logout.html (1)
- `width: 72px; height: 72px; background: linear-gradient(135deg, #ef4444, #b91c1c); box-shadow: 0 14px 32px rgba(239, 68, 68, 0.2);`

### templates/account/password_change.html (1)
- `width: 72px; height: 72px;`

### templates/account/password_reset.html (1)
- `width: 72px; height: 72px;`

### templates/account/password_reset_done.html (1)
- `width: 76px; height: 76px;`

### templates/account/password_reset_from_key.html (1)
- `width: 72px; height: 72px;`
