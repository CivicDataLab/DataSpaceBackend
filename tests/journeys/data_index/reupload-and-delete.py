"""
Journey: upload a CSV, read its rows, replace the file while polling the data
API (it must never come back empty or half-replaced), fire two replacements at
once (the rows served must match the file the download serves), then delete
the resource and get a 404 from the data API.

On-demand (Layer 5) — runs against a live backend. Reads from env:
    KEYCLOAK_TEST_TOKEN   a token for a user who can edit TEST_DATASET_ID
    TEST_BASE_URL         default http://localhost:8000
    TEST_DATASET_ID       a draft dataset to add the resource to
Fails loudly on the first assertion that fails.

Usage:
    KEYCLOAK_TEST_TOKEN=... TEST_DATASET_ID=... TEST_BASE_URL=http://localhost:8000 \
        python tests/journeys/data_index/reupload-and-delete.py

Afterwards, at least an hour later (the orphan list skips per-upload tables
built within the last hour, as their upload may still be switching), the
operator runs `python manage.py migrate_data_table_names` (a dry run) on the
server and checks the report lists no orphan from the racing uploads.
Docs: api/utils/data_indexing_architecture.md
"""

import csv
import io
import json
import os
import threading

import requests

base = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
token = os.environ["KEYCLOAK_TEST_TOKEN"]
dataset_id = os.environ["TEST_DATASET_ID"]
headers = {"Authorization": f"Bearer {token}"}
graphql = f"{base}/api/graphql"

CREATE = """mutation ($ds: UUID!, $file: Upload!) {
  createFileResources(fileResourceInput: {dataset: $ds, files: [$file]}) { id }
}"""
REPLACE = """mutation ($id: UUID!, $file: Upload!) {
  updateFileResource(fileResourceInput: {id: $id, file: $file}) { __typename }
}"""
DELETE = "mutation ($id: UUID!) { deleteFileResource(resourceId: $id) }"


def make_csv(label, rows):
    """A CSV whose every row carries the label, so a mix of two files is visible."""
    lines = ["district,label,value"] + [f"District {i},{label},{i}" for i in range(rows)]
    return ("\n".join(lines) + "\n").encode()


def upload(query, variables, file_bytes):
    """Post a GraphQL mutation with one file, using the GraphQL multipart spec."""
    operations = {"query": query, "variables": {**variables, "file": None}}
    res = requests.post(
        graphql,
        data={"operations": json.dumps(operations), "map": json.dumps({"0": ["variables.file"]})},
        files={"0": ("journey.csv", file_bytes, "text/csv")},
        headers=headers,
        timeout=300,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert not body.get("errors"), body["errors"]
    return body["data"]


def served_labels(resource_id):
    """The labels the data API serves for the resource (all rows), or None on an error."""
    res = requests.get(
        f"{base}/api/resources/{resource_id}/data/",
        params={"limit": 10000, "columns": "label"},
        headers=headers,
        timeout=60,
    )
    if res.status_code != 200:
        return None
    return {row[0] for row in res.json()["rows"]}, res.json()["total"]


def downloaded_label(resource_id):
    """The label in the file the download endpoint serves."""
    res = requests.get(f"{base}/api/download/resource/{resource_id}", headers=headers, timeout=60)
    assert res.status_code == 200, res.text
    rows = list(csv.DictReader(io.StringIO(res.content.decode())))
    labels = {row["label"] for row in rows}
    assert len(labels) == 1, labels
    return labels.pop()


# 1. Upload a CSV and read its rows back.
created = upload(CREATE, {"ds": dataset_id}, make_csv("first", 500))
resource_id = created["createFileResources"][0]["id"]
assert served_labels(resource_id) == ({"first"}, 500)

# 2. Replace it while polling: every read is the complete old or the complete new file.
seen = []
done = threading.Event()


def poll():
    while not done.is_set():
        seen.append(served_labels(resource_id))


poller = threading.Thread(target=poll)
poller.start()
upload(REPLACE, {"id": resource_id}, make_csv("second", 800))
done.set()
poller.join()
assert seen, "the poller never read anything"
for reading in seen:
    assert reading in (({"first"}, 500), ({"second"}, 800)), reading
assert served_labels(resource_id) == ({"second"}, 800)

# 3. Two replacements at once: whichever file the download serves, the data API serves too.
race_errors = []


def race(label):
    try:
        upload(REPLACE, {"id": resource_id}, make_csv(label, 300))
    except Exception as error:  # surfaced below: a thread's exception is otherwise lost
        race_errors.append(error)


racers = [threading.Thread(target=race, args=(label,)) for label in ("third", "fourth")]
for racer in racers:
    racer.start()
for racer in racers:
    racer.join()
assert not race_errors, race_errors
winner = downloaded_label(resource_id)
assert served_labels(resource_id) == ({winner}, 300), (winner, served_labels(resource_id))

# 4. Delete the resource: its data is gone.
res = requests.post(
    graphql, json={"query": DELETE, "variables": {"id": resource_id}}, headers=headers, timeout=60
)
assert res.status_code == 200 and not res.json().get("errors"), res.text
gone = requests.get(f"{base}/api/resources/{resource_id}/data/", headers=headers, timeout=60)
assert gone.status_code == 404, gone.text

print("PASS: reupload-and-delete")
print(
    "In an hour, run `python manage.py migrate_data_table_names` and check the report "
    "lists no orphans (younger per-upload tables are skipped by design)."
)
