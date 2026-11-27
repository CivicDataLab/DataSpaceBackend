"""Putting the best search matches first: one system-wide reranker over OpenRouter.

``POST {QE_RERANK_URL}/rerank`` with ``model``, ``query``, ``documents`` and
``top_n``; the answer's ``results[].index`` / ``relevance_score`` reorder the
documents. The model is QE_RERANK_MODEL, one of ALLOWED_RERANK_MODELS — a
system check refuses anything else at start-up, so a typo can't silently
switch models. Each allowed model has its own weak-match threshold
(RERANK_WEAK_MATCH; QE_WEAK_MATCH_RERANK overrides it), because their scores
aren't on one scale; switching the model switches the threshold too.

Any failure raises ``RerankUnavailable``; search then keeps the fused order
and reports itself degraded. Logs carry the model, counts and status codes,
never the key or the texts.

Docs: api/views/query_engine/architecture.md
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx
import structlog
from django.conf import settings
from django.core import checks

logger = structlog.get_logger("dataspace.query_engine.reranker")

ALLOWED_RERANK_MODELS = ("cohere/rerank-5-pro", "mongodb/rerank-3", "qwen/qwen3-reranker-8b")
# Provisional until the Phase 5 comparison on the golden set; recorded in the arch doc.
RERANK_WEAK_MATCH: Dict[str, float] = {
    "cohere/rerank-5-pro": 0.30,
    "mongodb/rerank-3": 0.35,
    "qwen/qwen3-reranker-8b": 0.40,
}
RERANK_TIMEOUT_SECONDS = 3.0


class RerankUnavailable(Exception):
    """The reranker could not score the documents right now."""


def rerank_configured() -> bool:
    """Whether reranking can work at all (a key, or an endpoint that needs none)."""
    default_endpoint = settings.QE_RERANK_URL.startswith("https://openrouter.ai")
    return bool(settings.QE_RERANK_API_KEY) or not default_endpoint


def rerank_model() -> str:
    """The configured reranker, refusing one outside the allow-list."""
    model = settings.QE_RERANK_MODEL
    if model not in ALLOWED_RERANK_MODELS:
        raise RerankUnavailable("model_not_allowed")
    return str(model)


def weak_match_threshold() -> float:
    """The score under which the best match counts as weak, for the active reranker."""
    if settings.QE_WEAK_MATCH_RERANK is not None:
        return float(settings.QE_WEAK_MATCH_RERANK)
    return RERANK_WEAK_MATCH[rerank_model()]


def rerank(
    query: str,
    documents: Sequence[str],
    *,
    top_n: Optional[int] = None,
    client: Optional[httpx.Client] = None,
) -> List[Tuple[int, float]]:
    """``(document index, relevance score)`` best first. Raises RerankUnavailable."""
    if not documents:
        return []
    body: Dict[str, Any] = {
        "model": rerank_model(),
        "query": query,
        "documents": list(documents),
        "top_n": top_n or len(documents),
    }
    headers = {"Content-Type": "application/json"}
    if settings.QE_RERANK_API_KEY:
        headers["Authorization"] = f"Bearer {settings.QE_RERANK_API_KEY}"
    url = settings.QE_RERANK_URL.rstrip("/") + "/rerank"
    own = client is None
    http = client or httpx.Client(timeout=RERANK_TIMEOUT_SECONDS)
    try:
        response = http.post(url, json=body, headers=headers)
    except httpx.HTTPError as error:
        logger.warning(
            "qe_rerank_unavailable", reason="connection", error_type=type(error).__name__
        )
        raise RerankUnavailable("connection") from error
    finally:
        if own:
            http.close()
    if response.status_code != 200:
        logger.warning("qe_rerank_unavailable", reason="status", status=response.status_code)
        raise RerankUnavailable(f"status_{response.status_code}")
    try:
        results = [
            (int(item["index"]), float(item["relevance_score"]))
            for item in response.json()["results"]
        ]
    except (ValueError, KeyError, TypeError) as error:
        logger.warning("qe_rerank_unavailable", reason="bad_response")
        raise RerankUnavailable("bad_response") from error
    if any(not 0 <= index < len(documents) for index, _ in results):
        raise RerankUnavailable("bad_response")
    return sorted(results, key=lambda pair: -pair[1])


@checks.register()
def check_rerank_model(app_configs: Any = None, **kwargs: Any) -> List[checks.CheckMessage]:
    """Start-up check: QE_RERANK_MODEL must be one of ALLOWED_RERANK_MODELS."""
    if settings.QE_RERANK_MODEL in ALLOWED_RERANK_MODELS:
        return []
    return [
        checks.Error(
            "QE_RERANK_MODEL is not an allowed reranker.",
            hint=f"Use one of: {', '.join(ALLOWED_RERANK_MODELS)}.",
            id="query_engine.E001",
        )
    ]
