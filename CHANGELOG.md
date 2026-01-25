# Changelog

## 2026-01-25 14:23 EST
- Skipped the external ICS alignment test by default unless `RUN_ICS_TESTS=1`.

## 2026-01-25 14:21 EST
- Added configurable Flask-Limiter storage URI support and documented it for production.

## 2026-01-25 14:18 EST
- Cached text lookups in `render_text_page` to reduce repeated seasonal/rite queries.
- Added LRU caching for Markdown rendering to avoid re-processing static text content.
- Reviewed service query usage for consolidation; no changes required now.

## 2026-01-25 14:13 EST
- Added schema constraints/indexes migration and updated `ordinarium/schema.sql`.
- Refactored route handlers into focused modules and added supporting service/text helpers.
- Split planning and liturgical calendar helpers into smaller modules with re-export wrappers.
- Replaced custom auth/CSRF/reset/mail with Flask-Login, Flask-WTF, itsdangerous (stateless reset), and Flask-Mail.
- Added rate limiting for login/signup/reset flows plus secure session cookie defaults.
- Expanded tests for CSRF failures, access control, propers search, page slugs, and data integrity.
- Added JSON validity constraints for services/texts and tests to enforce them.
- Removed the password reset token table after switching to stateless reset tokens.
- Added NOT NULL constraints for `users.email` and `pages.slug`.
