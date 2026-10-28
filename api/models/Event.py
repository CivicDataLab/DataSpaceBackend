import uuid
from typing import Any

from django.db import models
from django.utils.text import slugify

from api.utils.enums import EventStatus


class Event(models.Model):
    """A Luma-backed event owned by an organization or an individual user.

    Peer to Publication: a UUID/slug entity with a draft/publish status. The
    embed is stored as whitelisted iframe attributes, never as raw HTML.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=300, blank=True)
    slug = models.SlugField(max_length=255, unique=True)
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
            base_slug = slugify(self.name) or "untitled"
            slug = base_slug
            counter = 1
            while Event.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

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
