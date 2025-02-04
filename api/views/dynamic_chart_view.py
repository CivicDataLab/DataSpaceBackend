import json

from asgiref.sync import sync_to_async
from django.http import JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt

from api.models import ResourceChartDetails, ResourceSchema, Resource
from api.types.type_resource_chart import chart_base
from api.utils.enums import ChartTypes
from api.views.download_view import generate_chart


async def create_chart_details(request_details, resource):
    # Parse parameters from the request
    chart_type = request_details.get('chart_type')
    x_axis_label = request_details.get('x_axis_label', 'X-Axis')
    y_axis_label = request_details.get('y_axis_label', 'Y-Axis')
    x_axis_column = request_details.get('x_axis_column')
    y_axis_column = request_details.get('y_axis_column')
    y_axis_column_list = request_details.get('y_axis_column_list').split(',')
    region_column = request_details.get('region_column')
    value_column = request_details.get('value_column')
    aggregate_type = request_details.get('aggregate_type', 'none')
    show_legend = request_details.get('show_legend', False)

    # Validate chart type
    if chart_type not in ChartTypes.values:
        return JsonResponse({'error': f'Unsupported chart type: {chart_type}'}, status=400)

    # Validate required columns based on chart type
    if chart_type in ['BAR_VERTICAL', 'BAR_HORIZONTAL', 'LINE']:
        if not x_axis_column or not y_axis_column:
            return JsonResponse({'error': 'Missing required parameters: x_axis_column or y_axis_column'}, status=400)
    elif chart_type in ['ASSAM_DISTRICT', 'ASSAM_RC']:
        if not region_column or not value_column:
            return JsonResponse({'error': 'Missing required parameters: region_column or value_column'}, status=400)

    # Dynamically create ResourceChartDetails instance without saving it
    return ResourceChartDetails(
        resource=resource,
        chart_type=chart_type,
        x_axis_label=x_axis_label,
        y_axis_label=y_axis_label,
        x_axis_column=await sync_to_async(ResourceSchema.objects.get)(
            field_name=x_axis_column, resource=resource) if x_axis_column else None,
        y_axis_column=await sync_to_async(ResourceSchema.objects.get)(
            field_name=y_axis_column, resource=resource) if y_axis_column else None,
        region_column=await sync_to_async(ResourceSchema.objects.get)(
            field_name=region_column, resource=resource) if region_column else None,
        value_column=await sync_to_async(ResourceSchema.objects.get)(field_name=value_column, resource=resource) if value_column else None,
        aggregate_type=aggregate_type,
        show_legend=show_legend,
        y_axis_column_list=[await sync_to_async(ResourceSchema.objects.get)(
            field_name=column, resource=resource) for column in y_axis_column_list] if y_axis_column_list else None
    )


@csrf_exempt
async def generate_dynamic_chart(request, resource_id):
    if request.method == "POST":
        try:
            # Fetch the resource asynchronously
            resource = await sync_to_async(Resource.objects.get)(id=resource_id)
        except Resource.DoesNotExist:
            return JsonResponse({'error': 'Resource not found'}, status=404)

        # Validate and process chart details
        chart_details = await create_chart_details(json.loads(request.body), resource)
        if isinstance(chart_details, JsonResponse):
            return chart_details

        # Determine response type (default: json)
        response_type = request.GET.get('response_type', 'json').lower()

        # Generate the chart using chart_base
        try:
            chart = await sync_to_async(chart_base)(chart_details)
            if not chart:
                return JsonResponse({'error': 'Failed to generate chart'}, status=400)

            if response_type == 'file':
                response = await generate_chart(chart_details)
                response['Content-Disposition'] = 'attachment; filename="chart.png"'
                return response

            # Default response: JSON
            return JsonResponse(json.loads(chart.dump_options_with_quotes()), safe=False)

        except Exception as e:
            return JsonResponse({'error': f'Error generating chart: {e}'}, status=500)

    return JsonResponse({'error': 'Invalid HTTP method'}, status=405)
