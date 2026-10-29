import uuid
from typing import Any

from django.db import models
from django.utils.text import slugify

from api.utils.enums import EventStatus
from api.utils.public_links import PUBLIC_ID_LENGTH, build_url_slug, save_with_public_id


class Event(models.Model):
    """A Luma-backed event owned by an organization or an individual user.

    Peer to Publication: a UUID/slug entity with a draft/publish status. The
    embed is stored as whitelisted iframe attributes, never as raw HTML.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=300, blank=True)
    # Readable words only; not unique. Links and lookups use public_id.
    slug = models.SlugField(max_length=255)
    public_id = models.CharField(max_length=PUBLIC_ID_LENGTH, unique=True, editable=False)
    location = models.CharField(max_length=300, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    luma_embed = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=50,
        default=EventStatus.DRAFT,
        choices=EventStatus.choices,
    )

    organization = models.ForeignKey(
        "api.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    user = models.ForeignKey(
        "authorization.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            self.slug = slugify(self.name)[:255] or "untitled"
        save_with_public_id(self, lambda: super(Event, self).save(*args, **kwargs))

    @property
    def url_slug(self) -> str:
        """Public link part: title words plus public_id, e.g. ``data-meetup-k3x9m2qa7b1z``."""
        return build_url_slug(self.name, self.public_id)

    @property
    def is_individual_event(self) -> bool:
        """True when this event is owned by an individual, not an organization."""
        return self.organization is None and self.user is not None

    def __str__(self) -> str:
        return self.name or "Untitled event"

    class Meta:
        verbose_name = "Event"
        verbose_name_plural = "Events"
        db_table = "event"
        ordering = ["-modified"]
        indexes = [
            models.Index(fields=["organization", "-modified"], name="event_org_modified_idx"),
            models.Index(fields=["user", "-modified"], name="event_user_modified_idx"),
            models.Index(fields=["status"], name="event_status_idx"),
        ]
