import asyncio
import concurrent
import os

import magic
from asgiref.sync import sync_to_async
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
# from pyecharts.render import make_snapshot
from pyecharts_snapshot.main import make_a_snapshot
# from snapshot_selenium import snapshot

from api.models import Resource, ResourceChartDetails
from api.types.type_resource_chart import chart_base


@sync_to_async
def get_resource_chart(id):
    return ResourceChartDetails.objects.get(pk=id)


@sync_to_async
def get_resource(id):
    return Resource.objects.get(pk=id)


async def download(request, type, id):
    if type == "resource":
        try:
            # Fetch the resource asynchronously
            resource = await get_resource(id)
            file_path = resource.resourcefiledetails.file.name

            if len(file_path):
                # Use magic to get MIME type
                mime_type = magic.from_buffer(resource.resourcefiledetails.file.read(), mime=True)
                response = HttpResponse(resource.resourcefiledetails.file, content_type=mime_type)
                response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
            else:
                response = HttpResponse("File doesn't exist", content_type='text/plain')
        except ObjectDoesNotExist:
            response = HttpResponse("Resource not found", content_type='text/plain')

        return response

    elif type == "chart":
        try:
            # Fetch the chart asynchronously
            resource_chart = await get_resource_chart(id)

            # Assuming generate_chart is an async function
            response = await generate_chart(resource_chart)
            response['Content-Disposition'] = 'attachment; filename="chart.png"'
            return response

        except ObjectDoesNotExist:
            return HttpResponse("Chart not found", content_type='text/plain')


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
