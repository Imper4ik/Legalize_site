# Security hardening status

## Implemented

- Production responses include an enforced Content Security Policy.
- `script-src` is restricted to the application origin; executable inline
  scripts require a per-request nonce.
- Browser assets are vendored under `static/vendor/`; the application does not
  load fonts, scripts, styles, or QR images from public CDNs.
- Uploaded client files are private and may use database or S3-compatible
  storage.
- Sensitive model fields, authorization checks, rate limits and security audit
  events are covered by automated tests.

## Remaining improvements

- [ ] **Two-factor authentication:** choose and enable a 2FA flow for all
  staff/admin accounts. This needs an owner decision on email versus TOTP,
  recovery policy and support process.
- [ ] **Strict style CSP:** move the remaining template `<style>` blocks and
  `style=` attributes into static stylesheets, then remove `'unsafe-inline'`
  from `style-src`. `script-src` is already nonce-protected.
- [ ] **Audit events:** split document preview and download events if the
  business requires separate reporting.
- [ ] **Storage at scale:** use S3/R2/B2 instead of database media storage when
  file volume makes database backups or restores too slow.

To inventory style-policy violations without breaking the UI, enable
`LEGALIZE_CSP_STRICT_REPORT_ONLY=True`, review browser reports, and then migrate
the reported styles. Validate production settings with:

```bash
python manage.py check --deploy
```
