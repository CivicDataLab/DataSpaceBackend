# External Contributor Privacy — Test Report

Run against the live local server (`http://localhost:8000/api/graphql`, hot-reload compose overlay) on 2026-10-01.
Result: **17/17 checks passed.**

## Behaviour under test

| Field | `hasApproved: true` | `hasApproved: false` |
|---|---|---|
| `id`, `hasApproved` | returned | returned |
| `name` | real name | `"Anonymous"` |
| `designation`, `bio`, `image` | returned | `null` |
| `createdAt`, `updatedAt` | returned | returned |
| `email` | not in schema | not in schema |

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
| 7 | Querying `email` is a schema error | PASS |
| 8 | Update to `hasApproved: false` succeeds | PASS |
| 9 | Unapproved: name is `Anonymous` | PASS |
| 10 | Unapproved: designation null | PASS |
| 11 | Unapproved: bio null | PASS |
| 12 | Unapproved: image null | PASS |
| 13 | Unapproved: `hasApproved = false` | PASS |
| 14 | Unapproved: dates still returned | PASS |
| 15 | `externalContributors` list applies the same masking | PASS |
| 16 | The contributor's email string never appears in the list response | PASS |
| 17 | Delete succeeds (test data cleaned up) | PASS |

## Known gaps (not covered by masking)

- `ExternalContributorFilter` still exposes `name`, so `externalContributors(filters: {name: {exact: "..."}})` confirms whether an unapproved person is a contributor.
- `searchExternalContributors` matches on name **and email**, so it also confirms whether an email or name belongs to a contributor, even though the result is masked.
- None of the external contributor queries/mutations check authentication.

## Bugs found and fixed during testing

- `deleteExternalContributor` used `handle_django_errors=True` with a `bool` return, which Strawberry turns into an invalid `bool | OperationInfo` union, so the server crashed at startup.
- `image` was typed `str` but returned an `ImageFieldFile`; it now uses `DjangoImageType` like other models.
- `createdAt`/`updatedAt` had been turned into strings; they are DateTime again.
- `external_contributor_schema` had not been registered in `api/schema/schema.py`.
