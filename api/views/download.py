import os

import magic
from django.http import HttpResponse

from api.models import Resource


def download(request, type, id):
    resource = Resource.objects.get(pk=id)
    file_path = resource.resourcefiledetails.file.name
    if len(file_path):
        mime_type = magic.from_buffer(resource.resourcefiledetails.file.read(), mime=True)
        response = HttpResponse(resource.resourcefiledetails.file, content_type=mime_type)
        response['Content-Disposition'] = 'attachment; filename="{}"'.format(os.path.basename(file_path))
    else:
        response = HttpResponse("file doesnt exist", content_type='text/plain')
    return response
