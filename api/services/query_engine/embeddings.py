"""Turning text into vectors for AI search, through one OpenAI-compatible embeddings endpoint.

``POST {QE_EMBEDDINGS_URL}/embeddings`` with ``model``, ``input`` (a batch of
texts) and ``dimensions``; a bearer key when one is set. The model is fully
described by settings (URL, model id, size, key, batch size, and optional
``input_type`` and text prefixes for queries and documents — sent only when
configured), so trying another model is a settings change plus a rebuild of
the search index. Default: ``google/gemini-embedding-2`` through OpenRouter,
1,536 dimensions.

- ``embed_texts``: documents (indexing), in batches of QE_EMBEDDINGS_BATCH_SIZE,
  10 s per request.
- ``embed_query``: one search question, one attempt of 3 s (search falls back
  to keywords instead of waiting on retries), cached in Redis for a day under
  a hash of model, size, query settings and text (a cache outage just misses).

Texts are cut to 2,000 characters. Rate limits (429), server errors and
timeouts are retried with back-off; then, like any other failure or a vector
of the wrong length, ``EmbeddingsUnavailable`` is raised, and callers fall back
(index without a vector; search by keywords only). Logs carry counts, the
model and status codes — never the key or the text.

Docs: api/views/query_engine/architecture.md
"""

import hashlib
from typing import Any, Dict, List, Optional, Sequence

import httpx
import structlog
from django.conf import settings
from django.core.cache import cache
from tenacity import (
    RetryError,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger("dataspace.query_engine.embeddings")

MAX_TEXT_CHARS = 2000
INDEX_TIMEOUT_SECONDS = 10.0
QUERY_TIMEOUT_SECONDS = 3.0
QUERY_CACHE_SECONDS = 24 * 60 * 60
QUERY_CACHE_PREFIX = "qe_qemb:"
ATTEMPTS = 3
# How long to wait between attempts (tests swap in a zero wait).
RETRY_WAIT: Any = wait_exponential(multiplier=0.5, max=4)


class EmbeddingsUnavailable(Exception):
    """The embeddings endpoint could not give usable vectors right now."""


class _Retryable(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def model_fingerprint() -> str:
    """What identifies the vectors a document gets: model, size, document input type and prefix."""
    return "|".join(
        [
            settings.QE_EMBEDDINGS_MODEL,
            str(settings.QE_EMBEDDINGS_DIMS),
            settings.QE_EMBEDDINGS_DOC_INPUT_TYPE,
            settings.QE_EMBEDDINGS_DOC_PREFIX,
        ]
    )


def embed_texts(
    texts: Sequence[str], *, client: Optional[httpx.Client] = None
) -> List[List[float]]:
    """One vector per document text, in order. Raises EmbeddingsUnavailable."""
    prefix = settings.QE_EMBEDDINGS_DOC_PREFIX
    inputs = [(prefix + text)[:MAX_TEXT_CHARS] for text in texts]
    vectors: List[List[float]] = []
    batch_size = max(1, int(settings.QE_EMBEDDINGS_BATCH_SIZE))
    with _client(client, INDEX_TIMEOUT_SECONDS) as http:
        for start in range(0, len(inputs), batch_size):
            batch = inputs[start : start + batch_size]
            vectors.extend(_embed_batch(http, batch, settings.QE_EMBEDDINGS_DOC_INPUT_TYPE))
    return vectors


def embed_query(text: str, *, client: Optional[httpx.Client] = None) -> List[float]:
    """The vector of one search question (cached). Raises EmbeddingsUnavailable."""
    query = (settings.QE_EMBEDDINGS_QUERY_PREFIX + text)[:MAX_TEXT_CHARS]
    key = (
        QUERY_CACHE_PREFIX
        + hashlib.sha256(
            "|".join(
                [
                    settings.QE_EMBEDDINGS_MODEL,
                    str(settings.QE_EMBEDDINGS_DIMS),
                    settings.QE_EMBEDDINGS_QUERY_INPUT_TYPE,
                    settings.QE_EMBEDDINGS_QUERY_PREFIX,
                    text,
                ]
            ).encode("utf-8")
        ).hexdigest()
    )
    cached = _cache_get(key)
    if cached is not None:
        return list(cached)
    with _client(client, QUERY_TIMEOUT_SECONDS) as http:
        # One attempt: a search falls back to keywords rather than wait on retries.
        vector = _embed_batch(http, [query], settings.QE_EMBEDDINGS_QUERY_INPUT_TYPE, attempts=1)[0]
    _cache_set(key, vector)
    return vector


class _client:
    """The caller's client, or a short-lived one with the given timeout."""

    def __init__(self, given: Optional[httpx.Client], timeout: float) -> None:
        self.given = given
        self.own: Optional[httpx.Client] = None
        self.timeout = timeout

    def __enter__(self) -> httpx.Client:
        if self.given is not None:
            return self.given
        self.own = httpx.Client(timeout=self.timeout)
        return self.own

    def __exit__(self, *exc: Any) -> None:
        if self.own is not None:
            self.own.close()


def _embed_batch(
    http: httpx.Client, inputs: List[str], input_type: str, attempts: int = ATTEMPTS
) -> List[List[float]]:
    body: Dict[str, Any] = {
        "model": settings.QE_EMBEDDINGS_MODEL,
        "input": inputs,
        "dimensions": int(settings.QE_EMBEDDINGS_DIMS),
    }
    if input_type:
        body["input_type"] = input_type
    headers = {"Content-Type": "application/json"}
    if settings.QE_EMBEDDINGS_API_KEY:
        headers["Authorization"] = f"Bearer {settings.QE_EMBEDDINGS_API_KEY}"
    url = settings.QE_EMBEDDINGS_URL.rstrip("/") + "/embeddings"
    try:
        for attempt in Retrying(
            retry=retry_if_exception(lambda error: isinstance(error, _Retryable)),
            stop=stop_after_attempt(attempts),
            wait=RETRY_WAIT,
            reraise=False,
        ):
            with attempt:
                response = _post(http, url, body, headers)
    except RetryError as error:
        cause = error.last_attempt.exception()
        reason = getattr(cause, "reason", "retries_exhausted")
        logger.warning("qe_embeddings_unavailable", reason=reason, texts=len(inputs))
        raise EmbeddingsUnavailable(reason) from error
    return _vectors(response, len(inputs))


def _post(
    http: httpx.Client, url: str, body: Dict[str, Any], headers: Dict[str, str]
) -> httpx.Response:
    try:
        response = http.post(url, json=body, headers=headers)
    except httpx.TimeoutException:
        raise _Retryable("timeout")
    except httpx.HTTPError as error:
        logger.warning(
            "qe_embeddings_unavailable", reason="connection", error_type=type(error).__name__
        )
        raise EmbeddingsUnavailable("connection") from error
    if response.status_code == 429 or response.status_code >= 500:
        raise _Retryable(f"status_{response.status_code}")
    if response.status_code != 200:
        logger.warning("qe_embeddings_unavailable", reason="status", status=response.status_code)
        raise EmbeddingsUnavailable(f"status_{response.status_code}")
    return response


def _vectors(response: httpx.Response, expected: int) -> List[List[float]]:
    try:
        data = sorted(response.json()["data"], key=lambda item: item.get("index", 0))
        vectors = [[float(x) for x in item["embedding"]] for item in data]
    except (ValueError, KeyError, TypeError) as error:
        logger.warning("qe_embeddings_unavailable", reason="bad_response")
        raise EmbeddingsUnavailable("bad_response") from error
    dims = int(settings.QE_EMBEDDINGS_DIMS)
    if len(vectors) != expected or any(len(vector) != dims for vector in vectors):
        logger.error("qe_embeddings_wrong_shape", expected=expected, got=len(vectors), dims=dims)
        raise EmbeddingsUnavailable("wrong_dimensions")
    return vectors


def _cache_get(key: str) -> Optional[List[float]]:
    try:
        value = cache.get(key)
    except Exception as error:
        logger.warning("qe_embeddings_cache_unavailable", error_type=type(error).__name__)
        return None
    return list(value) if value is not None else None


def _cache_set(key: str, vector: List[float]) -> None:
    try:
        cache.set(key, vector, timeout=QUERY_CACHE_SECONDS)
    except Exception as error:
        logger.warning("qe_embeddings_cache_unavailable", error_type=type(error).__name__)


def embeddings_configured() -> bool:
    """Whether vectors can be expected at all (a key, or an endpoint that needs none)."""
    default_endpoint = settings.QE_EMBEDDINGS_URL.startswith("https://openrouter.ai")
    return bool(settings.QE_EMBEDDINGS_API_KEY) or not default_endpoint
