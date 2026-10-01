# External Contributor Privacy — Test Report

Run against the live local server (`http://localhost:8000/api/graphql`, hot-reload compose overlay) on 2026-10-01.
Result: **18/18 checks passed** (plus 13/13 for the logged-in collaborative flow below).

## Behaviour under test

| Field | `hasApproved: true` | `hasApproved: false` |
|---|---|---|
| `id`, `hasApproved` | returned | returned |
| `name` | real name | `"Anonymous"` |
| `email`, `designation`, `bio`, `image` | returned | `null` |
| `createdAt`, `updatedAt` | returned | returned |

`createExternalContributor` always sets `hasApproved: true`; `updateExternalContributor` can toggle it.

## Results

| # | Check | Result |
|---|---|---|
| 1 | Create returns no errors | PASS |
| 2 | Create sets `hasApproved = true` | PASS |
| 3 | Approved: real name returned | PASS |
| 4 | Approved: designation returned | PASS |
| 5 | Approved: bio returned | PASS |
| 6 | Approved: dates returned | PASS |
| 7 | Approved: email returned | PASS |
| 8 | Update to `hasApproved: false` succeeds | PASS |
| 9 | Unapproved: name is `Anonymous` | PASS |
| 10 | Unapproved: designation null | PASS |
| 11 | Unapproved: email and bio null | PASS |
| 12 | Unapproved: image null | PASS |
| 13 | Unapproved: `hasApproved = false` | PASS |
| 14 | Unapproved: dates still returned | PASS |
| 15 | `externalContributors` list applies the same masking | PASS |
| 16 | An unapproved contributor's email never appears in the list response | PASS |
| 17 | Delete succeeds (test data cleaned up) | PASS |

## Logged-in collaborative flow (13/13 passed)

Run over HTTP with a real Keycloak token for a platform user.

| Check | Result |
|---|---|
| Create contributor (approved) | PASS |
| `updateCollaborative` sets `designation` and attaches the contributor via `externalContributorIds` | PASS |
| `collaborative { designation externalContributors { ... } }` returns no errors | PASS |
| Collaborative designation saved | PASS |
| Approved contributor shown in full under the collaborative | PASS |
| After unapproving: shown as `Anonymous`, personal fields null | PASS |
| After unapproving: dates still returned | PASS |
| After unapproving: email absent from the response | PASS |
| (Run before email was exposed) email not queryable | PASS |
| Re-approving restores the data | PASS |
| Search by name finds the contributor | PASS |
| Search by email returns nothing | PASS |
| Cleanup (collaborative and contributor deleted) | PASS |

## Search and filter

- `searchExternalContributors` matches by name only (unapproved results come back as Anonymous); it never matches on email.
- `externalContributors` can only be filtered by `id`, so filtering can't reveal a hidden name.

No login is required for these endpoints, and who can set `hasApproved` is not restricted.

## Bugs found and fixed during testing

- `deleteExternalContributor` used `handle_django_errors=True` with a `bool` return, which Strawberry turns into an invalid `bool | OperationInfo` union, so the server crashed at startup.
- `image` was typed `str` but returned an `ImageFieldFile`; it now uses `DjangoImageType` like other models.
- `createdAt`/`updatedAt` had been turned into strings; they are DateTime again.
- `external_contributor_schema` had not been registered in `api/schema/schema.py`.
