# Publications (UI "Resource") — backend

> Part of feature: **resources** · siblings: `DataSpaceFrontend/app/[locale]/(user)/publications/architecture.md` (frontend slice)

## Overview

A **Publication** is a new top-level entity, peer to Datasets and AI Models: a container for human-authored content (reports, research, findings). It has typed metadata, an ordered list of heterogeneous **content blocks** (a file XOR a YouTube embed each), a publish/unpublish toggle, its own listing + global search presence, and it can be pulled into Use Cases and Collaboratives.

**Naming:** the user-facing entity is **"Resource"**, but the name `Resource` was already taken in this repo (the file-inside-a-dataset). So the entity is `Publication` everywhere in code — Django model, GraphQL type, table `publication`, ES index `publication`, SDK client, URL path `/publications`. The UI always renders "Resource".

### How the repos connect

- **DataExBackend** owns the whole data/API/search/SDK slice (this doc).
- **DataSpaceFrontend** (sibling doc) owns the create/edit/publish flow, detail page, listing, cards, and the Resource picker inside Use Case / Collaborative editors. It talks to the backend over GraphQL (`/api/graphql`) for CRUD/detail/list and REST for search (`/api/search/publication/`) and gated file download (`/api/publications/blocks/<id>/download/`).
- Request flow for a create: FE collects metadata → `createPublication` mutation → DRAFT row → FE adds blocks via `addPublicationFileBlock` / `addPublicationYoutubeBlock` (multipart for files) → `publishPublication`. A published resource then appears in the listing/search and is linkable from a Use Case / Collaborative.

## Submodule map

| Submodule | Trigger |
|---|---|
| CRUD + publish | GraphQL `publication_schema.py` (create/update/publish/unpublish/delete + list/detail) |
| Content blocks | GraphQL block mutations (add file/youtube, replace, remove, reorder) |
| Block-file download | REST `GET /api/publications/blocks/<block_id>/download/` |
| Search | REST `GET /api/search/publication/` + unified `GET /api/search/unified/` |
| Index sync | model signals (`publication_signals.py`) + `search_index --rebuild/--populate` |
| UC/Collab linking | GraphQL link trios in `usecase_schema.py` / `collaborative_schema.py` |
| SDK | `dataspace_sdk/resources/publications.py` |
| Resource Type lookup | Django admin + `seed_resource_types` command |

---

## Submodule: CRUD + publish

### Trigger
GraphQL: `createPublication`, `updatePublication`, `publishPublication`, `unpublishPublication`, `deletePublication` mutations; `getPublication(publicationId)` and `publications(filters, pagination, order, includePublic)` queries. Flow file: `api/schema/publication_schema.py`.

### Business use case
Any individual or org account creates a Resource, edits its metadata across subpages, and publishes/unpublishes it with a simple toggle (no moderation). Auditors (role `can_change=False`) can read but not edit/publish.

### Flow (English)
- **create:** reject missing/invalid metadata at the boundary → create a DRAFT owned by the org (from the request's organization header) or the user → wire sector/geography tags.
- **update:** load or 404 → apply only the provided fields (each validated) → save.
- **publish / unpublish:** load or 404 → flip `status`; the index signal adds/drops the search document.
- **delete:** load or 404 → hard delete (FK cascade drops blocks; M2M link rows auto-clear).
- **list:** scope to org / owner / anonymous, optionally union the public set, apply filters + ordering, enforce a bounded page window.
- **detail:** gated by `AllowPublishedPublications` — a published resource is world-readable; a draft only to owner/org/superuser.

### Helpers
All Tier-2, in `api/services/publication_service.py`:
- `validate_publication_metadata(...) -> ResourceType` — required-field + typed validation (license in `DatasetLicense`, active resource type, URL shape); raises field-keyed `ValidationError`; returns the resolved active resource type.
- `create_publication(...) -> Publication` — create DRAFT + set M2M tags.
- `apply_publication_update(publication, ...) -> Publication` — partial update, validating each provided field; never blanks untouched columns.
- `set_publication_status(publication, status) -> Publication`.
- `get_scoped_publications(user, organization, include_public) -> QuerySet` — org/owner/anonymous scoping + published union, ordered `-modified`, `.distinct()`.
- `resolve_pagination(offset, limit) -> (offset, limit)` — default page size + hard max, so a listing is never unbounded.
- `is_publication_published(publication) -> bool`.

Permissions (Tier-2, `authorization/permissions.py`): `CreatePublicationPermission`, `ChangePublicationPermission`, `DeletePublicationPermission`, `PublishPublicationPermission` (name-based admin/editor/owner), `AllowPublishedPublications`. All key on `publication_id` (or the update input's id, or a block's parent), keep the individual-owner branch, and drop Dataset's share-model fallback.

### Data model
`Publication` (table `publication`): UUID PK, `title`, `description` (Text), `slug` (unique, counter-dedupe on collision), `organization`/`user` nullable FKs (`SET_NULL`), `authors` (JSON list), `publication_date` (Date), `license` (reuses `DatasetLicense` choices), `external_source_link` (URL), `status` (`PublicationStatus` DRAFT/PUBLISHED), `resource_type` FK (`PROTECT`), `sectors`/`geographies` M2M, `download_count`, `created`/`modified`.
`ResourceType` (table `resource_type`): UUID/name(unique)/slug + `is_active` (adapted from `Sector`, no parent self-FK).
`UseCase`/`Collaborative`: gain a `publications` M2M.

### Indexing & performance
`Publication.Meta.indexes`: `(organization, -modified)`, `(user, -modified)`, `(status)` — matching the dashboard/listing query shapes. `slug` unique (detail lookup), org/user/resource_type FKs auto-indexed. No standalone org/user/resource_type indexes (composites/FK cover them). Sector/geography filters are ES-backed → no PG indexes. Pagination is server-enforced (default 20, max 100). `PublicationBlock.Meta.indexes`: `(publication, position)`.
**Migrations:** none committed — this repo auto-generates migrations at deploy (`docker-entrypoint.sh` runs `makemigrations --noinput` then `migrate`); the committed `0001_initial` is a stale stub and `authorization` has no migrations dir. All additions are additive (new tables + new nullable columns + additive M2M join tables), safe on large tables. See project-memory (2026-07-18).

### Security
Every query is org/user-scoped; anonymous sees only PUBLISHED. Cross-org request outcomes: mutating another org's DRAFT → permission denied (the resolver 404s the draft at read); mutating a PUBLISHED one → permission denied. Auditor (`can_change=False`) → read allowed, edit/publish denied. Publish gated to role **names** admin/editor/owner (mirroring Dataset). Individual resources restricted to their owner. All scoping is centralized in the permission classes — no inline role logic in resolvers.
The **linked-project fields** (`linkedUsecases` / `linkedCollaboratives` / `linkedCount` on `TypePublication`) are the owner's "linked to N" flag: they're gated to the owner / org member / superuser (`_caller_can_see_links`) **and** filtered to PUBLISHED projects, so a public resource never leaks the title of a private draft project (possibly in another org) that references it.

### SDK impact
SDK: **yes.** `dataspace_sdk/resources/publications.py` `PublicationClient` — `search` (REST), `get_by_id`/`list_all`/`get_organization_publications`/`create`/`update`/`delete` (GraphQL). Registered in `client.py` `__init__` and `set_organization`.

### Tests

#### Layer 1 — DB helper tests (`tests/test_publication_models.py`)
Slug dedupe (distinct slugs, unicode title); ownership property; ResourceType uniqueness/slug/`is_active`/active-query; block file/youtube storage; file-XOR-youtube CheckConstraint (both/neither rejected); block position ordering; delete cascade; seed idempotency; DRAFT/download_count/authors defaults.

#### Layer 2 — Non-DB helper tests
`tests/test_youtube_url.py` — id extraction across watch/youtu.be/embed, rejects non-YouTube, malformed, and non-http(s) schemes (javascript: stored-XSS guard). `tests/test_publication_uploads.py` — extension allow-list, 50 MB cap, PDF magic-byte sniff.

#### Layer 3 — Flow tests (in `tests/schema/test_publication_schema.py`, `tests/test_publication_blocks.py`)
Create org/individual → DRAFT; invalid metadata → no create; block add happy/invalid; reorder/renumber; replace-file (same id, old file gone).

#### Layer 4 — Backend API e2e (`tests/schema/test_publication_schema.py`, `tests/test_publication_blocks.py`)
CRUD; role gating (editor edits, auditor denied edit/publish but reads); publish/unpublish; cross-org denial for update/delete/publish + block add/remove; anonymous sees published detail, denied draft; org-scoped and anonymous (published-only) listings; block-file download gate (published→200 + count increment, draft anon/cross-org→404, owner draft→200, PDF inline).

#### Layer 4 — Search (`tests/test_publication_search.py`)
Index-decision (published indexed, draft not); re-index mapping incl. ResourceType/Sector/Geography/Org; signal predicate. Full ES query/filter/pagination behaviour runs against a live cluster (ES is disabled in the deterministic layers).

#### Layer 4 — Linking (`tests/test_publication_linking.py`)
Only-published-linkable guard (UC + Collab); stale-link (unpublish/delete hides, re-publish restores); linked-count; IDOR guard (non-owner can't link); the intentional cross-org affordance (org B UC links org A published resource).

#### Layer 5 — API user journey (`tests/journeys/publications/`)
`create-blocks-publish` and `link-unpublish-relink` (scripted, on-demand).

#### Layer 6 — Browser e2e
n/a in this repo — belongs to the frontend slice's doc.

### LLM-judge points
n/a — all assertions are deterministic.

---

## Limitations & future work

- **UC/Collab search does not index linked Resources.** A use case / collaborative is not findable by a linked Resource's title, and their `dataset_count` excludes Resources. Deferred by design.
- **Resource search matches name/description + the three facets only.** Author / date / usage-rights columns and block content are not indexed in v1.
- **Preview fidelity:** slide decks / DOCX / PPT are download-only (only PDF + YouTube render inline).
- **No versioning** for re-uploaded block files (in-place replace).
- **The dataset link trio's pre-existing IDOR** (no container-authorization check) is not fixed here — only the new publication trio is authorized. Follow-up: apply `assert_can_manage_links` to the dataset trio too.
- **Frontend is implemented** (see the sibling FE doc). Its Layer 6 browser flows and the visual checklist are written but not yet walked (agents don't run a visual pass on their own) — run on request.
- **The list resolver trusts the request's `organization` header without a membership check** — a faithful mirror of the existing dataset/aimodel/usecase list resolvers and the shared middleware (`api/utils/middleware.py`, which still carries a `# TODO: resolve auth_token`). This feature follows the platform pattern; if org membership is not enforced on that header upstream, a signed-in user could list another org's drafts by setting the header. The correct fix is at the shared middleware layer (so all entities are fixed together), not per-endpoint — deliberately **not** patched here to avoid divergence and false security. Flagged for a platform-level decision.
- **Frontend (Phases 7–8), the two Layer 5 journey scripts, and the FE architecture doc are not yet implemented** — the backend is complete and shippable; the UI is the remaining slice.
