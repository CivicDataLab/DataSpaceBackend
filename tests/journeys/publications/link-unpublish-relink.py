"""
Journey: create + publish a Resource, link it to a Use Case and a Collaborative,
confirm both render it, unpublish (both hide it), re-publish (both show it),
delete (both skip it and the linked-count stays consistent).

On-demand (Layer 5) — runs against a live backend. Reads KEYCLOAK_TEST_TOKEN,
TEST_BASE_URL, TEST_USE_CASE_ID and TEST_COLLABORATIVE_ID (both DRAFT, owned by
the token's user/org) from env. Fails loudly on the first bad assertion.

Usage:
    KEYCLOAK_TEST_TOKEN=... TEST_BASE_URL=http://localhost:8000 \
    TEST_USE_CASE_ID=... TEST_COLLABORATIVE_ID=... \
        python tests/journeys/publications/link-unpublish-relink.py
"""

import os

import requests

base = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
token = os.environ["KEYCLOAK_TEST_TOKEN"]
headers = {"Authorization": f"Bearer {token}"}
graphql = f"{base}/api/graphql"
use_case_id = os.environ["TEST_USE_CASE_ID"]
collaborative_id = os.environ["TEST_COLLABORATIVE_ID"]


def gql(query, variables=None):
    res = requests.post(
        graphql, json={"query": query, "variables": variables or {}}, headers=headers
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert not body.get("errors"), body["errors"]
    return body["data"]


# 1. Create + publish a resource (metadata ids from env, see the sibling script).
create = gql(
    """
    mutation($input: CreatePublicationInput!) {
      createPublication(input: $input) { success data { id } }
    }
    """,
    {
        "input": {
            "title": "Linkable Findings",
            "description": "For the link journey.",
            "authors": ["Journey Bot"],
            "publicationDate": "2024-01-01",
            "license": "CC_BY_4_0_ATTRIBUTION",
            "resourceTypeId": os.environ.get("TEST_RESOURCE_TYPE_ID", "REPLACE_ME"),
            "sectorIds": [os.environ.get("TEST_SECTOR_ID", "REPLACE_ME")],
            "geographyIds": [int(os.environ.get("TEST_GEOGRAPHY_ID", "1"))],
        }
    },
)
publication_id = create["createPublication"]["data"]["id"]
gql(
    "mutation($id: UUID!) { publishPublication(publicationId: $id) { success } }",
    {"id": publication_id},
)

# 2. Link it to the use case and the collaborative.
gql(
    "mutation($u: String!, $p: UUID!) { addPublicationToUseCase(useCaseId: $u, publicationId: $p) { __typename } }",
    {"u": use_case_id, "p": publication_id},
)
gql(
    "mutation($c: String!, $p: UUID!) { addPublicationToCollaborative(collaborativeId: $c, publicationId: $p) { __typename } }",
    {"c": collaborative_id, "p": publication_id},
)


def renders(entity, entity_id):
    query = {
        "usecase": "query($id: ID!) { useCase(pk: $id) { publications { id } } }",
        "collab": "query($id: ID!) { collaborative(pk: $id) { publications { id } } }",
    }[entity]
    data = gql(query, {"id": entity_id})
    key = "useCase" if entity == "usecase" else "collaborative"
    return [p["id"] for p in (data[key]["publications"] or [])]


# 3. Both render it while published.
assert publication_id in renders("usecase", use_case_id)
assert publication_id in renders("collab", collaborative_id)

# 4. Unpublish → both hide it.
gql(
    "mutation($id: UUID!) { unpublishPublication(publicationId: $id) { success } }",
    {"id": publication_id},
)
assert publication_id not in renders("usecase", use_case_id)
assert publication_id not in renders("collab", collaborative_id)

# 5. Re-publish → both show it again.
gql(
    "mutation($id: UUID!) { publishPublication(publicationId: $id) { success } }",
    {"id": publication_id},
)
assert publication_id in renders("usecase", use_case_id)

# 6. Delete → both skip it silently.
gql(
    "mutation($id: UUID!) { deletePublication(publicationId: $id) { success } }",
    {"id": publication_id},
)
assert publication_id not in renders("usecase", use_case_id)
assert publication_id not in renders("collab", collaborative_id)

print("PASS: link-unpublish-relink")
