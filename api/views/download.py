import asyncio
import concurrent
import os

import magic
from django.http import HttpResponse
# from pyecharts.render import make_snapshot
from pyecharts_snapshot.main import make_a_snapshot
# from snapshot_selenium import snapshot

from api.models import Resource, ResourceChartDetails
from api.types.type_resource_chart import chart_base


async def download(request, type, id):
    if type == "resource":
        resource = Resource.objects.get(pk=id)
        file_path = resource.resourcefiledetails.file.name
        if len(file_path):
            mime_type = magic.from_buffer(resource.resourcefiledetails.file.read(), mime=True)
            response = HttpResponse(resource.resourcefiledetails.file, content_type=mime_type)
            response['Content-Disposition'] = 'attachment; filename="{}"'.format(os.path.basename(file_path))
        else:
            response = HttpResponse("file doesnt exist", content_type='text/plain')
        return response
    elif type == "chart":
        resource_chart = ResourceChartDetails.objects.get(pk=id)
        response = await generate_chart(resource_chart)
        response['Content-Disposition'] = 'attachment; filename="chart.png"'
        return response


async def generate_chart(resource_chart: ResourceChartDetails):
    chart_ = chart_base(resource_chart)
    chart_.render("snapshot.html")
    image_file_name = "snapshot.png"
    # loop = asyncio.new_event_loop()
    # asyncio.set_event_loop(loop)
    # loop.run_until_complete(make_a_snapshot("snapshot.html", image_file_name))
    # loop.close()
    await make_a_snapshot("snapshot.html", image_file_name)
    # await make_snapshot(snapshot, "snapshot.html", image_file_name)
    with open(image_file_name, "rb") as f:
        image_data = f.read()
    return HttpResponse(image_data, content_type="image/png")
