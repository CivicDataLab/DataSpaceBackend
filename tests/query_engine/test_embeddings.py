"""Layer 2: the embeddings and reranker clients against a mock HTTP transport (EMB1–5, RR1)."""

import json
import logging
from typing import Any, Callable, Dict, List

import httpx
import pytest
from django.core.management import call_command
from django.core.management.base import SystemCheckError
from tenacity import wait_none

from api.services.query_engine import embeddings, reranker
from api.services.query_engine.embeddings import EmbeddingsUnavailable, embed_query, embed_texts
from api.services.query_engine.reranker import RerankUnavailable, rerank, weak_match_threshold

SECRET = "sk-or-test-key-123"


@pytest.fixture(autouse=True)
def embedding_settings(settings: Any, monkeypatch: Any) -> Any:
    settings.QE_EMBEDDINGS_URL = "https://embeddings.example/api/v1"
    settings.QE_EMBEDDINGS_MODEL = "test/embed"
    settings.QE_EMBEDDINGS_DIMS = 4
    settings.QE_EMBEDDINGS_BATCH_SIZE = 2
    settings.QE_EMBEDDINGS_API_KEY = SECRET
    settings.QE_EMBEDDINGS_QUERY_INPUT_TYPE = ""
    settings.QE_EMBEDDINGS_DOC_INPUT_TYPE = ""
    settings.QE_EMBEDDINGS_QUERY_PREFIX = ""
    settings.QE_EMBEDDINGS_DOC_PREFIX = ""
    settings.QE_RERANK_URL = "https://rerank.example/api/v1"
    settings.QE_RERANK_MODEL = "cohere/rerank-5-pro"
    settings.QE_RERANK_API_KEY = SECRET
    settings.QE_WEAK_MATCH_RERANK = None
    monkeypatch.setattr(embeddings, "RETRY_WAIT", wait_none())
    return settings


def recording(responder: Callable[[httpx.Request], httpx.Response]) -> Any:
    seen: List[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return responder(request)

    return httpx.Client(transport=httpx.MockTransport(handle)), seen


def vectors_for(request: httpx.Request, dims: int = 4) -> httpx.Response:
    body = json.loads(request.content)
    data = [{"index": i, "embedding": [float(i + 1)] * dims} for i in range(len(body["input"]))]
    return httpx.Response(200, json={"data": data})


class TestEmbedTexts:
    def test_batches_and_sends_model_dimensions_and_key(self) -> None:
        client, seen = recording(vectors_for)

        vectors = embed_texts(["a", "b", "c"], client=client)

        assert vectors == [[1.0] * 4, [2.0] * 4, [1.0] * 4]
        assert len(seen) == 2
        first = json.loads(seen[0].content)
        assert first == {"model": "test/embed", "input": ["a", "b"], "dimensions": 4}
        assert seen[0].url == "https://embeddings.example/api/v1/embeddings"
        assert seen[0].headers["Authorization"] == f"Bearer {SECRET}"

    def test_no_key_means_no_authorization_header(self, settings: Any) -> None:
        settings.QE_EMBEDDINGS_API_KEY = ""
        client, seen = recording(vectors_for)
        embed_texts(["a"], client=client)
        assert "Authorization" not in seen[0].headers

    def test_input_type_and_prefix_only_when_configured(self, settings: Any) -> None:
        settings.QE_EMBEDDINGS_DOC_INPUT_TYPE = "search_document"
        settings.QE_EMBEDDINGS_DOC_PREFIX = "passage: "
        client, seen = recording(vectors_for)
        embed_texts(["rain"], client=client)
        body = json.loads(seen[0].content)
        assert body["input_type"] == "search_document"
        assert body["input"] == ["passage: rain"]

    def test_texts_are_cut_to_2000_characters(self) -> None:
        client, seen = recording(vectors_for)
        embed_texts(["x" * 5000], client=client)
        assert len(json.loads(seen[0].content)["input"][0]) == 2000

    def test_a_vector_of_the_wrong_size_is_refused(self) -> None:
        client, _ = recording(lambda request: vectors_for(request, dims=3))
        with pytest.raises(EmbeddingsUnavailable, match="wrong_dimensions"):
            embed_texts(["a"], client=client)

    @pytest.mark.parametrize("status", [429, 500, 503])
    def test_rate_limits_and_server_errors_are_retried_then_unavailable(self, status: int) -> None:
        client, seen = recording(lambda request: httpx.Response(status))
        with pytest.raises(EmbeddingsUnavailable):
            embed_texts(["a"], client=client)
        assert len(seen) == embeddings.ATTEMPTS

    def test_a_retry_that_succeeds_returns_vectors(self) -> None:
        answers = [httpx.Response(503), None]

        def flaky(request: httpx.Request) -> httpx.Response:
            answer = answers.pop(0)
            return answer if answer is not None else vectors_for(request)

        client, seen = recording(flaky)
        assert embed_texts(["a"], client=client) == [[1.0] * 4]
        assert len(seen) == 2

    def test_timeouts_are_retried(self) -> None:
        def slow(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("slow", request=request)

        client, seen = recording(slow)
        with pytest.raises(EmbeddingsUnavailable):
            embed_texts(["a"], client=client)
        assert len(seen) == embeddings.ATTEMPTS

    def test_a_client_error_is_not_retried(self) -> None:
        client, seen = recording(lambda request: httpx.Response(401))
        with pytest.raises(EmbeddingsUnavailable):
            embed_texts(["a"], client=client)
        assert len(seen) == 1

    def test_logs_carry_neither_the_key_nor_the_text(self, caplog: Any) -> None:
        caplog.set_level(logging.DEBUG)
        client, _ = recording(lambda request: httpx.Response(500))
        with pytest.raises(EmbeddingsUnavailable):
            embed_texts(["anaemia in Kamrup district"], client=client)
        assert SECRET not in caplog.text
        assert "anaemia" not in caplog.text


class TestEmbedQuery:
    def test_a_repeated_question_is_served_from_the_cache(self) -> None:
        client, seen = recording(vectors_for)
        first = embed_query("rainfall in Assam", client=client)
        second = embed_query("rainfall in Assam", client=client)
        assert first == second and len(seen) == 1

    def test_a_cache_outage_just_misses(self, monkeypatch: Any) -> None:
        def broken(*args: Any, **kwargs: Any) -> None:
            raise ConnectionError("redis down")

        monkeypatch.setattr(embeddings.cache, "get", broken)
        monkeypatch.setattr(embeddings.cache, "set", broken)
        client, seen = recording(vectors_for)
        assert embed_query("rainfall", client=client) == [1.0] * 4
        assert len(seen) == 1

    def test_query_input_type_is_its_own_setting(self, settings: Any) -> None:
        settings.QE_EMBEDDINGS_QUERY_INPUT_TYPE = "search_query"
        client, seen = recording(vectors_for)
        embed_query("rainfall", client=client)
        assert json.loads(seen[0].content)["input_type"] == "search_query"


class TestReranker:
    def test_sends_the_request_shape_and_reads_scores_best_first(self) -> None:
        client, seen = recording(
            lambda request: httpx.Response(
                200,
                json={
                    "results": [
                        {"index": 0, "relevance_score": 0.2},
                        {"index": 1, "relevance_score": 0.9},
                    ]
                },
            )
        )

        order = rerank("rainfall", ["doc a", "doc b"], client=client)

        assert order == [(1, 0.9), (0, 0.2)]
        assert json.loads(seen[0].content) == {
            "model": "cohere/rerank-5-pro",
            "query": "rainfall",
            "documents": ["doc a", "doc b"],
            "top_n": 2,
        }
        assert seen[0].url == "https://rerank.example/api/v1/rerank"

    @pytest.mark.parametrize(
        "answer",
        [
            httpx.Response(500),
            httpx.Response(200, json={"oops": 1}),
            httpx.Response(200, json={"results": [{"index": 7, "relevance_score": 1}]}),
        ],
        ids=["server-error", "bad-shape", "index-out-of-range"],
    )
    def test_failures_are_a_typed_error(self, answer: httpx.Response) -> None:
        client, _ = recording(lambda request: answer)
        with pytest.raises(RerankUnavailable):
            rerank("rainfall", ["doc a"], client=client)

    def test_switching_the_model_switches_the_threshold(self, settings: Any) -> None:
        settings.QE_RERANK_MODEL = "cohere/rerank-5-pro"
        cohere = weak_match_threshold()
        settings.QE_RERANK_MODEL = "qwen/qwen3-reranker-8b"
        assert weak_match_threshold() != cohere
        client, seen = recording(lambda request: httpx.Response(200, json={"results": []}))
        rerank("q", ["d"], client=client)
        assert json.loads(seen[0].content)["model"] == "qwen/qwen3-reranker-8b"

    def test_the_override_wins(self, settings: Any) -> None:
        settings.QE_WEAK_MATCH_RERANK = 0.77
        assert weak_match_threshold() == 0.77

    def test_a_model_outside_the_allow_list_fails_at_start_up(self, settings: Any) -> None:
        settings.QE_RERANK_MODEL = "someone/else"
        with pytest.raises(SystemCheckError, match="query_engine.E001"):
            call_command("check")
        with pytest.raises(RerankUnavailable):
            rerank("q", ["d"])
