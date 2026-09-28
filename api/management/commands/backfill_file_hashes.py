"""Compute the SHA-256 of resource files uploaded before the column existed.

    python manage.py backfill_file_hashes            # fill every missing hash
    python manage.py backfill_file_hashes --dry-run  # only count

Writes through a queryset update, so the DVC versioning signal does not run.
"""

from django.core.management.base import BaseCommand

from api.models import ResourceFileDetails
from api.models.Resource import compute_sha256


class Command(BaseCommand):
    help = "Fill ResourceFileDetails.sha256 for files that have none."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report only; write nothing.")

    def handle(self, *args, **options):
        pending = (
            ResourceFileDetails.objects.filter(sha256__isnull=True)
            .exclude(file="")
            .select_related("resource")
            .order_by("id")
        )
        total = pending.count()
        self.stdout.write(f"{total} file(s) without a hash")
        if options["dry_run"]:
            return
        done = failed = 0
        for details in pending.iterator():
            digest = compute_sha256(details.file)
            if digest is None:
                failed += 1
                self.stderr.write(
                    f"  skipped {details.resource_id}: file unreadable ({details.file.name})"
                )
                continue
            ResourceFileDetails.objects.filter(pk=details.pk).update(sha256=digest)
            done += 1
        self.stdout.write(self.style.SUCCESS(f"hashed {done}, skipped {failed}"))
