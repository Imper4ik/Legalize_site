# Security Hardening TODO

## Future Security Improvements
The following are planned security improvements for the next iterations:

- [ ] **Content Security Policy (CSP)**: Add `django-csp` and configure strict CSP headers.
- [ ] **Subresource Integrity (SRI)**: Remove CDNs or add SRI attributes and `crossorigin` to all external script/style tags.
- [ ] **Two-Factor Authentication (2FA)**: Enable 2FA for all staff/admin accounts.
- [ ] **Audit Events**: Split document preview and document download audit events for better traceability.
- [ ] **Storage Infrastructure**: Move away from `DatabaseMediaStorage` and consider Cloudflare R2 or AWS S3 for media storage to prevent database bloat and improve file serving performance.
