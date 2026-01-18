# TODO

Reference list of findings from the review for future follow-up. Context notes:
- Non-observance services are not a current use case (may be in the future).
- `markdown_template` is admin-controlled content; user content uses the safe filter.
- Modern browser support is acceptable (CSS nesting is OK for now).

## Critical
None

## High
None

## Medium
- Keep an eye on `markdown_template` usage if any content becomes user-editable or untrusted in the future (SSTI/XSS risk).
  - Locations: `ordinarium/__init__.py:51-55`, `ordinarium/templates/page.html:7-11`.

## Low
- `tests/test_ics_alignment.py` depends on a live external ICS feed and can be flaky; consider marking as integration/offline or skipping by default in CI.
  - Location: `tests/test_ics_alignment.py:1-170`.
