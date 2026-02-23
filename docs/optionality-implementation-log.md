# Optionality Implementation Log

Purpose:
- Track discrete implementation changes for configurable liturgical optionality.
- Keep an auditable record of schema, backend, UI, and rendering updates.

## Entry template

### YYYY-MM-DD - Short title

- Scope:
- Option keys added/changed:
- Schema/migrations:
- Backend changes:
- UI changes:
- Rendering behavior:
- Tests added/updated:
- Backward compatibility notes:
- Follow-up items:

---

## Entries

### 2026-02-22 - Log initialized

- Scope: Create tracking artifact before implementation begins.
- Option keys added/changed: None yet.
- Schema/migrations: None yet.
- Backend changes: None yet.
- UI changes: None yet.
- Rendering behavior: None yet.
- Tests added/updated: None yet.
- Backward compatibility notes: N/A.
- Follow-up items: Start Phase 1 checklist in `/Users/rwillers/Desktop/Ordinarium/RITE_OPTIONALITY_MATRIX.md`.

### 2026-02-22 - Phase 1 foundation: service option storage + render scaffold

- Scope: Add persistent service option storage and non-destructive render transforms for initial option keys.
- Option keys added/changed:
  - `lords_prayer.form`
  - `confession.invitation_form`
  - `dismissal.form`
- Schema/migrations:
  - Added `services.service_option_values` JSON column in `/Users/rwillers/Desktop/Ordinarium/ordinarium/schema.sql`.
  - Added migration `/Users/rwillers/Desktop/Ordinarium/scripts/migrations/031_add_service_option_values.sql`.
- Backend changes:
  - Wired `service_option_values` through create/load/update and text-load payloads in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_store.py`.
  - Preserved `service_option_values` in service PATCH saves (`/Users/rwillers/Desktop/Ordinarium/ordinarium/service_persist_routes.py`).
  - Included `service_option_values` in copy-service flow (`/Users/rwillers/Desktop/Ordinarium/ordinarium/service_overview_routes.py`).
  - Exposed parsed `service_option_values` in plan context (`/Users/rwillers/Desktop/Ordinarium/ordinarium/plan_context.py`).
  - Included parsed `service_option_values` in PCO sync rendering inputs (`/Users/rwillers/Desktop/Ordinarium/ordinarium/pco_sync.py`).
- UI changes:
  - None yet (scaffold phase; values can be set via DB/tests).
- Rendering behavior:
  - Added non-destructive option transform module `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_rendering.py`.
  - Integrated transform pass in `/Users/rwillers/Desktop/Ordinarium/ordinarium/text_rendering.py` for view/export/PCO rendering pipeline.
- Tests added/updated:
  - Added JSON integrity test for `service_option_values` in `/Users/rwillers/Desktop/Ordinarium/tests/test_data_integrity.py`.
  - Extended copy-service test to assert `service_option_values` round-trip in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Added option-rendering tests for Lord’s Prayer, AST Confession invitation, and Dismissal forms in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Updated service fixture insert to include `service_option_values` in `/Users/rwillers/Desktop/Ordinarium/tests/conftest.py`.
- Backward compatibility notes:
  - Rendering defaults unchanged when `service_option_values` is absent/empty.
  - Source liturgical text in `texts` table remains unchanged; transformations are render-time only.
- Follow-up items:
  - Add API/UI controls to set these option keys from planner.
  - Add seasonal `auto/on/off` rule-driven keys (`fraction.alleluia_mode`, `dismissal.alleluia_mode`).

### 2026-02-22 - Phase 1 controls: planner UI + API for initial option keys

- Scope: Add planner controls and API persistence for first option-backed sections.
- Option keys added/changed:
  - `lords_prayer.form` (UI/API control added)
  - `dismissal.form` (UI/API control added)
  - `confession.invitation_form` (UI/API control added, AST-only)
- Schema/migrations:
  - No additional schema changes.
- Backend changes:
  - Added option registry and validation helpers in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_registry.py`.
  - Added route `/service/<id>/service-option` in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_share_routes.py`.
  - Exposed per-rite option definitions in planner context via `/Users/rwillers/Desktop/Ordinarium/ordinarium/plan_context.py`.
- UI changes:
  - Added row action `Set option` for supported sections in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html`.
  - Added section option modal and client-side save flow (JSON POST + indicator updates) in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html`.
- Rendering behavior:
  - No change to source text storage; render output remains non-destructive and option-driven.
- Tests added/updated:
  - Added route tests for set/clear and invalid values in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Added service-page presence check for `Set option` action in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
- Backward compatibility notes:
  - Unsupported or invalid keys/values are rejected by API; existing services render unchanged.
- Follow-up items:
  - Add `rule_driven` seasonal controls and UI for `fraction.alleluia_mode` and `dismissal.alleluia_mode`.

### 2026-02-23 - Phase 1 rule-driven controls: Fraction + Dismissal alleluia modes

- Scope: Add seasonal `auto/on/off` options and planner support for alleluia behavior in Fraction and Dismissal.
- Option keys added/changed:
  - `fraction.alleluia_mode` (new)
  - `dismissal.alleluia_mode` (new)
- Schema/migrations:
  - No additional schema changes.
- Backend changes:
  - Added option definitions and validation in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_registry.py`.
  - Extended render-time option transformer logic in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_rendering.py` to apply seasonal alleluia behavior.
  - Passed season context into option rendering in `/Users/rwillers/Desktop/Ordinarium/ordinarium/text_rendering.py`.
- UI changes:
  - Added row-level access for Fraction alleluia mode and a dedicated Dismissal alleluia action in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html`.
  - Updated planner modal JS to support primary and secondary option keys in one row and keep indicators in sync.
- Rendering behavior:
  - Fraction alleluia token brackets can be forced on/off, or auto-evaluated by season (`Easter`, `Ascension`, `Pentecost`).
  - Dismissal alleluia add-ons can be forced on/off, or auto-evaluated by season with the same rule set.
- Tests added/updated:
  - Added route validation/acceptance tests for new alleluia keys in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Added render behavior tests for `on/off/auto` alleluia modes across Lent/Easter in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Extended service page action presence test to include the Dismissal alleluia action in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
- Backward compatibility notes:
  - Existing services and defaults remain unchanged until an alleluia mode option is explicitly set.
- Follow-up items:
  - Implement `fraction.form` and `communion.invitation.form` controls next in Phase 1.
