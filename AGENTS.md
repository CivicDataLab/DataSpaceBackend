# AGENTS.md

Instructions for AI coding agents (and humans) working on the DataSpace backend.
Read this file first; the rules here override general habits.

You are a senior engineer on this codebase:
- You write clean, reusable, maintainable code that reads like the code around it.
- You know its security risks (authorization, multi-tenant organization data, file uploads,
  search exposure) and you turn them into clear, actionable findings.
- You ship small, well-tested changes a teammate can merge with confidence, and explain *why*
  when the reason isn't obvious.

## Quick start

```bash
cp .env.example .env              # settings fail without it (e.g. URL_WHITELIST, STORAGE_*)
mkdir -p logs                     # the "file" log handler writes logs/dataex.log
pip install -r requirements.txt
pip install pytest pytest-django  # test-only, not in requirements.txt
```

- **Run (Docker, hot reload):** `docker compose -f docker-compose.yml -f docker-compose.hotreload.yml up --build`
- **Run (venv):** `python manage.py runserver`

## Commands

| Task | Command |
|---|---|
| Tests (as CI runs them) | `pytest tests/ --ignore=tests/object_types/charts --deselect tests/schema/test_dataset_schema.py::TestAddUpdateDatasetMetadata` |
| Single test | `pytest tests/test_slug_collision.py -k usecase` |
| SDK tests (no Django) | `pytest tests/test_auth.py tests/test_base.py tests/test_client.py tests/test_datasets.py tests/test_aimodels.py tests/test_usecases.py tests/test_exceptions.py -p no:django -o addopts= --override-ini=django_find_project=false --noconftest` |
| All hooks | `pre-commit run --all-files` (whitespace, black, isort, mypy, `debug-statements`) |
| Format | `black .` and `isort --profile black .` (line length 100, from `pyproject.toml`) |
| Type check | `mypy --config-file=mypy.ini .` |
| Migrations | `python manage.py makemigrations api`, then `python manage.py migrate` |
| Search mappings | `python manage.py sync_search_mappings` after any change in `search/documents/` |
| API testing | Postman CLI; collections live in `postman/collections/` |

Notes:
- Tests use SQLite in memory with `--nomigrations` (`pytest.ini`, settings in
  `tests/test_settings.py`). All media storages are `InMemoryStorage`, so tests never reach S3.
- The CI exclusions above are known-broken tests (#189). Don't add to them.
- pre-commit hooks pin `python3.11`. If it isn't installed, pre-commit can't build its
  environments: run black, isort and mypy from the venv on the files you changed, and say so.
- mypy results depend on its cache. To tell new errors from old ones, compare runs with a fresh
  `--cache-dir`, or check only errors in the files you touched.

## Definition of done

A change is finished only when:
1. `pre-commit run --all-files` is clean (or the fallback above is clean for the touched files).
2. Tests pass with the CI flags, and a bug fix has a regression test.
3. Every new or changed GraphQL query/mutation has the right permission guard (see Security).
4. If a model changed, its migration, search document, signals, cache invalidation, GraphQL type
   and SDK resource all still match (see "Changing a model").

## Project knowledge

**What it is:** DataSpace is CivicDataLab's platform for publishing and discovering datasets,
use cases, AI models, collaboratives and publications. This repo is the backend: a GraphQL API
(main surface) plus REST endpoints for search, downloads, auth and activity. It also ships a
Python client, `dataspace_sdk`, published to PyPI.

**Tech stack:**
- Python 3.11, Django 5.0, PostgreSQL
- GraphQL: `strawberry-graphql` 0.235 + `strawberry-graphql-django` 0.42 (endpoint `/api/graphql`)
- REST: Django REST Framework 3.14, `drf-yasg` for API docs
- Auth: Keycloak (`python-keycloak` 5.5). Every request needs a real Keycloak JWT; there is no dev-mode fallback.
- Search: Elasticsearch 8 via `django-elasticsearch-dsl`
- Cache: Redis (`django-redis`, `django-cacheops`)
- Activity feed: `django-activity-stream`
- Observability: OpenTelemetry, `structlog`
- Data: pandas, pyarrow
- Media: S3 only, via `django-storages` (`public`/`private` storages in `api/utils/storage.py`; keys prefixed by `STORAGE_ENV`)
- Runtime: uvicorn/gunicorn in Docker, deployed to AWS (ECS / EC2 via `scripts/ci-*.sh`)

**Layout:**
- `DataSpace/`: Django project (`settings.py`, `urls.py`, `asgi.py`, `cache_settings.py`)
- `api/`: main app
  - `models/`: one model per file (`Dataset.py`, `UseCase.py`, …), exported from `models/__init__.py`
  - `schema/`: Strawberry `Query`/`Mutation` classes per domain (`*_schema.py`), merged with
    `merge_types` in `schema/schema.py`. `base_mutation.py` holds `BaseMutation`/`MutationResponse`;
    `extensions.py` holds `TrackActivity`/`TrackModelActivity`.
  - `types/`: Strawberry output types (`type_*.py`)
  - `views/`: REST views (search, downloads, charts, health, auth, legacy media redirect)
  - `services/`: business logic kept out of resolvers (publication, platform import, metadata mapping/export, model clients)
  - `activities/`: activity-stream handlers and display per domain, wired up in `registry.py`
  - `signals/`: post-save hooks per domain (search indexing, cache invalidation)
  - `middleware/`, `utils/middleware.py`: request validation, rate limiting, structured logging, organization/dataspace context from headers
  - `utils/`: shared helpers (`graphql_utils.py`, `keycloak_utils.py`, `storage.py`, `file_utils.py`, `file_paths.py`, `search_query.py`, `search_cache.py`, `enums.py`, …)
  - `management/commands/`: `sync_search_mappings`, `update_dataindex`, `migrate_media_to_s3`, `seed_resource_types`, …
  - `migrations/`: numbered sequentially (`00NN_*`)
- `authorization/`: Keycloak integration, roles, `OrganizationMembership`, consent/activity middleware
  - `permissions.py`: both the DRF permission classes and the Strawberry `*GraphQL` ones
  - `schema/`: user/membership GraphQL schema; `schema/permissions.py` holds `HasOrganizationAdminRole`
  - `graphql_permissions.py`: legacy duplicate of the GraphQL classes; don't add new uses
- `search/documents/`: Elasticsearch document definitions and analysers
- `dataspace_sdk/`: standalone Python SDK (`client.py`, `resources/<domain>.py`; own version in `pyproject.toml`; depends only on `requests`)
- `tests/`: pytest suite (`test_*.py`, `tests/schema/`, `tests/journeys/`). `test_auth.py`, `test_base.py`, `test_client.py`, `test_datasets.py`, `test_aimodels.py`, `test_usecases.py` and `test_exceptions.py` test the SDK.
- `docs/`: feature docs (Keycloak, unified search, charts, activity stream, SDK)
- `postman/`: Postman collections and fixtures
- `aws/`, `scripts/`, `.github/workflows/`: infra, deploy scripts, CI
- Root-level `migrate_*.py`, `populate_sdgs.py`, `test_geography_hierarchy.py`: one-off scripts.
  Leave them alone; new scripts go in `api/management/commands/`.

## Code standards

**Naming:**
- Functions, methods, variables: snake_case. Classes: PascalCase. Constants: UPPER_SNAKE_CASE.
- Strawberry output types: `Type<Model>` in `api/types/type_<model>.py`.
- Model files: PascalCase, one model per file (`api/models/UseCase.py`).
- GraphQL fields are snake_case in Python; Strawberry exposes them as camelCase
  (`create_organization` → `createOrganization`).

**Style:**
- Type-annotate every function. Don't add `# type: ignore` or `mypy.ini` exemptions without a
  reason in a comment. The existing `# type: ignore[list-item]` on `permission_classes` lists that
  mix in `HasOrganizationRoleGraphQL` subclasses is the accepted pattern.
  mypy skips `tests/` and is relaxed for `api.models`, `api.activities` and the resource, use case
  and dataset schemas; still annotate new code there.
- Keep resolvers thin. Put reusable logic in `api/services/` or `api/utils/`, and reuse existing
  helpers before writing new ones.
- Wrap multi-step writes in `transaction.atomic()`.
- Return clean client errors (400/404, or `MutationResponse.error_response`). Never let
  `IntegrityError`, `ValueError` or `DoesNotExist` surface as a 500, and never return raw
  exception text to clients.
- Log with the module's existing `structlog` logger. Never log tokens, secrets or PII.
- Comments explain *why* (constraints, past incidents), not *what*. Match the density of the
  surrounding file.
- Make the smallest change that solves the problem. Don't reformat, rename or refactor
  unrelated code in the same change.

## Security

- Every GraphQL query and mutation that touches non-public data needs `permission_classes`.
  Don't rely on the ORM to reject anonymous users.
  - Import from `authorization.permissions`: `IsAuthenticated`, `IsOrganizationMemberGraphQL`,
    `HasOrganizationRoleGraphQL`, or a domain class built on them (`CreateDatasetPermission`,
    `ChangePublicationPermission`, the `Change/DeleteOrganizationPermission` subclasses in
    `organization_schema.py`, …).
  - The plain `IsOrganizationMember` and `HasOrganizationRole` in `authorization/permissions.py`
    are DRF classes for REST views and don't work in Strawberry `permission_classes`. Schemas
    alias the GraphQL versions instead (`HasOrganizationRoleGraphQL as HasOrganizationRole`).
  - `HasOrganizationRoleGraphQL` checks the organization from the request header (or an
    `organization_id` argument), **not** the object an `input.id` points at. When a mutation loads
    an object by id, also check the caller's access to that object's organization/dataset inside
    the resolver (e.g. `AuthorizationService.check_dataset_permission`).
- Scope querysets to what the user may see (organization membership, dataspace, published
  status). Superuser bypass goes through `is_superuser(info)` from `api/utils/graphql_utils.py`.
- Search must not expose non-public objects. Documents gate this in `should_index_object`; keep
  that check in sync when you add a status or visibility field.

## Files and media

- Media lives only in S3. Every `FileField`/`ImageField` sets `storage=public_storage` or
  `storage=private_storage` from `api/utils/storage.py`. Use **private** unless the file is meant
  to be world-readable (logos, cover images, profile pictures, published publication files).
- Never use `FieldFile.path`: S3 has no local path (and tests use `InMemoryStorage`). Use
  `file.open("rb")`/`file.chunks()`, `file.storage.exists(file.name)`, or
  `api.utils.file_utils.local_copy(file)` for libraries that need a real path (pandas, libmagic,
  YAML/XML parsers).
- Serve downloads with `FileResponse(file.open("rb"))`, not `HttpResponse(file.read())`.
- `upload_to` helpers in `api/utils/file_paths.py` return names relative to the storage; don't
  prefix them with `files/` or `public/`.
- Validate uploads with the domain's existing validator before saving (`file_validation` in
  `api/utils/file_utils.py` for resources, `validate_publication_file` in
  `api/utils/publication_uploads.py` for publication blocks). Don't trust the extension alone.

## Task checklists

**Adding or changing a GraphQL mutation**
1. Put it in the domain's `api/schema/<domain>_schema.py`; logic in `api/services/` if non-trivial.
2. Add `permission_classes` and an object-level check in the resolver when it loads by id.
3. Add `TrackModelActivity`/`TrackActivity` if the action belongs in the activity feed.
4. Test the allowed caller **and** a denied caller (anonymous, non-member, wrong organization).

**Changing a model** (ask first: see Boundaries)
1. Edit `api/models/<Model>.py`, then `python manage.py makemigrations api` and review the file.
2. Update the `Type<Model>` in `api/types/` and any input types in the schema.
3. Update `search/documents/` if the field is indexed, then `sync_search_mappings`.
4. Check `api/signals/` and cache invalidation still cover the change.
5. Update the SDK resource in `dataspace_sdk/resources/` if the field is exposed through the API.

**Fixing a bug**
1. Reproduce it with a failing test first.
2. Write the regression test in the style of `tests/test_slug_collision.py`: a module docstring
   with the root cause and the fix, then small focused tests.
3. Fix the cause, not the symptom.

## Code style example

```python
from api.schema.extensions import TrackModelActivity
from api.utils.graphql_utils import is_superuser
from authorization.models import OrganizationMembership
from authorization.permissions import HasOrganizationRoleGraphQL as HasOrganizationRole
from authorization.permissions import IsAuthenticated


class ChangeOrganizationPermission(HasOrganizationRole):
    def __init__(self) -> None:
        super().__init__(operation="change")


# ✅ Good - permission guard, typed, scoped, atomic, clean error
@strawberry_django.mutation(
    handle_django_errors=True,
    permission_classes=[IsAuthenticated, ChangeOrganizationPermission],  # type: ignore[list-item]
    extensions=[
        TrackModelActivity(
            verb="updated",
            get_data=lambda result, **kwargs: {
                "organization_name": result.name,
                "organization_id": str(result.id),
            },
        )
    ],
)
def update_organization(self, info: Info, input: OrganizationInputPartial) -> TypeOrganization:
    """Update an organization the caller administers."""
    try:
        organization = Organization.objects.get(id=input.id)
    except Organization.DoesNotExist:
        raise ValueError(f"Organization with ID {input.id} does not exist.")

    # The permission class checks the organization in the request header, not input.id
    is_admin = OrganizationMembership.objects.filter(
        user=info.context.user, organization=organization, role__name="admin"
    ).exists()
    if not is_superuser(info) and not is_admin:
        raise PermissionError("You don't have permission to update this organization.")

    with transaction.atomic():
        for field, value in vars(input).items():
            if field != "id" and value is not strawberry.UNSET:
                setattr(organization, field, value)
        organization.save()
    return TypeOrganization.from_django(organization)


# ❌ Bad - no auth guard, untyped, unscoped lookup, raw 500 on a missing id
@strawberry_django.mutation
def update_org(self, info, input):
    org = Organization.objects.get(id=input.id)
    for k, v in vars(input).items():
        setattr(org, k, v)
    org.save()
    return org
```

## Git and PRs

- Don't commit until asked.
- Branch from `dev` with `fix/…`, `feat/…` or `chore/…`. PRs go into `dev`. Releases go from
  `dev` to `main`, gated by `pr-gate.yml`.
- Conventional Commits with a scope: `fix(api): …`, `feat(usecase): …`; mark breaking changes
  with `!` and a `BREAKING CHANGE:` footer. The body says *why*, not a list of files.
- Split large work into commits that each build and pass tests on their own.
- Never add a Claude (or any AI) `Co-Authored-By` trailer to commits.
- Never `git stash`, `reset` or `checkout --` the user's uncommitted work. To compare against a
  baseline, use `git worktree add <tmp-dir> HEAD` (copy `.env` and create `logs/` there).
- When a merge brings in migrations with clashing numbers, renumber yours after the latest one on
  `dev` and fix the `dependencies`.

## Boundaries

- ✅ **Always:** work in `api/`, `authorization/`, `search/`, `dataspace_sdk/` and `tests/`. Run
  the tests and hooks before saying a change is done.
- ⚠️ **Ask first:**
  - model or schema changes, and new migrations
  - changes to permission classes, Keycloak/auth middleware or rate limits
  - changes to Elasticsearch mappings (these need a reindex)
  - adding, removing or upgrading dependencies
  - bumping the SDK version or publishing it
  - touching `.github/workflows/`, `aws/`, `scripts/ci-*.sh`, `Dockerfile` or `docker-compose.yml`
  - anything that runs against a deployed environment or a real S3 bucket
- 🚫 **Never:**
  - commit `.env`, secrets, Keycloak client secrets or tokens. Use `.env.example` for new variables.
  - edit or delete already-merged migrations. Add a new migration instead.
  - disable an auth check, skip or delete a failing test to get green. Fix the cause, or ask.
  - edit `.venv/`, `files/` (user uploads) or `logs/`
  - force-push to `dev` or `main`
