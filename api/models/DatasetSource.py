import uuid

from django.db import models

from api.utils.enums import ImportPlatform


class DatasetSource(models.Model):
    """Provenance record for a dataset imported from a third-party platform.

    Imports are link-only: DataSpace never copies the platform's files. This
    row holds what the platform told us about the dataset, in typed columns.
    Every column here has a reader: either a metadata standard on export
    (DCAT / Croissant / Dublin Core) or the platform itself (attribution,
    duplicate detection, licence review). No raw payload is kept.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dataset = models.OneToOneField("api.Dataset", on_delete=models.CASCADE, related_name="source")
    platform = models.CharField(max_length=50, choices=ImportPlatform.choices)

    # --- identity on the platform ------------------------------------------
    # Platform-native identifier, e.g. "owner/dataset-slug" (Kaggle) or
    # "namespace/name" (Hugging Face). Normalised by the importer.
    source_identifier = models.CharField(max_length=300)
    # Human-facing page on the platform. Export: schema:sameAs / prov:wasDerivedFrom.
    source_url = models.URLField(max_length=500)
    # Home page declared by the source, if any (GitHub `homepage`). Export: dcat:landingPage.
    source_homepage = models.URLField(max_length=500, blank=True)
    # Commit hash (Hugging Face / GitHub) or version number (Kaggle) at import time.
    # Export: Croissant `version`. Later: what a sync compares against.
    revision = models.CharField(max_length=64, blank=True)

    # --- descriptive metadata the standards read ----------------------------
    # Who made the data on the platform. Export: dcterms:creator / Croissant creator.
    source_author = models.CharField(max_length=300, blank=True)
    # License string exactly as the platform reported it (may not map onto
    # DatasetLicense; the mapped value lives on Dataset.license).
    source_license = models.CharField(max_length=300, blank=True)
    # Full dataset card / README. Dataset.description keeps a 1,000-char cut.
    source_readme = models.TextField(blank=True)
    # BibTeX or free-text citation, when the platform provides one. Export: Croissant citeAs.
    citation = models.TextField(blank=True)
    # Language codes of the data, e.g. ["en", "hi"]. Export: dcterms:language / inLanguage.
    languages = models.JSONField(default=list, blank=True)
    # When the dataset was first published on the platform. Export: dcterms:issued.
    source_created_at = models.DateTimeField(null=True, blank=True)
    # When the platform last changed it. Export: dcterms:modified.
    source_last_updated = models.DateTimeField(null=True, blank=True)
    # Source is frozen / read-only upstream (GitHub `archived`). Shown as a hint.
    is_archived = models.BooleanField(default=False)

    # --- our side -------------------------------------------------------------
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
