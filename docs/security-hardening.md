# Security Hardening TODO

## Future Security Improvements
The following are planned security improvements for the next iterations:

- [ ] **Content Security Policy (CSP)**: Add `django-csp` and configure strict CSP headers.
- [ ] **Subresource Integrity (SRI)**: Remove CDNs or add SRI attributes and `crossorigin` to all external script/style tags.
- [ ] **Two-Factor Authentication (2FA)**: Enable 2FA for all staff/admin accounts.
- [ ] **Audit Events**: Split document preview and document download audit events for better traceability.
- [ ] **Storage Infrastructure**: Move away from `DatabaseMediaStorage` and consider Cloudflare R2 or AWS S3 for media storage to prevent database bloat and improve file serving performance.

## CSP inline script/style migration

Production CSP still allows `'unsafe-inline'` for `script-src` and `style-src` to avoid breaking legacy templates that contain inline JavaScript and CSS. Treat this as a temporary compatibility mode.

Migration plan:

1. Inventory inline `<script>` and `<style>` blocks in templates.
2. Move stable inline JavaScript/CSS to static files.
3. For unavoidable inline snippets, use per-request nonces or hashes.
4. Enable CSP report-only first (`LEGALIZE_CSP_REPORT_ONLY=True`) and review reports.
5. Remove `'unsafe-inline'` once reports show no required inline execution.

Validation:

```bash
python manage.py check --deploy
```
