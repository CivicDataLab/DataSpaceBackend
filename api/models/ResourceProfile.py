"""A table's query-engine profile: computed stats plus the facts it was hashed from.

One row per tabular resource the query engine can reach, written only by the
``qe_sync`` process. ``data_table_id`` is the ResourceDataTable row the stats
were computed from (a plain value, not a key: that row is replaced on every
re-upload), so a profile whose id no longer matches is stale. ``error`` is an
error code, never a raw message.

Docs: api/views/query_engine/architecture.md
"""

import uuid

from django.db import models
from django.db.models import Q

from api.models.QeSummaryFields import QeSummaryFields


class ResourceProfileStatus(models.TextChoices):
    READY = "READY"
    FAILED = "FAILED"


class ResourceProfile(QeSummaryFields):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resource = models.OneToOneField(
        "api.Resource", on_delete=models.CASCADE, related_name="qe_profile"
    )
    data_table_id = models.UUIDField()
    profiler_version = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=16, choices=ResourceProfileStatus.choices)
    error = models.CharField(max_length=64, null=True, blank=True)
    failed_attempts = models.PositiveIntegerField(default=0)
    retry_after = models.DateTimeField(null=True, blank=True)
    stats = models.JSONField(null=True, blank=True)
    facts_hash = models.CharField(max_length=64, blank=True, default="")
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "qe_resource_profile"
        indexes = [
            # Pending summaries: filter(summary_needed=True).order_by("modified").
            models.Index(
                fields=["modified"],
                name="qe_rp_summary_needed_idx",
                condition=Q(summary_needed=True),
            )
        ]

    def __str__(self) -> str:
        return f"profile of {self.resource_id} ({self.status})"
