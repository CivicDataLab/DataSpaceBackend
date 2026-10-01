# External Contributor Privacy — Test Report

Run on 2026-10-01 against the local server (`http://localhost:8000/api/graphql`, hot-reload compose overlay) at commit `adaaaf4`.

**Result: 32/32 checks passed** (Suite A 18/18, Suite B 14/14).

## Expected behaviour

| Field | `hasApproved: true` | `hasApproved: false` |
|---|---|---|
| `id`, `hasApproved` | returned | returned |
| `name` | real name | `"Anonymous"` |
| `email`, `designation`, `bio`, `image` | returned | `null` |
| `createdAt`, `updatedAt` | returned | returned |

- `createExternalContributor` always sets `hasApproved: true`; `updateExternalContributor` can toggle it.
- `searchExternalContributors` matches by name only, never email. Unapproved matches come back masked.
- `externalContributors` can only be filtered by `id`.
- No login is required for the external contributor endpoints.

## Suite A — external contributor API, no login (18/18)

| # | Check | Result |
|---|---|---|
| 1 | Create returns no errors | PASS |
| 2 | Create sets `hasApproved = true` | PASS |
| 3 | Approved: real name | PASS |
| 4 | Approved: designation | PASS |
| 5 | Approved: bio | PASS |
| 6 | Approved: dates | PASS |
| 7 | Approved: email | PASS |
| 8 | Update to `hasApproved: false` succeeds | PASS |
| 9 | Unapproved: name is `Anonymous` | PASS |
| 10 | Unapproved: designation null | PASS |
| 11 | Unapproved: email null | PASS |
| 12 | Unapproved: bio null | PASS |
| 13 | Unapproved: image null | PASS |
| 14 | Unapproved: `hasApproved = false` | PASS |
| 15 | Unapproved: dates still returned | PASS |
| 16 | `externalContributors` list applies the same masking | PASS |
| 17 | Unapproved contributor's email never appears in the list response | PASS |
| 18 | Delete succeeds (test data removed) | PASS |

## Suite B — collaborative flow, logged in with a real Keycloak token (14/14)

| # | Check | Result |
|---|---|---|
| 1 | Logged-in user creates a draft collaborative (`addCollaborative`) | PASS |
| 2 | Create external contributor (approved) | PASS |
| 3 | `updateCollaborative` sets `designation` and attaches the contributor via `externalContributorIds` | PASS |
| 4 | `collaborative { designation externalContributors { ... } }` returns no errors | PASS |
| 5 | Collaborative designation saved | PASS |
| 6 | Approved contributor shown in full under the collaborative | PASS |
| 7 | Approved contributor's email returned | PASS |
| 8 | After unapproving: `Anonymous`, email/designation/bio/image null | PASS |
| 9 | After unapproving: dates still returned | PASS |
| 10 | After unapproving: email absent from the whole response | PASS |
| 11 | Re-approving restores name and email | PASS |
| 12 | Search by name finds the contributor | PASS |
| 13 | Search by email returns nothing | PASS |
| 14 | Cleanup (collaborative and contributor deleted) | PASS |

## Raw API walkthrough (curl, logged in)

Ran the full flow as raw `curl` requests and inspected every response: create collaborative → create contributor with an image (multipart upload) → set collaborative designation and attach contributor → read → unapprove → read → search by name / email → re-approve → delete. All responses matched the expected behaviour above, and the contributor's email did not appear anywhere in the response for the unapproved read.

## Image handling (verified with multipart uploads)

| Check | Result |
|---|---|
| Upload on create stores the file under a random name (`external_contributors/<uuid>.png`) and it is served (200) | PASS |
| Replacing the image deletes the old file (old URL → 404, new → 200) | PASS |
| Deleting the contributor deletes the image (URL → 404, no files left on disk) | PASS |
| Unapproved contributor: `image` is `null` in the API | PASS |

## Not covered / known limitations

- Platform users' emails (`user { email }`, `contributors { email }`) are still returned to anonymous callers; left unchanged by decision.
- Any caller can set `hasApproved`; no permission check by decision.
- An unapproved contributor's image file is still publicly served if someone already has its URL; the random name only stops it being guessed.

## Bugs found and fixed while testing

- `deleteExternalContributor` used `handle_django_errors=True` with a `bool` return, which crashed the server at startup.
- `image` was typed `str` but returned a file object; it now uses `DjangoImageType` like other models.
- `createdAt`/`updatedAt` had been turned into strings; they are DateTime again.
- `external_contributor_schema` was not registered in `api/schema/schema.py`.
- Images were saved under `external_contributors/None/…` (the id isn't set at create time), using the original, guessable filename; they now get a random name.
- Replacing or deleting a contributor left the old image file on disk; it is now removed.
