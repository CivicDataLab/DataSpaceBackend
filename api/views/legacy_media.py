"""
legacy_media
────────────
Keeps links issued before the move to S3 working. Media used to be served from
disk at ``/public/<name>``; that path now redirects to the file's S3 URL.

Names are normalised first: rows created on disk carried a ``files/public/`` or
``files/`` prefix that S3 keys no longer have, so ``/public/files/public/x.png``
redirects to the file now stored as ``x.png``.

Only public files redirect. The old route also exposed resources and draft
files whenever DEBUG was on; anything not in public storage is a 404 here, so
this route can never hand out a private object.
"""

import posixpath

from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse

from api.utils.storage import normalize_media_name, public_storage


def legacy_media_redirect(request: HttpRequest, name: str) -> HttpResponse:
    """Redirect an old ``/public/<name>`` link to the public file's S3 URL, else 404."""
    normalised = posixpath.normpath(name)
    if normalised != name or normalised.startswith(("/", "..")):
        return JsonResponse({"error": "Not found"}, status=404)

    storage = public_storage()
    current = normalize_media_name(name)
    if not storage.exists(current):
        return JsonResponse({"error": "Not found"}, status=404)

    response = HttpResponseRedirect(storage.url(current))
    response["Cache-Control"] = "public, max-age=86400"
    return response
