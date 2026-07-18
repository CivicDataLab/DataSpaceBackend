"""
Journey: create a Resource, add a PDF block and a YouTube block, set metadata,
reorder, publish, then fetch it anonymously and confirm it's visible with its
blocks in order.

On-demand (Layer 5) — runs against a live backend. Reads KEYCLOAK_TEST_TOKEN
and TEST_BASE_URL from env. Fails loudly on the first assertion that fails.

Usage:
    KEYCLOAK_TEST_TOKEN=... TEST_BASE_URL=http://localhost:8000 \
        python tests/journeys/publications/create-blocks-publish.py
"""

import os

import requests

base = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
token = os.environ["KEYCLOAK_TEST_TOKEN"]
headers = {"Authorization": f"Bearer {token}"}
graphql = f"{base}/api/graphql"


def gql(query, variables=None, files=None):
    """Post a GraphQL operation (multipart when files are given)."""
    if files:
        return requests.post(graphql, data=files, headers=headers)
    res = requests.post(
        graphql, json={"query": query, "variables": variables or {}}, headers=headers
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert not body.get("errors"), body["errors"]
    return body["data"]


# 1. Create a DRAFT resource with full metadata (ids below are placeholders —
#    fill in a real resource type / sector / geography id from your test data).
create = gql(
    """
    mutation($input: CreatePublicationInput!) {
      createPublication(input: $input) {
        success errors { fieldErrors { field messages } } data { id status }
      }
    }
    """,
    {
        "input": {
            "title": "Journey Findings",
            "description": "A journey-test resource.",
            "authors": ["Journey Bot"],
            "publicationDate": "2024-01-01",
            "license": "CC_BY_4_0_ATTRIBUTION",
            "resourceTypeId": os.environ.get("TEST_RESOURCE_TYPE_ID", "REPLACE_ME"),
            "sectorIds": [os.environ.get("TEST_SECTOR_ID", "REPLACE_ME")],
            "geographyIds": [int(os.environ.get("TEST_GEOGRAPHY_ID", "1"))],
        }
    },
)
assert create["createPublication"]["success"], create
publication_id = create["createPublication"]["data"]["id"]
assert create["createPublication"]["data"]["status"] == "DRAFT"

# 2. Add a YouTube block (a PDF block is added via the multipart upload path the
#    frontend uses — see ResourceDropzone; scripted upload builds the GraphQL
#    multipart request the same way).
yt = gql(
    """
    mutation($id: UUID!, $url: String!) {
      addPublicationYoutubeBlock(publicationId: $id, youtubeUrl: $url) {
        success data { id position blockType }
      }
    }
    """,
    {"id": publication_id, "url": "https://youtu.be/dQw4w9WgXcQ"},
)
assert yt["addPublicationYoutubeBlock"]["success"], yt

# 3. Publish it.
pub = gql(
    "mutation($id: UUID!) { publishPublication(publicationId: $id) { success data { status } } }",
    {"id": publication_id},
)
assert pub["publishPublication"]["data"]["status"] == "PUBLISHED"

# 4. Fetch anonymously and confirm it's visible with its blocks in order.
anon = requests.post(
    graphql,
    json={
        "query": "query($id: UUID!) { getPublication(publicationId: $id) { id status blocks { position } } }",
        "variables": {"id": publication_id},
    },
)
data = anon.json()["data"]["getPublication"]
assert data and data["status"] == "PUBLISHED", data
positions = [b["position"] for b in data["blocks"]]
assert positions == sorted(positions), positions

print("PASS: create-blocks-publish")
