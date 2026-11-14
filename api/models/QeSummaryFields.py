"""The model-written summary stored on a query-engine profile.

Shared by ResourceProfile and DatasetProfile. A summary is written by the
query engine from the profile's facts; it is served and indexed only while
``summary_facts_hash`` equals the profile's current ``facts_hash``, and is
always labelled as generated. ``summary_needed`` and ``summary_rejections``
are reset whenever the facts change.

Docs: api/views/query_engine/architecture.md
"""

from django.db import models


class QeSummaryFields(models.Model):
    summary_text = models.TextField(blank=True, default="")
    summary_facts_hash = models.CharField(max_length=64, blank=True, default="")
    summary_model = models.CharField(max_length=200, blank=True, default="")
    summary_prompt_version = models.CharField(max_length=64, blank=True, default="")
    summary_generated_at = models.DateTimeField(null=True, blank=True)
    summary_needed = models.BooleanField(default=False)
    summary_rejections = models.PositiveSmallIntegerField(default=0)

    class Meta:
        abstract = True
