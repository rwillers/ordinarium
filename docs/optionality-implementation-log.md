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

### 2026-02-23 - Phase 1 form controls: Fraction + Communion invitation

- Scope: Add selectable form options for Fraction and Ministration invitation text.
- Option keys added/changed:
  - `fraction.form` (new)
  - `communion.invitation.form` (new)
- Schema/migrations:
  - No additional schema changes.
- Backend changes:
  - Added option definitions/validation in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_registry.py`.
  - Extended render-time transformer logic in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_rendering.py`:
    - Fraction form selection (`passover_is_sacrificed` / `passover_lamb_has_been_sacrificed`)
    - Communion invitation form selection (`gifts_of_god` / `behold_lamb`)
  - Preserved non-destructive behavior: source liturgical text remains unchanged; substitutions happen at render time.
- UI changes:
  - Updated planner row option mapping in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html`:
    - Fraction row primary option now edits `fraction.form`
    - Fraction row includes secondary action for `fraction.alleluia_mode`
    - Ministration row supports `communion.invitation.form`
  - Extended row indicator logic to account for Fraction secondary alleluia mode in addition to Dismissal.
- Rendering behavior:
  - Fraction renders a single selected invitation form when configured, then applies alleluia mode rules.
  - Ministration renders only the selected invitation block and removes the inline “or this” alternative.
- Tests added/updated:
  - Added API tests for set/validation on `fraction.form` and `communion.invitation.form` in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Added render tests for selected Fraction and Communion invitation forms in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
- Backward compatibility notes:
  - Existing services render unchanged unless these option keys are set.
- Follow-up items:
  - Implement token-level toggles for Communion bracketed clauses (invitation and distribution formulae).

### 2026-02-23 - Phase 1 token toggles: Communion bracketed clauses

- Scope: Add token-level include/omit controls for bracketed Communion clauses.
- Option keys added/changed:
  - `communion.invitation.appended_clause` (new)
  - `communion.distribution.body_clause` (new)
  - `communion.distribution.blood_clause` (new)
- Schema/migrations:
  - No additional schema changes.
- Backend changes:
  - Added option definitions/validation in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_registry.py`.
  - Added render transforms in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_rendering.py` to include/omit bracketed clauses non-destructively.
- UI changes:
  - Added Ministration row actions in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html` for:
    - Invitation appended clause
    - Body formula clause
    - Blood formula clause
  - Extended option indicator logic so Ministration row reflects secondary clause settings.
- Rendering behavior:
  - `include` renders bracketed clause text inline without brackets.
  - `omit` removes bracketed clause text.
  - Unset key preserves original bracketed source text.
- Tests added/updated:
  - Added API set/validation coverage for all three new keys in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Added render tests for both `omit` and `include` modes in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
- Backward compatibility notes:
  - Existing services render unchanged unless these keys are explicitly set.
- Follow-up items:
  - Add Filioque and other bracket-token toggles outside the Communion section.

### 2026-02-23 - Phase 1 token toggles: Nicene Creed Filioque clause

- Scope: Add explicit include/omit control for the Nicene Creed Filioque bracket token.
- Option keys added/changed:
  - `creed.filioque_clause` (new)
- Schema/migrations:
  - No additional schema changes.
- Backend changes:
  - Added option definition/validation in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_registry.py`.
  - Added render transform in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_rendering.py` for include/omit behavior on `[and the Son]`.
- UI changes:
  - Added Nicene Creed row option mapping in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html`.
- Rendering behavior:
  - `include` renders “and the Son” without brackets.
  - `omit` removes bracketed phrase.
  - Unset key preserves source bracketed text.
- Tests added/updated:
  - Added API set/validation tests for `creed.filioque_clause` in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Added render tests for both include/omit modes in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
- Backward compatibility notes:
  - Existing services render unchanged unless key is set.
- Follow-up items:
  - Continue bracket-token coverage for remaining sections beyond Communion and Nicene Creed.

### 2026-02-23 - Phase 1 token toggles: Prayers of the People bracket clauses

- Scope: Add include/omit controls for bracketed local-insert clauses in RAT/AST Prayers of the People.
- Option keys added/changed:
  - `prayers.public_service.especially_clause` (RAT)
  - `prayers.adversity.especially_clause` (RAT/AST)
  - `prayers.departed.especially_clause` (RAT/AST)
  - `prayers.saints.named_insert` (AST)
- Schema/migrations:
  - No additional schema changes.
- Backend changes:
  - Added option definitions/validation in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_registry.py`.
  - Added render transforms in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_rendering.py` for Prayers clause include/omit behavior.
- UI changes:
  - Added Prayers row option mapping and secondary actions in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html`.
  - Extended row indicator logic for Prayers secondary option keys.
- Rendering behavior:
  - `include` removes brackets and keeps clause text inline.
  - `omit` removes the bracketed clause/insert.
  - Unset keys preserve source text with bracketed placeholders.
- Tests added/updated:
  - Added API set/validation tests for new Prayers keys and rite restrictions in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Added RAT/AST rendering tests for Prayers include/omit behavior in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
- Backward compatibility notes:
  - Existing services render unchanged unless keys are set.
- Follow-up items:
  - Expand from include/omit to full named-fill templated inserts for local persons/titles.

### 2026-02-23 - Phase 2 templated inserts: Prayers named fills

- Scope: Add text-valued named inserts for Prayers of the People placeholders.
- Option keys added/changed:
  - `prayers.public_service.especially_names` (RAT)
  - `prayers.adversity.especially_names` (RAT/AST)
  - `prayers.departed.especially_names` (RAT/AST)
  - `prayers.saints.named_person` (AST)
- Schema/migrations:
  - No additional schema changes.
- Backend changes:
  - Extended option registry validation to support text-valued options (`input_type=text`, `max_length`) in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_registry.py`.
  - Updated route normalization to be option-key-aware in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_share_routes.py`.
  - Added render logic in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_rendering.py` to inject named values into bracket placeholders and auto-include when names are present unless explicitly set to omit.
- UI changes:
  - Extended service-option modal to support text input mode in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html`.
  - Added Prayers row actions for setting named values (adversity/departed/public-service names, saint name) in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html`.
  - Extended Prayers indicator logic to include text-valued keys in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html`.
- Rendering behavior:
  - Named fills replace placeholder underscores (and `N.` in saints insert) while preserving include/omit control.
  - Explicit `omit` still removes bracketed clause even when a named value exists.
- Tests added/updated:
  - Added route tests for text-valued Prayers keys and max-length validation in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Added RAT/AST rendering tests for named-fill output in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Added service-page action presence assertions for new named-fill controls in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
- Backward compatibility notes:
  - Existing services render unchanged unless named keys are set.
- Follow-up items:
  - Implement office-title/polity substitutions (`President/Sovereign/Prime Minister`, `Archbishop/Bishop/...`) via canonical local profile settings.
