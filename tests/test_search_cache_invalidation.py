"""The search cache must be invalidated after the index write, with a key that never expires."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from api.signals import collaborative_signals, dataset_signals, usecase_signals
from api.utils import search_cache
from api.utils.enums import CollaborativeStatus, DatasetStatus, UseCaseStatus


def test_version_key_never_expires() -> None:
    with patch.object(search_cache, "cache") as cache:
        cache.get.return_value = 4
        search_cache.invalidate_search_cache()
    cache.set.assert_called_once_with(search_cache.SEARCH_CACHE_VERSION_KEY, 5, timeout=None)


CASES = [
    (dataset_signals, "handle_dataset_publication", "Dataset", "DatasetDocument", DatasetStatus),
    (usecase_signals, "handle_usecase_publication", "UseCase", "UseCaseDocument", UseCaseStatus),
    (
        collaborative_signals,
        "handle_collaborative_publication",
        "Collaborative",
        "CollaborativeDocument",
        CollaborativeStatus,
    ),
]


@pytest.mark.parametrize("module,handler,model,document,status", CASES)
@pytest.mark.parametrize("publishing", [True, False])
def test_invalidates_only_after_the_refreshed_index_write(
    module, handler, model, document, status, publishing
) -> None:
    """A search between the bump and the index write would re-cache stale results."""
    calls = []
    before, after = (status.DRAFT, status.PUBLISHED) if publishing else (status.PUBLISHED, status.DRAFT)
    instance = SimpleNamespace(pk=1, id=1, title="t", status=after)

    doc = MagicMock()
    doc.update.side_effect = lambda *a, **kw: calls.append(("index", kw.get("refresh")))
    doc.delete.side_effect = lambda *a, **kw: calls.append(("index", kw.get("refresh")))
    document_class = MagicMock(return_value=doc)
    document_class.get.return_value = doc

    model_class = MagicMock()
    model_class.objects.get.return_value = SimpleNamespace(status=before)

    with patch.object(module, model, model_class), patch.object(
        module, document, document_class
    ), patch.object(
        module, "invalidate_search_cache", side_effect=lambda: calls.append(("invalidate", None))
    ):
        getattr(module, handler)(sender=None, instance=instance)

    assert calls == [("index", True), ("invalidate", None)]
