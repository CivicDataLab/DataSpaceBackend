"""Media storages for model file fields.

Every ``FileField``/``ImageField`` names one of these through ``storage=``.
They are callables, not instances, so migrations record a function reference
instead of bucket settings, and tests can swap the backend through STORAGES.
"""

from django.core.files.storage import Storage, storages

# Folder prefixes from the on-disk era, when MEDIA_ROOT was files/public and the
# upload_to helpers added their own "files/..." on top. The S3 storages already
# put every key under <env>/public or <env>/private, so these only repeat it.
_LEGACY_PREFIXES = ("files/public/", "files/")


def public_storage() -> Storage:
    """Storage for files anyone may read: unsigned, cacheable URLs."""
    return storages["public"]


def private_storage() -> Storage:
    """Storage for gated files: short-lived presigned URLs only."""
    return storages["private"]


def normalize_media_name(name: str) -> str:
    """Strip the legacy ``files/public/`` or ``files/`` prefix from a stored name.

    ``files/public/organizations/acme/png/logo.png`` -> ``organizations/acme/png/logo.png``.
    Names without a legacy prefix are returned unchanged.
    """
    for prefix in _LEGACY_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name
