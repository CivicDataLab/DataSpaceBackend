import os
import uuid
from typing import Any, BinaryIO, Optional, Union, cast

import magic
from asgiref.sync import sync_to_async
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.uploadedfile import UploadedFile
from django.http import HttpRequest, HttpResponse, JsonResponse
from pyecharts.charts.chart import Chart
from pyecharts.render import make_snapshot
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver
from snapshot_selenium import snapshot

from api.models import Resource, ResourceChartDetails, ResourceChartImage
from api.types.type_resource_chart import chart_base


@sync_to_async
def get_resource_chart(id: uuid.UUID) -> ResourceChartDetails:
    """Get a ResourceChartDetails object by ID."""
    return ResourceChartDetails.objects.get(pk=id)


@sync_to_async
def get_resource_chart_image(id: uuid.UUID) -> ResourceChartImage:
    """Get a ResourceChartImage object by ID."""
    return ResourceChartImage.objects.get(pk=id)


@sync_to_async
def get_resource(id: uuid.UUID) -> Resource:
    """Get resource by id."""
    return Resource.objects.get(id=id)


@sync_to_async
def get_chart_image(id: uuid.UUID) -> ResourceChartImage:
    """Get chart image by id."""
    return ResourceChartImage.objects.get(id=id)


@sync_to_async
def get_resource_response(
    resource: Resource, request: Optional[HttpRequest] = None
) -> HttpResponse:
    """Get file response for a resource."""
    file_details = resource.resourcefiledetails
    if not file_details or not file_details.file:
        return JsonResponse({"error": "File not found"}, status=404)

    response = HttpResponse(
        file_details.file.read(), content_type="application/octet-stream"
    )

    # Handle filename and basename explicitly
    default_name = f"resource_{resource.name}.csv"
    if file_details.file.name:
        filename = str(file_details.file.name)
        # Get last part of path, fallback to default if empty
        parts = filename.split("/")
        basename = parts[-1] if parts else default_name
    else:
        basename = default_name

    # Increment download count
    resource.download_count += 1
    resource.save()

    # Track the download activity if the user is authenticated
    if request and hasattr(request, "user") and request.user.is_authenticated:
        # Import here to avoid circular imports
        import asyncio

        from api.activities.resource import track_resource_downloaded

        asyncio.create_task(
            sync_to_async(track_resource_downloaded)(request.user, resource, request)
        )

    response["Content-Disposition"] = f'attachment; filename="{basename}"'
    return response


@sync_to_async
def get_chart_image_response(chart_image: ResourceChartImage) -> HttpResponse:
    """Get file response for a chart image."""
    if not chart_image.image:
        return JsonResponse({"error": "File not found"}, status=404)

    response = HttpResponse(
        chart_image.image.read(), content_type="application/octet-stream"
    )

    # Handle filename and basename explicitly
    default_name = f"chart_{chart_image.id}.png"
    if chart_image.image.name:
        filename = str(chart_image.image.name)
        # Get last part of path, fallback to default if empty
        parts = filename.split("/")
        basename = parts[-1] if parts else default_name
    else:
        basename = default_name

    response["Content-Disposition"] = f'attachment; filename="{basename}"'
    return response


async def download(request: HttpRequest, type: str, id: uuid.UUID) -> HttpResponse:
    """Handle download requests for resources, chart images, and charts."""
    try:
        if type == "resource":
            try:
                resource = await get_resource(id)
                return await get_resource_response(resource, request)
            except Resource.DoesNotExist:
                return JsonResponse({"error": "Resource not found"}, status=404)
            except Exception as e:
                return JsonResponse({"error": str(e)}, status=500)

        elif type == "chart_image":
            try:
                chart_image = await get_chart_image(id)
                return await get_chart_image_response(chart_image)
            except ResourceChartImage.DoesNotExist:
                return JsonResponse({"error": "Chart image not found"}, status=404)
            except Exception as e:
                return JsonResponse({"error": str(e)}, status=500)

        elif type == "chart":
            try:
                # Fetch the chart asynchronously
                resource_chart = await get_resource_chart(id)

                response = await generate_chart(resource_chart)
                response["Content-Disposition"] = 'attachment; filename="chart.png"'
                return response

            except ObjectDoesNotExist:
                return HttpResponse("Chart not found", content_type="text/plain")

        return HttpResponse("Invalid type", content_type="text/plain")
    except RuntimeError as e:
        if "no running event loop" in str(e):
            import asyncio

            # Create a new event loop if one doesn't exist
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            # Re-run the function with the new loop
            return asyncio.run(download(request, type, id))
        raise


def get_file_resource_response(resource: Resource) -> HttpResponse:
    """Generate an HTTP response for a resource file download."""
    file_obj = cast(UploadedFile, resource.resourcefiledetails.file)
    if file_obj and hasattr(file_obj, "name"):
        # Use magic to get MIME type
        mime_type = magic.from_buffer(file_obj.read(), mime=True)
        file_obj.seek(0)  # Reset file pointer
        response = HttpResponse(file_obj, content_type=mime_type)
        file_name = str(file_obj.name)
        response["Content-Disposition"] = (
            f'attachment; filename="{resource.name}.{os.path.basename(file_name).split(".")[1]}"'
        )
    else:
        response = HttpResponse("File doesn't exist", content_type="text/plain")
    return response


def get_file_chart_image_response(chart_image: ResourceChartImage) -> HttpResponse:
    """Generate an HTTP response for a chart image file download."""
    file_obj = cast(UploadedFile, chart_image.image)
    if file_obj and hasattr(file_obj, "name"):
        # Use magic to get MIME type
        mime_type = magic.from_buffer(file_obj.read(), mime=True)
        file_obj.seek(0)  # Reset file pointer
        response = HttpResponse(file_obj, content_type=mime_type)
        file_name = str(file_obj.name)
        response["Content-Disposition"] = (
            f'attachment; filename="{os.path.basename(file_name)}"'
        )
    else:
        response = HttpResponse("File doesn't exist", content_type="text/plain")
    return response


def get_custom_webdriver() -> WebDriver:
    """Configure and return a custom Selenium WebDriver."""
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")  # Bypass OS security model
    chrome_options.add_argument(
        "--disable-dev-shm-usage"
    )  # Overcome limited resource problems
    chrome_options.add_argument("--headless")  # Run headless browser
    chrome_options.add_argument("--disable-gpu")  # Disable GPU for headless browser

    # Specify path to ChromeDriver
    driver: WebDriver = webdriver.Chrome(options=chrome_options)
    return driver


async def generate_chart(resource_chart: ResourceChartDetails) -> HttpResponse:
    """Generate a chart image from a ResourceChartDetails object."""
    chart_ = cast(Chart, await sync_to_async(chart_base)(resource_chart))
    chart_.render("snapshot.html")

    # Get custom webdriver
    driver = get_custom_webdriver()

    # Make snapshot
    make_snapshot(snapshot, chart_.render(), "chart.png", driver=driver)

    # Clean up
    driver.quit()
    try:
        os.remove("snapshot.html")
    except FileNotFoundError:
        pass

    # Return the image file
    try:
        with open("chart.png", "rb") as f:
            response = HttpResponse(f.read(), content_type="image/png")
        os.remove("chart.png")
    except FileNotFoundError:
        response = HttpResponse("Chart image not found", content_type="text/plain")
    return response
