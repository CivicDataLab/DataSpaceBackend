import uuid

from django.db import models

from api.utils.enums import ImportPlatform


class DatasetSource(models.Model):
    """Provenance record for a dataset imported from a third-party platform.

    Imports are link-only: DataSpace never copies the platform's files. This
    row remembers where the dataset came from so the UI can attribute it, link
    back to it, and (later) re-sync its metadata. The raw platform response is
    kept in ``raw_metadata`` for debugging and future field mapping.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dataset = models.OneToOneField("api.Dataset", on_delete=models.CASCADE, related_name="source")
    platform = models.CharField(max_length=50, choices=ImportPlatform.choices)
    # Platform-native identifier, e.g. "owner/dataset-slug" (Kaggle) or
    # "namespace/name" (Hugging Face). Normalised by the importer.
    source_identifier = models.CharField(max_length=300)
    # Human-facing page on the platform.
    source_url = models.URLField(max_length=500)
    source_author = models.CharField(max_length=300, blank=True)
    # License string exactly as the platform reported it (may not map onto
    # DatasetLicense; the mapped value lives on Dataset.license).
    source_license = models.CharField(max_length=300, blank=True)
    source_last_updated = models.DateTimeField(null=True, blank=True)
    raw_metadata = models.JSONField(default=dict, blank=True)
    imported_by = models.ForeignKey(
        "authorization.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="imported_dataset_sources",
    )
    imported_at = models.DateTimeField(auto_now_add=True)
    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dataset_source"
        indexes = [models.Index(fields=["platform", "source_identifier"])]

    def __str__(self) -> str:
        return f"{self.platform}:{self.source_identifier}"
