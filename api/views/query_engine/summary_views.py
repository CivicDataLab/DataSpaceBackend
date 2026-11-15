"""GET summaries/pending/ and PUT summaries/<level>/<id>/ — model-written summaries, checked here.

The query engine asks which datasets and tables need a summary, writes them
with its own model, and sends each back with the facts hash it was written
from. A summary is stored only when the item is still in the corpus (404),
it was written from the current facts (409, nothing stored), it is plain
text of the right length without links (422), and every number in it is
found in the facts the backend recomputes itself (422 listing the numbers).
Each refusal after the facts check counts against those facts; after two
the item is no longer offered until its facts change. Stored summaries are
always shown labelled as generated.

These two endpoints take no scope: they serve the whole processing set.

Docs: ./architecture.md
"""

from uuid import UUID

import structlog
from rest_framework.request import Request
from rest_framework.response import Response

from api.services.query_engine.errors import FactsChanged, SummaryRejected, UntracedNumbers
from api.services.query_engine.summaries import (
    current_facts,
    get_summary_target,
    pending_summaries,
    record_rejection,
    require_same_facts,
    save_summary_if_current,
)
from api.services.query_engine.summary_check import check_summary_text, find_untraced_numbers
from api.views.query_engine.base import InternalQeView
from api.views.query_engine.serializers import (
    PendingSummariesSerializer,
    SummaryWriteSerializer,
    read_input,
)

logger = structlog.get_logger("dataspace.query_engine.summaries")


class PendingSummariesView(InternalQeView):
    def get(self, request: Request) -> Response:
        # How many items the caller wants (at most 20).
        params = read_input(PendingSummariesSerializer, request.query_params)

        # The items that need a summary now, each with its current facts and their hash.
        return Response(pending_summaries(params["limit"]))


class SummaryWriteView(InternalQeView):
    def put(self, request: Request, level: str, item_id: UUID) -> Response:
        # Read the summary and the facts hash it was written from.
        params = read_input(SummaryWriteSerializer, request.data)
        written_from = params["facts_hash"]

        # The profile it is for, only while its dataset (and table) is in the corpus (404).
        target = get_summary_target(level, item_id)

        # The facts as they are now, recomputed here — never the caller's copy.
        facts = current_facts(target)

        # A summary written from other facts is refused before anything else is checked (409).
        require_same_facts(target, facts, written_from)

        # Plain text of the right length, with no links, emails or code (422; counts against these facts).
        problems = check_summary_text(params["text"])
        if problems:
            record_rejection(target, written_from)
            raise SummaryRejected(details={"problems": problems}, reason="text_rules")

        # Every number must be traceable to the facts; a miss counts against these facts (422).
        untraced = find_untraced_numbers(params["text"], facts)
        if untraced:
            record_rejection(target, written_from)
            raise UntracedNumbers(details={"untraced_numbers": untraced}, reason="untraced_numbers")

        # Store it, unless newer facts arrived in the meantime (409, nothing stored).
        if not save_summary_if_current(
            target, written_from, params["text"], params["model"], params["prompt_version"]
        ):
            raise FactsChanged(reason="facts_changed_during_write")
        logger.info(
            "qe_summary_stored",
            level=level,
            item_id=str(item_id),
            model=params["model"],
            prompt_version=params["prompt_version"],
            length=len(params["text"]),
        )
        return Response(status=204)
