"""Permanent public links: a short random ``public_id`` plus readable title words.

A link looks like ``city-air-quality-index-k3x9m2qa7b1z``. Only the last part,
the ``public_id``, finds the record; the words come from the current title and
are there for people to read. Renaming a record changes the words, never the
id, so old links keep working.

``public_id`` is unique per table, enforced by the database unique index. It is
never checked before saving (a check and an insert can race); a clash makes the
insert fail, and the save is retried with a new id.
"""

from __future__ import annotations

import re
import secrets
import string
import uuid
from typing import Callable, Optional

from django.db import IntegrityError, models, transaction
from django.utils.text import slugify

PUBLIC_ID_LENGTH = 12
PUBLIC_ID_ALPHABET = string.ascii_lowercase + string.digits
URL_SLUG_WORDS_MAX = 50

_PUBLIC_ID_RE = re.compile(rf"[a-z0-9]{{{PUBLIC_ID_LENGTH}}}")


def generate_public_id() -> str:
    """12 random characters from a-z and 0-9 (36^12, about 4.7 x 10^18 values)."""
    return "".join(secrets.choice(PUBLIC_ID_ALPHABET) for _ in range(PUBLIC_ID_LENGTH))


def save_with_public_id(
    instance: models.Model,
    save_fn: Callable[[], None],
    field: str = "public_id",
    max_attempts: int = 5,
) -> None:
    """Save ``instance``, giving it a new ``public_id`` first if it has none.

    If the insert fails because another row already has that id, a new id is
    generated and the save runs again. Any other database error is raised
    unchanged. Each attempt runs in its own savepoint, so a failed attempt does
    not break the caller's transaction.
    """
    if getattr(instance, field):
        save_fn()
        return

    for attempt in range(1, max_attempts + 1):
        setattr(instance, field, generate_public_id())
        try:
            with transaction.atomic():
                save_fn()
            return
        except IntegrityError as exc:
            if field not in str(exc) or attempt == max_attempts:
                raise


def build_url_slug(title: Optional[str], public_id: str) -> str:
    """Link part for a record: title words (max 50 chars, cut between words) + id.

    Returns only the id when the title has no Latin letters or digits (for
    example a title written only in Hindi), since those are dropped by slugify.
    """
    words = slugify(title or "")
    if len(words) > URL_SLUG_WORDS_MAX:
        cut = words[: URL_SLUG_WORDS_MAX + 1].rsplit("-", 1)[0]
        # A single word longer than the limit has no boundary to cut at.
        words = cut if len(cut) <= URL_SLUG_WORDS_MAX else words[:URL_SLUG_WORDS_MAX]
        words = words.strip("-")
    return f"{words}-{public_id}" if words else public_id


def parse_public_id(link_part: Optional[str]) -> Optional[str]:
    """The ``public_id`` at the end of a link part, or None if there is none.

    ``city-air-quality-index-k3x9m2qa7b1z`` and ``k3x9m2qa7b1z`` both give
    ``k3x9m2qa7b1z``. A UUID or a number gives None. An old slug whose last word
    happens to be 12 letters long does parse, so callers should fall back to
    their old lookup both when this returns None and when no record has the id.
    """
    if not link_part:
        return None
    link_part = link_part.strip().strip("/")
    # A UUID's last group is also 12 hex characters; it is an old link, not an id.
    try:
        uuid.UUID(link_part)
        return None
    except ValueError:
        pass
    candidate = link_part.rsplit("-", 1)[-1].lower()
    return candidate if _PUBLIC_ID_RE.fullmatch(candidate) else None


def fill_missing_public_ids(model: type[models.Model], field: str = "public_id") -> int:
    """Give every row of ``model`` that has no ``public_id`` a new one.

    For data migrations that add the column to an existing table, run before the
    unique index is added. Uniqueness is kept here with a set of ids already in
    the table, since the index that would catch a clash does not exist yet.
    Returns the number of rows filled.
    """
    manager = model._default_manager  # type: ignore[attr-defined]
    used = set(manager.exclude(**{f"{field}__isnull": True}).values_list(field, flat=True))
    filled = 0
    for pk in list(manager.filter(**{f"{field}__isnull": True}).values_list("pk", flat=True)):
        value = generate_public_id()
        while value in used:
            value = generate_public_id()
        used.add(value)
        manager.filter(pk=pk).update(**{field: value})
        filled += 1
    return filled
