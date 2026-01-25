# TODO

Remaining work and follow-ups.

## High-level

- Implement export formats: PDF (already supported through custom print stylesheet, but would be nice to give download option) and DOCX.
- Add additional liturgy templates (Morning Prayer, Compline, funerals, weddings; other prayer books/sacramentaries/missals).
- Implement additional export formats and integrations: Planning Center, ProPresenter, etc.
- Add team accounts (shared services and element libraries).
- Add collaboration features for team accounts: comments, approvals, version history.

## Details

### Planning Center API (one-way push)
Goal: map an Ordinarium `/service` plan to a Planning Center Services plan, then create/update the PCO service order to match Ordinarium elements.

#### Open items
- Confirm OAuth 2 flow requirements for user-linked accounts (scopes, refresh token handling, org selection).
- Confirm the exact Services API endpoints and JSON:API shapes for:
  - Service Types
  - Plans
  - Plan Times (if needed)
  - Plan Items (create/update/delete)
  - Item reorder action
- Decide on matching strategy for plans (date-only vs. date+title vs. explicit linkage).
- Define a stable mapping between Ordinarium element types and PCO item types/fields (with fallback).
- Decide how to handle re-sync (replace all items vs. diff/merge vs. "upsert + reorder").
- Identify required permissions for creating plans/items under a service type (editor/admin).
- Decide whether to support PCO plan templates (import) or always build from scratch.
- Confirm rate limits and any pagination needs for large service types.

#### Planning steps
- Draft a minimal data model for account linkage and mapping:
  - PCO org + service type mapping per Ordinarium service context.
  - Optional per-plan mapping: Ordinarium service instance ↔ PCO plan id.
- Sketch the sync pipeline:
  - Fetch/resolve service type.
  - Resolve plan by date or mapping; create if missing.
  - Build item payloads from Ordinarium elements.
  - Apply updates and reorder items.
- Define error handling rules (auth expired, permission denied, partial item failure).
- Add UX requirements for:
  - Connect Planning Center account.
  - Choose service type.
  - Preview changes and "push" confirmation.
- Define audit/logging expectations (push timestamp, plan id, item counts).

#### Build details (future implementation)
- Add OAuth config + token storage (refresh tokens) in `instance/` or encrypted storage.
- Add PCO integration module (e.g., `ordinarium/pco.py`) to wrap API calls.
- Add database tables/migrations for:
  - linked accounts
  - service type mappings
  - plan mappings (optional)
  - sync audit log
- Add routes/UI:
  - `/settings/planning_center` for linking and selecting service type.
  - `/service/<id>/push` action to create/update plan items.
- Add background/task handling if pushing can be slow (optional).
- Add tests:
  - Mapping rules for element → item payload.
  - Sync pipeline behavior (create vs update vs reorder).
  - OAuth token refresh handling.
