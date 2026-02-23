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

### 2026-02-23 - Phase 2 templated inserts: AST polity/title substitutions

- Scope: Implement AST Prayers placeholder substitutions for civil-leader/clergy names and titles.
- Option keys added/changed:
  - `prayers.ast.civil_leader.name` (text)
  - `prayers.ast.civil_leader.title` (enum: `president` / `sovereign` / `prime_minister`)
  - `prayers.ast.clergy.name` (text)
  - `prayers.ast.clergy.title` (enum: `archbishop` / `bishop` / `priest` / `deacon`)
- Schema/migrations:
  - No additional schema changes.
- Backend changes:
  - Added option definitions/validation in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_registry.py`.
  - Added AST profile substitution rendering in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_rendering.py` for:
    - `especially N, our President/Sovereign/Prime Minister`
    - `servant(s) N, our Archbishop/Bishop/Priest/Deacon, etc.`
- UI changes:
  - Added AST Prayers row actions in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html` for civil/clergy name/title settings.
  - Extended Prayers indicator logic to include new AST profile keys in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html`.
- Rendering behavior:
  - User-selected names/titles replace AST slash placeholders non-destructively at render time.
  - Unset keys preserve original source wording.
- Tests added/updated:
  - Added API update/validation tests for AST profile keys and rite restrictions in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Added rendering tests for AST profile substitutions in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Added service-page action presence checks for new AST profile controls in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
- Backward compatibility notes:
  - Existing services remain unchanged unless new keys are set.
- Follow-up items:
  - Add optional profile presets that set a coherent civil/clergy combination in one selection.

### 2026-02-23 - Phase 2 templated inserts: AST profile presets + default prayer substitutions

- Scope: Add one-click AST profile selection and make AST prayer title substitutions default to profile values when unset.
- Option keys added/changed:
  - `prayers.ast.profile` (enum: `american` / `commonwealth`)
- Schema/migrations:
  - No additional schema changes.
- Backend changes:
  - Added `prayers.ast.profile` definition/validation in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_registry.py`.
  - Extended AST substitution rendering in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_rendering.py` to:
    - Resolve selected profile (`american` default when unset/invalid)
    - Apply profile title defaults (`President/Bishop` vs `Sovereign/Archbishop`)
    - Keep per-field title/name overrides authoritative when present
  - Updated override entry guard so substitutions still run when `service_option_values` is `{}` in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_rendering.py`.
- UI changes:
  - Added AST Prayers action for `Set AST profile` in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html`.
  - Extended Prayers indicator logic to include `prayers.ast.profile` in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html`.
- Rendering behavior:
  - AST prayer text now defaults to profile-resolved substitutions even with no explicit AST keys set:
    - Default profile: `american` -> `N, our President` and `N, our Bishop`
    - Optional profile: `commonwealth` -> `N, our Sovereign` and `N, our Archbishop`
  - Explicit civil/clergy name/title overrides still supersede profile defaults.
- Tests added/updated:
  - Added API update/validation coverage for `prayers.ast.profile` in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Added rendering tests for:
    - default American substitutions with no AST options set
    - Commonwealth profile defaults
    - explicit name/title override precedence
- Backward compatibility notes:
  - AST prayer output now normalizes slash placeholders into concrete titles by default; no source text is mutated.
- Follow-up items:
  - Expand profile catalog only if additional regional presets are needed.

### 2026-02-23 - Phase 2 cross-rite swaps: Prayers + Post Communion

- Scope: Implement render-time swap controls for Prayers of the People and Post Communion Prayer so either rite can render the corresponding section from the other rite.
- Option keys added/changed:
  - `prayers.form` (enum: `rat` / `ast`)
  - `post_communion.form` (enum: `own_rite` / `other_rite`)
- Schema/migrations:
  - No additional schema changes.
- Backend changes:
  - Added option definitions/validation in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_registry.py`.
  - Added cross-rite source loading and swap application in `/Users/rwillers/Desktop/Ordinarium/ordinarium/text_rendering.py`:
    - loads opposite-rite text blocks for `The Prayers of the People` and `The Post Communion Prayer`
    - applies section swap non-destructively before section-level option transforms
  - Updated rendered-ordinaries pipeline so option transforms are applied pre-template-render for consistency across view/export/sync paths in `/Users/rwillers/Desktop/Ordinarium/ordinarium/text_rendering.py`.
- UI changes:
  - Updated planner row option mapping in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html`:
    - Prayers primary option key -> `prayers.form`
    - Post Communion row now supports `post_communion.form` via row `Set option`
  - Updated client-side indicator logic for the Prayers row primary key in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html`.
- Rendering behavior:
  - `prayers.form` now swaps the full Prayers section text between RAT/AST at render time.
  - `post_communion.form=other_rite` now swaps the full Post Communion Prayer text to the other rite at render time.
  - Source `texts.text` remains unchanged; swaps are render-only.
- Tests added/updated:
  - Added API update/validation coverage for `prayers.form` and `post_communion.form` in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Added service page assertions for row option bindings to new keys in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Added rendering tests verifying both RAT->AST and AST->RAT section swaps for Prayers and Post Communion in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
- Backward compatibility notes:
  - Existing services render unchanged unless one of the new cross-rite swap keys is set.
- Follow-up items:
  - Add swapped-form-specific optional controls where rites differ (for example RAT-only public-service insert controls when AST services swap to RAT Prayers).

### 2026-02-23 - Phase 2 multi-select blocks: Comfortable Words

- Scope: Implement one-or-more sentence selection for Comfortable Words.
- Option keys added/changed:
  - `comfortable_words.sentences` (multi-select array)
- Schema/migrations:
  - No additional schema changes.
- Backend changes:
  - Added multi-select option definition and choices in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_registry.py`.
  - Extended option normalization/validation for `input_type=multi_select` in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_registry.py`.
  - Added render transform in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_rendering.py` to render only selected Comfortable Words sentence blocks while preserving section intro text.
- UI changes:
  - Bound Comfortable Words row to `comfortable_words.sentences` in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html`.
  - Extended service-option modal to support multi-select checkbox controls in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html`.
- Rendering behavior:
  - When set, only selected Comfortable Words sentence/ref blocks are rendered (in canonical order).
  - When unset, source text is unchanged and all four sentence blocks remain.
- Tests added/updated:
  - Added API update/storage test for `comfortable_words.sentences` in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Added invalid-value test coverage for malformed multi-select payloads in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Added service-page binding assertion for Comfortable Words option key in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Added rendering test for selected Comfortable Words subset in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
- Backward compatibility notes:
  - Existing services render unchanged unless `comfortable_words.sentences` is set.
- Follow-up items:
  - Reuse multi-select support for additional “one or more” rubric patterns as they are implemented.

### 2026-02-23 - Phase 2 reading catalog select: canonical lesson alternates

- Scope: Add lesson-level canonical alternate picking before free-text custom override.
- Option keys added/changed:
  - None in `service_option_values`; implemented in lesson override workflow.
- Schema/migrations:
  - No additional schema changes.
- Backend changes:
  - Added canonical lesson option resolution helpers in `/Users/rwillers/Desktop/Ordinarium/ordinarium/plan_lessons.py`:
    - `_resolve_lesson_reference_options`
    - `_resolve_lesson_reference_alternates`
  - Refactored default lesson selection to reuse options resolution in `/Users/rwillers/Desktop/Ordinarium/ordinarium/plan_lessons.py`.
  - Exposed canonical lesson alternates in planner context via `/Users/rwillers/Desktop/Ordinarium/ordinarium/plan_context.py`.
  - Extended lesson save route in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_share_routes.py`:
    - supports `lesson_mode=canonical`
    - validates submitted canonical value against computed alternates
    - stores selected canonical reference in `lesson_overrides`.
- UI changes:
  - Extended lesson modal in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html` to include:
    - `Use canonical alternate` mode
    - canonical alternate `<select>` field
  - Added planner-side JS wiring for mode toggling and canonical option population from `lesson_alternate_options`.
- Rendering behavior:
  - Canonical lesson picks flow through existing `lesson_overrides` rendering path and appear in view/export the same as custom overrides.
  - Default behavior remains unchanged when no override is selected.
- Tests added/updated:
  - Added canonical lesson route acceptance/rejection tests (with deterministic alternates via monkeypatch) in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Added service-page assertion for canonical lesson mode UI presence in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
- Backward compatibility notes:
  - Existing `lesson_overrides` values continue to work unchanged.
  - Canonical selections are stored as reference strings (not text IDs) in current implementation.
- Follow-up items:
  - Consider text-id-backed persistence for canonical picks to improve long-term stability against formatting changes.

### 2026-02-23 - Phase 2 free-text list UX: section-level quick-add custom rows

- Scope: Add quick-add custom row affordances from relevant sections without introducing fixed insertion anchors.
- Option keys added/changed:
  - None.
- Schema/migrations:
  - No additional schema changes.
- Backend changes:
  - No API/data-model changes; reused existing custom element insert flow.
- UI changes:
  - Added section-level quick-add actions in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html`:
    - `Quick add additional prayer` (Prayers of the People)
    - `Quick add communion sentence` (Ministration of Communion)
    - `Quick add alternate blessing` (Blessing)
  - Extended custom-element modal open flow to accept suggested title/text from action metadata while keeping insertion point as the selected row token.
- Rendering behavior:
  - Custom rows continue to render as independent elements in plan order.
  - Quick-add now pre-fills suggested content and insertion point, but users can freely edit title/text and re-order.
- Tests added/updated:
  - Added service-page assertions for quick-add action presence in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
- Backward compatibility notes:
  - Existing custom rows and add/edit flows remain unchanged; quick-add is additive UI behavior only.
- Follow-up items:
  - Consider adding more section-specific quick-add templates once usage patterns are known.

### 2026-02-23 - Phase 2 templated inserts: Communion clause text overrides

- Scope: Complete `templated_insert` coverage for bracketed clauses outside Prayers by allowing explicit replacement text in Communion invitation/distribution formulas.
- Option keys added/changed:
  - `communion.invitation.appended_text` (text)
  - `communion.distribution.body_text` (text)
  - `communion.distribution.blood_text` (text)
- Schema/migrations:
  - No additional schema changes.
- Backend changes:
  - Extended Communion clause rendering in `/Users/rwillers/Desktop/Ordinarium/ordinarium/service_option_rendering.py`:
    - explicit include/omit modes still supported
    - custom text now replaces bracket content when set
    - explicit `omit` continues to take precedence over custom text
    - when text is set and no include/omit mode is set, clause auto-includes
- UI changes:
  - Added planner row actions in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html`:
    - `Set invitation clause text`
    - `Set Body formula text`
    - `Set Blood formula text`
  - Extended Communion row “configured” indicator logic to include these text keys.
- Rendering behavior:
  - Communion bracket clauses can now be rendered as:
    - omitted
    - included with source bracket text
    - included with customized replacement text
- Tests added/updated:
  - Added API update/storage assertions for new Communion text keys in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Added invalid-value tests for max-length enforcement on the new text keys in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Added service-page assertions for new row action labels in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
  - Added render tests for custom text replacement, auto-include behavior, and omit precedence in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
- Backward compatibility notes:
  - Existing services remain unchanged unless new text keys are set.
- Decision note:
  - Deferred item retained: Gloria/hymn workflow remains intentionally out of scope for this phase.

### 2026-02-23 - Phase 1 API/UI parity: remaining bracket token toggle exposure

- Scope: Close the remaining API/UI gap for bracketed-token toggles by exposing Prayers adversity clause control in planner actions and indicator logic.
- Option keys added/changed:
  - No new keys; wired existing key:
    - `prayers.adversity.especially_clause`
- Schema/migrations:
  - No additional schema changes.
- Backend changes:
  - No backend registry/render changes required; key already supported.
- UI changes:
  - Added Prayers row action `Set adversity clause` in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html`.
  - Updated Prayers row configured-indicator logic to include `prayers.adversity.especially_clause` in `/Users/rwillers/Desktop/Ordinarium/ordinarium/templates/service.html`.
- Tests added/updated:
  - Extended service-page option action presence test for `Set adversity clause` in `/Users/rwillers/Desktop/Ordinarium/tests/test_services.py`.
- Backward compatibility notes:
  - Existing services are unaffected; this is UI exposure/visibility parity for an already-supported option key.
