"""A dataset's query-engine profile: only its facts hash and its summary.

The rollup itself (tables, coverage, metadata) is computed on read from the
dataset's table profiles, so it can never drift; this row holds what must be
remembered between passes. Written only by ``qe_sync`` and the summary
endpoint.

Docs: api/views/query_engine/architecture.md
"""

import uuid

from django.db import models
from django.db.models import Q

from api.models.QeSummaryFields import QeSummaryFields


class DatasetProfile(QeSummaryFields):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dataset = models.OneToOneField(
        "api.Dataset", on_delete=models.CASCADE, related_name="qe_profile"
    )
    facts_hash = models.CharField(max_length=64, blank=True, default="")
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "qe_dataset_profile"
        indexes = [
            # Pending summaries: filter(summary_needed=True).order_by("modified").
            models.Index(
                fields=["modified"],
                name="qe_dp_summary_needed_idx",
                condition=Q(summary_needed=True),
            )
        ]

    def __str__(self) -> str:
        return f"profile of dataset {self.dataset_id}"
