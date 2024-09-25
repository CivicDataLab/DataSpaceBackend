import asyncio
import concurrent
import os

import magic
from asgiref.sync import sync_to_async
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from pyecharts.render import make_snapshot
from pyecharts_snapshot.main import make_a_snapshot
# from snapshot_selenium import Snapshot
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from snapshot_selenium import snapshot

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


# Configure Selenium WebDriver with no-sandbox option
def get_custom_webdriver():
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")  # Bypass OS security model
    chrome_options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems
    chrome_options.add_argument("--headless")  # Run headless browser
    chrome_options.add_argument("--disable-gpu")  # Disable GPU for headless browser

    # Specify path to ChromeDriver
    driver = webdriver.Chrome(options=chrome_options)
    return driver


async def generate_chart(resource_chart: ResourceChartDetails):
    chart_ = await sync_to_async(chart_base)(resource_chart)
    chart_.render("snapshot.html")
    image_file_name = "snapshot.png"
    # loop = asyncio.new_event_loop()
    # asyncio.set_event_loop(loop)
    # loop.run_until_complete(make_a_snapshot("snapshot.html", image_file_name))
    # loop.close()

    # Create a custom snapshot instance using the custom WebDriver
    # snapshot = Snapshot(webdriver=get_custom_webdriver())

    # await make_snapshot(get_custom_webdriver(), "snapshot.html", image_file_name)
    webdriver = get_custom_webdriver()
    make_snapshot(snapshot, "snapshot.html", image_file_name, driver=webdriver)
    with open(image_file_name, "rb") as f:
        image_data = f.read()
    return HttpResponse(image_data, content_type="image/png")
