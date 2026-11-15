"""Layer 4: POST search/ with the index gateway, embeddings and reranker mocked (SRCH, LEAK1, LEAK-STALE).

The canned index answers include documents that must never be served; only
the database post-filter can drop them.
"""

import logging
import uuid
from typing import Any, Callable, Dict, Iterator, List, Optional
from unittest import mock

import pytest

from api.models import Dataset, Resource, ResourceProfile
from api.services.query_engine.embeddings import EmbeddingsUnavailable
from api.services.query_engine.profiles import save_resource_profile_if_current
from api.services.query_engine.reranker import RerankUnavailable
from api.utils.enums import DatasetAccessType, DatasetStatus, DatasetType
from search.query_engine.index import SearchIndexError

URL = "/api/internal/qe/search/"
SEARCH = "api.services.query_engine.search"
STATS = {"row_count": 3, "layout": "long", "analysable": True, "columns": []}


def doc(doc_id: str, dataset_id: Any, resource_id: Any = None) -> Dict[str, Any]:
    return {
        "_id": doc_id,
        "_score": 0.9,
        "_source": {
            "dataset_id": str(dataset_id),
            "resource_id": str(resource_id) if resource_id else None,
            "title": doc_id,
            "rerank_text": doc_id,
        },
    }


class FakeIndex:
    """What the mocked index returns: the same hits on both legs."""

    def __init__(self) -> None:
        self.hits: List[Dict[str, Any]] = []
        self.bodies: List[Dict[str, Any]] = []

    def __call__(self, bodies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        self.bodies = bodies
        return [{"hits": {"hits": list(self.hits)}} for _ in bodies]


@pytest.fixture
def index(settings: Any) -> Iterator[FakeIndex]:
    settings.QE_EMBEDDINGS_API_KEY = "test-key"
    settings.QE_RERANK_API_KEY = "test-key"
    settings.QE_EMBEDDINGS_URL = "https://openrouter.ai/api/v1"
    settings.QE_RERANK_URL = "https://openrouter.ai/api/v1"
    fake = FakeIndex()
    with mock.patch(f"{SEARCH}.multi_search", side_effect=fake), mock.patch(
        f"{SEARCH}.embed_query", return_value=[0.1, 0.2]
    ), mock.patch(
        f"{SEARCH}.rerank",
        side_effect=lambda query, docs: [(i, 0.9 - i * 0.01) for i in range(len(docs))],
    ):
        yield fake


@pytest.fixture
def table(make_dataset: Callable, make_resource: Callable) -> Callable[..., Resource]:
    def make(title: str = "Anaemia", **changes: Any) -> Resource:
        resource = make_resource(make_dataset(title, **changes))
        save_resource_profile_if_current(resource, resource.resourcedatatable.id, STATS)
        return resource

    return make


def search(api: Callable, **body: Any) -> Any:
    return api().post(
        URL, {"scope": "platform", "query": "anaemia in women", **body}, format="json"
    )


@pytest.mark.django_db
class TestSearchResponse:
    def test_results_carry_datasets_tables_scores_and_flags(
        self, api: Callable, index: FakeIndex, table: Callable
    ) -> None:
        resource = table()
        index.hits = [
            doc(f"r:{resource.id}", resource.dataset_id, resource.id),
            doc(f"d:{resource.dataset_id}", resource.dataset_id),
        ]

        response = search(api)

        assert response.status_code == 200
        body = response.json()
        assert (body["scope"], body["weak_match"], body["degraded"]) == ("platform", False, [])
        [result] = body["results"]
        assert result["dataset_id"] == str(resource.dataset_id)
        assert result["title"] == "Anaemia" and result["organization"] == "Health Org"
        assert [t["resource_id"] for t in result["tables"]] == [str(resource.id)]
        assert result["tables"][0]["analysable"] is True
        assert result["summary"] is None

    def test_a_current_summary_is_labelled_generated(
        self, api: Callable, index: FakeIndex, table: Callable
    ) -> None:
        resource = table()
        from api.models import DatasetProfile

        DatasetProfile.objects.create(
            dataset=resource.dataset,
            facts_hash="f",
            summary_facts_hash="f",
            summary_text="Covers Assam.",
        )
        index.hits = [doc(f"d:{resource.dataset_id}", resource.dataset_id)]

        summary = search(api).json()["results"][0]["summary"]

        assert summary["text"] == "Covers Assam." and summary["generated"] is True

    def test_size_caps_the_number_of_datasets(
        self, api: Callable, index: FakeIndex, table: Callable
    ) -> None:
        resources = [table(f"Dataset {i}") for i in range(4)]
        index.hits = [doc(f"d:{r.dataset_id}", r.dataset_id) for r in resources]

        assert len(search(api, size=2).json()["results"]) == 2
        assert search(api, size=11).status_code == 400

    def test_a_weak_best_match_is_flagged(
        self, api: Callable, index: FakeIndex, table: Callable
    ) -> None:
        resource = table()
        index.hits = [doc(f"d:{resource.dataset_id}", resource.dataset_id)]
        with mock.patch(f"{SEARCH}.rerank", return_value=[(0, 0.01)]):
            assert search(api).json()["weak_match"] is True

    def test_degraded_modes(self, api: Callable, index: FakeIndex, table: Callable) -> None:
        resource = table()
        index.hits = [doc(f"d:{resource.dataset_id}", resource.dataset_id)]
        with mock.patch(
            f"{SEARCH}.embed_query", side_effect=EmbeddingsUnavailable("down")
        ), mock.patch(f"{SEARCH}.rerank", side_effect=RerankUnavailable("down")):
            body = search(api).json()
        assert body["degraded"] == ["vector", "rerank"]
        assert len(index.bodies) == 1  # keyword leg only

    def test_a_failed_vector_leg_falls_back_to_keywords(
        self, api: Callable, index: FakeIndex, table: Callable
    ) -> None:
        resource = table()
        hits = [doc(f"d:{resource.dataset_id}", resource.dataset_id)]
        answers = [{"hits": {"hits": hits}}, {"error": {"type": "illegal_argument_exception"}}]
        with mock.patch(f"{SEARCH}.multi_search", return_value=answers):
            body = search(api).json()
        assert body["degraded"] == ["vector"]
        assert [r["dataset_id"] for r in body["results"]] == [str(resource.dataset_id)]

    def test_without_keys_no_model_service_is_called(
        self, api: Callable, index: FakeIndex, table: Callable, settings: Any
    ) -> None:
        settings.QE_EMBEDDINGS_API_KEY = ""
        settings.QE_RERANK_API_KEY = ""
        resource = table()
        index.hits = [doc(f"d:{resource.dataset_id}", resource.dataset_id)]
        with mock.patch(f"{SEARCH}.embed_query") as embed, mock.patch(f"{SEARCH}.rerank") as rerank:
            body = search(api).json()
        embed.assert_not_called()
        rerank.assert_not_called()
        assert body["degraded"] == ["vector", "rerank"]

    def test_a_reversed_year_range_is_400(self, api: Callable, index: FakeIndex) -> None:
        assert search(api, year_from=2020, year_to=2015).status_code == 400

    def test_search_down_is_503(self, api: Callable, table: Callable) -> None:
        with mock.patch(
            f"{SEARCH}.multi_search", side_effect=SearchIndexError("msearch")
        ), mock.patch(f"{SEARCH}.embed_query", return_value=[0.1]):
            response = search(api)
        assert response.status_code == 503

    def test_an_over_long_question_is_400(self, api: Callable, index: FakeIndex) -> None:
        assert search(api, query="x" * 501).status_code == 400

    def test_the_question_never_reaches_the_info_logs(
        self, api: Callable, index: FakeIndex, table: Callable, caplog: Any
    ) -> None:
        caplog.set_level(logging.INFO)
        table()
        search(api, query="secret question about Kamrup")
        assert "secret question" not in caplog.text
        assert "qe_search_done" in caplog.text


@pytest.mark.django_db
class TestLeaks:
    def test_only_the_in_scope_eligible_document_is_served(
        self,
        api: Callable,
        index: FakeIndex,
        table: Callable,
        make_resource: Callable,
        make_dataset: Callable,
        make_collaborative: Callable,
    ) -> None:
        eligible = table("Anaemia")
        outside = table("Rainfall")
        draft = table("Draft", status=DatasetStatus.DRAFT)
        private = table("Private", access_type=DatasetAccessType.PRIVATE)
        restricted = table("Restricted", access_type=DatasetAccessType.RESTRICTED)
        prompt = table("Prompts", dataset_type=DatasetType.PROMPT)
        inactive = make_resource(eligible.dataset, name="Old table", is_active=False)
        fem = make_collaborative(
            "FemHealth", datasets=[eligible.dataset, draft.dataset, private.dataset]
        )
        index.hits = [
            doc(f"r:{r.id}", r.dataset_id, r.id)
            for r in (draft, private, restricted, prompt, inactive, outside, eligible)
        ] + [doc(f"r:{uuid.uuid4()}", eligible.dataset_id, uuid.uuid4())]

        body = search(api, scope=f"collaborative:{fem.public_id}").json()

        assert [r["dataset_id"] for r in body["results"]] == [str(eligible.dataset_id)]
        assert [t["resource_id"] for t in body["results"][0]["tables"]] == [str(eligible.id)]
        # The collaborative's dataset ids were sent to the index as a filter too.
        assert {"terms": {"dataset_id": sorted([str(eligible.dataset_id)])}} in index.bodies[0][
            "query"
        ]["bool"]["filter"]

    def test_platform_scope_never_serves_ineligible_datasets(
        self, api: Callable, index: FakeIndex, table: Callable
    ) -> None:
        eligible = table("Anaemia")
        ineligible = [
            table("Draft", status=DatasetStatus.DRAFT),
            table("Private", access_type=DatasetAccessType.PRIVATE),
            table("Restricted", access_type=DatasetAccessType.RESTRICTED),
            table("Prompts", dataset_type=DatasetType.PROMPT),
        ]
        index.hits = [doc(f"d:{r.dataset_id}", r.dataset_id) for r in ineligible + [eligible]]

        body = search(api).json()

        assert [r["dataset_id"] for r in body["results"]] == [str(eligible.dataset_id)]

    def test_platform_sectors_leave_out_other_sectors(
        self, api: Callable, settings: Any, index: FakeIndex, table: Callable, make_sector: Callable
    ) -> None:
        climate = make_sector("Climate Action")
        kept = table("Rainfall")
        kept.dataset.sectors.add(climate)
        other = table("Anaemia")
        settings.QE_PLATFORM_SECTORS = ["climate-action"]
        index.hits = [
            doc(f"d:{other.dataset_id}", other.dataset_id),
            doc(f"d:{kept.dataset_id}", kept.dataset_id),
        ]

        body = search(api).json()

        assert [r["dataset_id"] for r in body["results"]] == [str(kept.dataset_id)]

    def test_an_unpublished_dataset_disappears_at_once_though_still_indexed(
        self, api: Callable, index: FakeIndex, table: Callable
    ) -> None:
        resource = table()
        index.hits = [
            doc(f"r:{resource.id}", resource.dataset_id, resource.id),
            doc(f"d:{resource.dataset_id}", resource.dataset_id),
        ]
        profile_url = f"/api/internal/qe/resources/{resource.id}/profile/"

        assert len(search(api).json()["results"]) == 1
        assert api().get(profile_url, {"scope": "platform"}).status_code == 200

        Dataset.objects.filter(pk=resource.dataset_id).update(status=DatasetStatus.DRAFT)

        assert search(api).json()["results"] == []
        assert api().get(profile_url, {"scope": "platform"}).status_code == 404
        dataset_url = f"/api/internal/qe/datasets/{resource.dataset_id}/profile/"
        assert api().get(dataset_url, {"scope": "platform"}).status_code == 404
        query_url = f"/api/internal/qe/resources/{resource.id}/query/"
        assert (
            api()
            .post(query_url, {"scope": "platform", "measures": [{"fn": "count"}]}, format="json")
            .status_code
            == 404
        )
