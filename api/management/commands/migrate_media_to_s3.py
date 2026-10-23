"""Bring every stored file into S3 under its current, prefix-free name.

    python manage.py migrate_media_to_s3                                 # dry run
    python manage.py migrate_media_to_s3 --execute                       # copy + rename
    python manage.py migrate_media_to_s3 --source /code/files/public --execute

Rows created on disk carry a ``files/public/`` or ``files/`` prefix that the S3
keys no longer use (see ``normalize_media_name``). For each stored name this
puts the file at the normalised key in the storage its field names, taking it
from the old S3 key or, with ``--source``, from the old disk tree, then points
the row at the new name. Safe to re-run: names already in place are skipped.
Nothing is deleted, neither local files nor old S3 objects.
"""

from collections import Counter
from pathlib import Path
from typing import Any, Iterator, List, Optional, Set, Tuple, Type

import structlog
from django.apps import apps
from django.core.files import File
from django.core.files.storage import Storage
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import models

from api.utils.storage import normalize_media_name

logger = structlog.get_logger("dataspace.commands.migrate_media_to_s3")


def iter_file_fields() -> Iterator[Tuple[Type[models.Model], models.FileField]]:
    """Yield every concrete file field across installed models."""
    for model in apps.get_models():
        for field in model._meta.get_fields():
            if isinstance(field, models.FileField):
                yield model, field


def stored_names(model: Type[models.Model], field: models.FileField) -> List[str]:
    """Distinct non-empty names stored in ``field``."""
    return list(
        model._default_manager.exclude(**{field.name: ""})
        .exclude(**{f"{field.name}__isnull": True})
        .values_list(field.name, flat=True)
        .distinct()
    )


def copy_to(storage: Storage, target: str, fh: Any) -> None:
    """Save ``fh`` under exactly ``target``; the row will point at that name."""
    saved = storage.save(target, File(fh))
    if saved != target:
        storage.delete(saved)
        raise RuntimeError(f"storage renamed {target} to {saved}")


class Command(BaseCommand):
    help = "Copy media into S3 under prefix-free names and point DB rows at them."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--source",
            help="Old MEDIA_ROOT that legacy names are relative to (e.g. /code/files/public)",
        )
        parser.add_argument(
            "--execute", action="store_true", help="Copy and rename; without it, only report."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        source: Optional[Path] = None
        if options["source"]:
            source = Path(options["source"]).resolve()
            if not source.is_dir():
                raise CommandError(f"Source directory not found: {source}")
        execute: bool = options["execute"]

        counts: Counter = Counter()
        seen: Set[str] = set()
        for model, field in iter_file_fields():
            storage = field.storage
            for name in stored_names(model, field):
                target = normalize_media_name(name)
                seen.add(target)
                try:
                    present = self._place(storage, name, target, source, execute, counts)
                    if present and target != name:
                        counts["rows_renamed"] += 1
                        if execute:
                            model._default_manager.filter(**{field.name: name}).update(
                                **{field.name: target}
                            )
                except Exception as exc:
                    counts["failed"] += 1
                    logger.error("media_migration_failed", name=name, error=str(exc))

        if source:
            counts["orphaned"] = sum(
                1
                for p in source.rglob("*")
                # Disk files keep their legacy names; rows may already use the clean ones.
                if p.is_file()
                and normalize_media_name(p.relative_to(source).as_posix()) not in seen
            )

        summary = ", ".join(f"{key}={counts[key]}" for key in sorted(counts))
        logger.info("media_migration_summary", execute=execute, **dict(counts))
        self.stdout.write(f"{'Done' if execute else 'Dry run'}: {summary}")
        if counts["failed"]:
            raise CommandError(f"{counts['failed']} file(s) failed")

    def _place(
        self,
        storage: Storage,
        name: str,
        target: str,
        source: Optional[Path],
        execute: bool,
        counts: Counter,
    ) -> bool:
        """Make sure ``target`` exists in ``storage``; return whether it does (or would)."""
        if storage.exists(target):
            counts["in_place"] += 1
            return True

        if target != name and storage.exists(name):
            counts["moved_in_s3"] += 1
            if execute:
                with storage.open(name, "rb") as fh:
                    copy_to(storage, target, fh)
            return True

        if source is not None:
            local = (source / name).resolve()
            # Names come from the DB; never read outside the source tree.
            if local.is_relative_to(source) and local.is_file():
                counts["copied_from_disk"] += 1
                if execute:
                    with local.open("rb") as fh:
                        copy_to(storage, target, fh)
                return True

        counts["missing"] += 1
        logger.warning("media_source_missing", name=name)
        return False
