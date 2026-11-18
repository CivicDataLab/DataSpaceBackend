"""What a use case, collaborative or dataset needs before it can be published (#292).

The rules are the frontend's publish step, so a call to the API cannot publish a
draft the UI would block. Events and publications keep their own checks in
their services.
"""

import json
import re
from typing import Any, List, Optional

from api.models import Collaborative, Dataset, UseCase

_TAG = re.compile(r"<[^>]+>")


def _plain_text(value: Optional[str]) -> str:
    """Text without HTML tags or non-breaking spaces, like the frontend's plainSummary."""
    text = _TAG.sub(" ", value or "").replace("&nbsp;", " ")
    return " ".join(text.split())


def _filled(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _block_has_content(block: Any) -> bool:
    if not isinstance(block, dict):
        return False
    kind = block.get("type")
    if kind == "text":
        html = block.get("html")
        return bool(_plain_text(html if isinstance(html, str) else ""))
    if kind == "image":
        return _filled(block.get("src"))
    if kind == "chart":
        return _filled(block.get("chartId"))
    if kind == "highlight":
        return _filled(block.get("title")) or _filled(block.get("body"))
    if kind == "link":
        return _filled(block.get("url"))
    return False


def _has_content_blocks(summary: Optional[str]) -> bool:
    """A use case summary is the frontend's block document (JSON, version 1).

    Older drafts hold plain HTML instead, which counts when it has any text.
    """
    if not (summary or "").strip():
        return False
    try:
        document = json.loads(summary or "")
    except ValueError:
        return bool(_plain_text(summary))
    if (
        isinstance(document, dict)
        and document.get("version") == 1
        and isinstance(document.get("blocks"), list)
    ):
        return any(_block_has_content(block) for block in document["blocks"])
    return bool(_plain_text(summary))


def _refuse_if_missing(missing: List[str]) -> None:
    # A GraphQL error, not handle_django_errors' OperationInfo: the frontend's
    # publish calls only read the published type, so a refusal returned as data
    # would look like success.
    if missing:
        raise ValueError(f"Cannot publish yet: {'; '.join(missing)}.")


def assert_use_case_ready(use_case: UseCase) -> None:
    missing = []
    if not (use_case.title or "").strip():
        missing.append("add a title")
    if not use_case.logo:
        missing.append("upload a thumbnail image")
    if not _has_content_blocks(use_case.summary):
        missing.append("add at least one content block")
    if not use_case.sectors.exists():
        missing.append("select at least one sector")
    if not use_case.sdgs.exists():
        missing.append("select at least one SDG")
    if not use_case.datasets.exists():
        missing.append("connect at least one dataset")
    _refuse_if_missing(missing)


def assert_collaborative_ready(collaborative: Collaborative) -> None:
    missing = []
    if not (collaborative.title or "").strip():
        missing.append("add a title")
    if not _plain_text(collaborative.summary):
        missing.append("add a description")
    if not collaborative.sectors.exists():
        missing.append("select at least one sector")
    if not collaborative.sdgs.exists():
        missing.append("select at least one SDG")
    if not (collaborative.datasets.exists() or collaborative.use_cases.exists()):
        missing.append("connect at least one dataset or use case")
    _refuse_if_missing(missing)


def assert_dataset_ready(dataset: Dataset) -> None:
    missing = []
    if not dataset.resources.exists():  # type: ignore[attr-defined]
        missing.append("add at least one resource")
    if not (dataset.description or "").strip():
        missing.append("add a description")
    if not dataset.sectors.exists():
        missing.append("select at least one sector")
    if not dataset.tags.exists():
        missing.append("add at least one tag")
    if not dataset.license:
        missing.append("choose a license")
    _refuse_if_missing(missing)
