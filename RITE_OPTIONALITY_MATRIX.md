# Rite Optionality Matrix (RAT + AST)

Scope:
- Source pages reviewed: `/service/25/view` (Renewed Ancient Text) and `/service/26/view` (Anglican Standard Text).
- Goal: enumerate configurable optionality and map current Ordinarium support vs gaps.
- Date: 2026-02-23.

Legend:
- `Supported`: first-class in current planner/data model.
- `Partial`: possible via workaround or adjacent feature, but not first-class for the rubric choice itself.
- `Not supported`: no current config surface for the choice.

## Current capability baseline

Already supported in code:
- Row include/exclude and row reordering via `services.text_disabled` and `services.text_order`.
- Lesson reference overrides via `services.lesson_overrides`.
- Offertory sentence selection via `services.offertory_sentence_id`.
- Collect/Proper Preface override via `services.proper_overrides`.
- Arbitrary inserted text via `service_custom_elements`.

## Matrix A: Optionality Universe by Rite

| Rite | Liturgy area | Rubric optionality / swap | Config type | Current support | Current mechanism | Recommended approach |
|---|---|---|---|---|---|---|
| Both | Summary of the Law | Summary of the Law **or** Decalogue | `single_select_block` | Supported | `law.form` controls Summary vs Decalogue rubric rendering | Keep `law.form`; revisit full Decalogue text sourcing if we later add page-100 content directly |
| Both | Kyrie / Trisagion | Multiple Kyrie forms; **or this** Trisagion | `single_select_block` (with nested select) | Supported | `penitential_song.mode` + `kyrie.form` | Keep current model; extend only if additional Kyrie variants are needed |
| Both | Gloria in Excelsis | Gloria **or** other song of praise; may be omitted seasonally | `single_select_enum` | Partial | Can disable row (omit) but cannot represent “other song” as structured choice | Defer for now; keep include/exclude behavior in Phase 1 and revisit with hymn/song modeling |
| Both | Lessons intro/outro | One or more lessons; citation may be added; post-reading response variants; silence may follow | `multi_toggle` + `single_select_block` | Partial | Lessons are separate rows and can be disabled; response/citation/silence choices are not modeled | Add lesson-level options object (citation on/off, response form, silence on/off, lesson-count mode) |
| Both | Lectionary alternatives | Alternate appointed readings/options within a slot | `reading_catalog_select` | Supported (reference-level) | Lesson modal supports `default` / `canonical` / `custom`; canonical alternates are surfaced from calendar-resolved lesson sets and stored as lesson overrides | Keep current picker; optionally evolve to text-id-backed persistence later |
| Both | Psalm slot | Psalm, hymn, or anthem may follow; Gloria Patri may be sung/said | `single_select_enum` + `toggle` | Partial | `psalm.gloria_patri` controls Gloria Patri include/omit; slot content mode not yet modeled | Keep `psalm.gloria_patri`; defer psalm/hymn/anthem slot-content modeling |
| Both | Nicene Creed | Filioque optional: `[and the Son]` | `token_toggle` | Supported | `creed.filioque_clause` include/omit toggle | Keep include/omit toggle; later add named local profile presets if needed |
| Both | Peace | Ministers/People may greet one another | `row_toggle` | Supported | Include/exclude row | Keep row toggle; add display label “Exchange of the Peace” for clarity |
| Both | Comfortable Words | Celebrant may say one **or more** of provided sentences | `multi_select_block` | Supported | `comfortable_words.sentences` stores selected sentence IDs and renders selected subset | Keep as implemented |
| Both | Offertory sentence | Begin with one provided sentence | `catalog_select` | Supported | Offertory sentence picker + `offertory_sentence_id` | Keep as-is; expand labeling/filtering by season/day for usability |
| Both | Offertory rites | Offertory music may be sung; offertory presentation sentence may be said | `toggle` | Partial | Music/presentation optionality is only rubric text | Add optional toggles with planner hints; allow optional inserted text slot |
| Both | Sursum Corda | Dialog may be sung or said | `single_select_enum` | Not supported | Static rubric text | Add `delivery_mode` enum for chant/spoken where useful |
| Both | Prayer of Consecration | People stand or kneel; manual acts options; break may happen here or later | `single_select_enum` + `toggle` | Partial | Can disable whole row only; manual-act timing not represented | Add ceremonial options group (posture/manual acts/fraction timing) |
| Both | Lord’s Prayer | Traditional-language form **or** contemporary-language form | `single_select_block` | Supported | `lords_prayer.form` selector | Keep as implemented |
| Both | Fraction | Two alternative invitations; optional `[Alleluia.]`; seasonal rule for omission/addition | `single_select_block` + `token_toggle` + `rule_driven` | Supported | `fraction.form` + `fraction.alleluia_mode` | Keep as implemented; consider adding rubric-aware defaults at service creation |
| Both | Prayer of Humble Access | May be said | `row_toggle` | Supported | Include/exclude row | Keep as-is |
| Both | Agnus Dei | Use provided text **or** other suitable anthem; sung/said | `single_select_block` + `custom_text_ref` | Partial | Row can be disabled; no structured alternative anthem selection | Add anthem selection mode: default/custom reference/custom text |
| Both | Ministration invitation | Invitation form A **or** B; bracketed optional add-on clauses | `single_select_block` + `token_toggle` + `templated_insert` | Supported | `communion.invitation.form` + `communion.invitation.appended_clause` + `communion.invitation.appended_text` | Keep as implemented; explicit omit/include and optional custom clause text |
| Both | Distribution formulae | Optional longer bracketed words for Body/Blood formulae | `token_toggle` + `templated_insert` | Supported | `communion.distribution.body_clause` + `communion.distribution.body_text` + `communion.distribution.blood_clause` + `communion.distribution.blood_text` | Keep as implemented |
| Both | Communion close | Optional closing scripture sentence | `toggle` + `custom_text_ref` | Not supported | Rubric note only | Add toggle + selectable/typed sentence |
| Both | Post Communion Prayer | Rite prayer **or** prayer from the other rite | `cross_rite_swap` | Supported | `post_communion.form` (`own_rite` / `other_rite`) | Keep as implemented |
| Both | Blessing | This blessing **or** alternate blessing | `single_select_block` | Partial | Can disable entire row; no alternate blessing selection | Add blessing selector + optional custom blessing text |
| Both | Dismissal | Four dismissal options; seasonal alleluia add-on rules | `single_select_block` + `rule_driven` | Supported | `dismissal.form` + `dismissal.alleluia_mode` | Keep as implemented |
| Both | Exhortation | Celebrant may say Exhortation | `toggle` | Not supported | Rubric note only | Add optional row or optional appended element |
| RAT | Prayers of the People | RAT form **or** AST form | `cross_rite_swap` | Supported | `prayers.form` (`rat` / `ast`) swaps section text at render time | Keep as implemented; consider adding swapped-form-specific sub-options later |
| RAT | Prayers of the People | People may add petitions silently/aloud; additional petitions and thanksgivings may be invited | `toggle` + `free_text_list` | Not supported | Rubric note only | Add fields for intercessions mode and optional free-text additions |
| RAT | Prayers of the People | Bracketed local inserts (`[especially ...]`) | `templated_insert` | Partial | `prayers.*.especially_clause` include/omit + named fills implemented | Extend named fills to richer list/profile structures as needed |
| AST | Prayers of the People | AST form **or** RAT form | `cross_rite_swap` | Supported | `prayers.form` (`rat` / `ast`) swaps section text at render time | Keep as implemented; consider adding swapped-form-specific sub-options later |
| AST | Prayers of the People | Additional prayers may be added | `free_text_list` | Supported (custom rows) | Standalone custom elements with section-level quick-add affordances and suggested insertion point | Keep independent custom rows; no fixed anchor |
| AST | Prayers of the People | Placeholder substitutions (`President/Sovereign/Prime Minister`, `Archbishop/Bishop/...`) and bracketed inserts | `templated_insert` + `single_select_enum` | Supported | Bracketed inserts + named fills implemented; civil/clergy substitutions via `prayers.ast.*` keys + `prayers.ast.profile` presets (`american`/`commonwealth`) with American defaults when unset | Extend profile presets if more regional variants are needed |
| AST | Confession invitation | Long invitation **or** short “Let us humbly confess...” | `single_select_block` | Supported | `confession.invitation_form` selector | Keep as implemented |

## Matrix B: Config Type -> Product Strategy

| Config type | Typical rubric pattern | Current support | Recommended persistence model | Recommended UI pattern |
|---|---|---|---|---|
| `row_toggle` | “may be said” for whole section | Supported | Keep `text_disabled` tokens | Existing include checkbox |
| `row_order` | Reorder-able liturgy blocks | Supported | Keep `text_order` tokens | Existing drag/drop |
| `catalog_select` | “use one of provided texts” | Supported (Offertory/Propers) | Keep FK in service row or `service_option_values` | Existing modal picker pattern |
| `single_select_block` | “or this” between fixed alternatives in one section | Not supported | Add keyed enum in `service_option_values` JSON/object | Segment control/radio in row actions |
| `multi_select_block` | “one or more of the following” | Supported (Comfortable Words) | Keyed array in `service_option_values` (`comfortable_words.sentences`) | Checkbox list modal |
| `token_toggle` | Bracketed optional clause `[ ... ]` | Not supported | Add boolean keys per token | Small toggles in row options |
| `templated_insert` | `[especially ______]`, office/title substitutions | Supported (section-scoped) | Use named string fields in `service_option_values` (implemented for Prayers placeholders, AST civil/clergy substitutions, and Communion bracket clause text overrides) | Structured form fields by section |
| `cross_rite_swap` | “or [same section] in the other rite” | Supported (Prayers/Post-Communion) | Enum key in `service_option_values` (`prayers.form`, `post_communion.form`) | Existing row `Set option` modal |
| `free_text_list` | Additional petitions/prayers may be added | Partial | Use `service_custom_elements` and preserve row-order placement | Reuse custom-row workflow, with quick-add action from relevant sections |
| `reading_catalog_select` | Choose among canonical alternate lessons | Supported (reference-level) | Current: store selected canonical reference text in `lesson_overrides`; Future: store text IDs by slot | Modal picker with “default / canonical alternate / custom reference” modes |
| `rule_driven` | Seasonal rules (e.g., Alleluia) | Not supported | `auto/on/off` enum + rule evaluator | Toggle with “Auto by season” default |
| `ceremonial_enum` | Sing/say, stand/kneel, manual-act timing | Not supported | Enum fields grouped by section | Compact “Ceremonial” controls, optional export annotations |

## Recommended implementation order

1. Introduce a generic `service_option_values` JSON column on `services` keyed by stable option IDs.
2. Add a non-destructive render layer that applies option substitutions at render time (planner + view/export), without mutating source `texts.text`.
3. Implement `single_select_block`, `multi_select_block`, and `token_toggle` first (largest current gap).
4. Add `templated_insert` for bracket placeholders and local office-title profiles.
5. Add `cross_rite_swap` and `free_text_list` using independent custom rows for Prayers/Post-Communion.
6. Add `rule_driven` (`auto/on/off`) for alleluia and similar seasonal switches.

## Option key registry (initial)

- Store new values under `services.service_option_values` with stable dotted keys.
- Suggested initial keys:
  - `law.form` (`summary`, `decalogue`)
  - `penitential_song.mode` (`kyrie`, `trisagion`)
  - `kyrie.form` (`traditional`, `contemporary`, `greek`)
  - `lords_prayer.form` (`traditional`, `contemporary`)
  - `fraction.form` (`passover_is_sacrificed`, `passover_lamb_has_been_sacrificed`)
  - `fraction.alleluia_mode` (`auto`, `on`, `off`)
  - `communion.invitation.form` (`gifts_of_god`, `behold_lamb`)
  - `dismissal.form` (`go_forth_name_of_christ`, `go_in_peace_love_serve`, `go_forth_rejoicing`, `let_us_bless`)
  - `dismissal.alleluia_mode` (`auto`, `on`, `off`)
  - `confession.invitation_form` (`long`, `short`)
  - `comfortable_words.sentences` (`matthew_11_28`, `john_3_16`, `first_timothy_1_15`, `first_john_2_1_2`)
  - `prayers.form` (`rat`, `ast`)
  - `post_communion.form` (`own_rite`, `other_rite`)
  - `prayers.ast.profile` (`american`, `commonwealth`)
  - `prayers.ast.civil_leader.name` (text)
  - `prayers.ast.civil_leader.title` (`president`, `sovereign`, `prime_minister`)
  - `prayers.ast.clergy.name` (text)
  - `prayers.ast.clergy.title` (`archbishop`, `bishop`, `priest`, `deacon`)

## Execution checklist (Phase 1 / Phase 2)

### Phase 1 (core option engine + highest-value controls)

- [x] Migration: add `services.service_option_values` JSON column (default `{}`) and wire it into load/save paths.
- [x] Rendering: implement option-aware, non-destructive transformers in the text rendering pipeline.
- [x] API/UI: add controls for:
  - [x] `confession.invitation_form`
  - [x] `lords_prayer.form`
  - [x] `dismissal.form`
  - [x] `fraction.form`
  - [x] `fraction.alleluia_mode`
  - [x] `dismissal.alleluia_mode`
  - [x] `communion.invitation.form`
- [x] API/UI: add token toggles for bracketed clauses (Filioque, Communion formula additions, etc.) (All bracketed tokens currently present in RAT/AST source texts are now wired with API/UI controls, including Prayers adversity clause).
- [x] Tests: add unit + integration coverage for default behavior, explicit overrides, and seasonal `auto` modes.

### Phase 2 (expanded content selection + rite swaps + templated inserts)

- [x] Add `multi_select_block` support for Comfortable Words (one or more).
- [x] Add `cross_rite_swap` rendering for Prayers and Post-Communion (render swapped text in full).
- [x] Add `templated_insert` fields for bracket placeholders and office-title substitutions (Prayers named fills + AST office-title substitutions/profile defaults + Communion clause text overrides complete).
- [x] Add AST one-click profile presets with default substitutions in prayer text (`prayers.ast.profile` with American default and Commonwealth alternative).
- [x] Add canonical lesson alternative picker (`reading_catalog_select`) before custom free-text override.
- [x] Add quick-add custom-row affordances from relevant sections (no fixed insertion anchor).
- [ ] Revisit deferred Gloria modeling with hymn/song workflow (deferred by decision; no implementation in current phase).

### Phase 3 (clean up, bug fixes, polish, etc.)

- [x] The live preview shown in option modals should use the same CSS rendering as standard text views (e.g., pre + code sections are rendering using "standard" CSS instead of our custom text rendering rules).
- [x] Please use the standard (smaller) rounded corners for section borders within modals.
- [x] Ensure that modal selects and inputs are not allowed to stretch wider than the width of the modal (and any modal section constraints).
- [x] Instead of saying "Using the other rite's prayer" (e.g., on the options for the post-communion prayer), update the language to refer to the specific alternate rite (e.g., when on a RAT rite service, it would read "Using the Anglican Standard Text prayer").
- [x] Move other existing options (e.g., Override proper, Override passage) into the same shared options modal approach that we implemented for all new options. The modal for these should also include live previews.
- [x] The Kyrie / Trisagion binary option doesn't appear to be implemented (at least in the UI).
- [x] The Summary of the Law / Decalogue binary option doesn't appear to be implemented (at least in the UI).
- [x] The ability to use a canonical alternative for any of the Lessons should only be enabled if there is a canonical alternative.
- [x] I'm not seeing the gloria patri option for the Psalm.
- [x] Double check that inapplicable rubrics are overridden based on selections made — for example, if an alleluia mode is set on The Dismissal, the remainder of the liturgy text explaining the use of alleluias through the end of that element does not need to be shown.

## Open decisions to annotate

- Should ceremonial choices (stand/kneel, sing/say) affect only planner metadata, or also generated text output?
    - Answer: They should update both locations, however, we should have a generic option that retains the default language.
- For cross-rite swaps, should we render the swapped text in full, or keep a pointer note plus linked section?
    - Answer: We should render the swapped text.
- For bracket tokens, should defaults follow rite/season automatically unless explicitly overridden?
    - Answer: Yes, that is a good idea.
- Should custom added prayers be inserted into a fixed anchor point (inside section), or remain independent custom rows?
    - Answer: A fixed anchor point is going to be too inflexible, I believe, so let's just go with custom rows.

## Additional notes on implementation approach

- Wherever possible, we should render changes in a non-destructive way. E.g., if a default rubric says "stand or kneel" and the user sets the config to "kneel", it would be preferable to substitute/map the default language to the config as opposed to changing the source value stored in the database for the liturgical element.
- Due to the complexity of these changes, we should keep track as we make changes and document the specific changes made.
- Tracking artifact: `docs/optionality-implementation-log.md`.
