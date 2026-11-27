"""Layer 4: GET /api/internal/qe/scope/ — what a scope covers right now."""

from typing import Any, Callable

import pytest

from api.utils.enums import CollaborativeStatus, DatasetAccessType, DatasetStatus

URL = "/api/internal/qe/scope/"


@pytest.mark.django_db
class TestScopeEndpoint:
    def test_platform_scope_counts_the_corpus(self, api: Callable, make_dataset: Callable) -> None:
        make_dataset("Rainfall")
        make_dataset("Anaemia")
        make_dataset("Draft", status=DatasetStatus.DRAFT)

        response = api().get(URL, {"scope": "platform"})

        assert response.status_code == 200
        assert response.json() == {
            "kind": "platform",
            "public_id": None,
            "title": None,
            "dataset_count": 2,
        }

    def test_a_collaborative_scope_lists_its_corpus_datasets_when_asked(
        self, api: Callable, make_dataset: Callable, make_collaborative: Callable
    ) -> None:
        anaemia = make_dataset("Anaemia")
        private = make_dataset("Private", access_type=DatasetAccessType.PRIVATE)
        fem = make_collaborative("FemHealth", datasets=[anaemia, private])

        response = api().get(
            URL, {"scope": f"collaborative:{fem.public_id}", "include_dataset_ids": "true"}
        )

        assert response.status_code == 200
        assert response.json() == {
            "kind": "collaborative",
            "public_id": fem.public_id,
            "title": "FemHealth",
            "dataset_count": 1,
            "dataset_ids": [str(anaemia.id)],
        }

    def test_platform_ids_are_capped(
        self, api: Callable, make_dataset: Callable, monkeypatch: Any
    ) -> None:
        monkeypatch.setattr("api.services.query_engine.scope.MAX_SCOPE_DATASET_IDS", 2)
        for index in range(3):
            make_dataset(f"Dataset {index}")

        body = api().get(URL, {"scope": "platform", "include_dataset_ids": "true"}).json()

        assert body["dataset_count"] == 3
        assert len(body["dataset_ids"]) == 2

    def test_missing_scope_is_400(self, api: Callable) -> None:
        response = api().get(URL)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "bad_request"

    @pytest.mark.parametrize("scope", ["everything", "collaborative:SHORT", "collaborative:"])
    def test_a_malformed_scope_is_400(self, api: Callable, scope: str) -> None:
        response = api().get(URL, {"scope": scope})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "bad_scope"
        # Never echoes what the caller sent.
        assert scope not in response.json()["error"]["message"] or scope == "collaborative:"

    @pytest.mark.parametrize("status", [CollaborativeStatus.DRAFT, CollaborativeStatus.ARCHIVED])
    def test_an_unpublished_collaborative_is_404(
        self, api: Callable, make_collaborative: Callable, status: str
    ) -> None:
        collaborative = make_collaborative(status=status)
        response = api().get(URL, {"scope": f"collaborative:{collaborative.public_id}"})
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "scope_not_found"

    def test_an_unknown_collaborative_is_404(self, api: Callable) -> None:
        response = api().get(URL, {"scope": "collaborative:zzzzzzzzzzzz"})
        assert response.status_code == 404

    def test_a_collaborative_not_enabled_is_404(
        self, api: Callable, settings: Any, make_collaborative: Callable
    ) -> None:
        fem = make_collaborative("FemHealth")
        other = make_collaborative("Other")
        settings.QE_ENABLED_COLLABORATIVES = [fem.public_id]

        assert api().get(URL, {"scope": f"collaborative:{fem.public_id}"}).status_code == 200
        assert api().get(URL, {"scope": f"collaborative:{other.public_id}"}).status_code == 404
