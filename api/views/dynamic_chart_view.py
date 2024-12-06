import json

from asgiref.sync import sync_to_async
from django.http import JsonResponse

from api.models import ResourceChartDetails, ResourceSchema, Resource
from api.types.type_resource_chart import chart_base
from api.utils.enums import ChartTypes


async def create_chart_details(request, resource):
    # Parse parameters from the request
    chart_type = request.POST.get('chart_type')
    x_axis_label = request.POST.get('x_axis_label', 'X-Axis')
    y_axis_label = request.POST.get('y_axis_label', 'Y-Axis')
    x_axis_column = request.POST.get('x_axis_column')
    y_axis_column = request.POST.get('y_axis_column')
    region_column = request.POST.get('region_column')
    value_column = request.POST.get('value_column')
    aggregate_type = request.POST.get('aggregate_type', 'none')
    show_legend = request.POST.get('show_legend', False)

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
            field_name=x_axis_column) if x_axis_column else None,
        y_axis_column=await sync_to_async(ResourceSchema.objects.get)(
            field_name=y_axis_column) if y_axis_column else None,
        region_column=await sync_to_async(ResourceSchema.objects.get)(
            field_name=region_column) if region_column else None,
        value_column=await sync_to_async(ResourceSchema.objects.get)(field_name=value_column) if value_column else None,
        aggregate_type=aggregate_type,
        show_legend=show_legend
    )


async def generate_dynamic_chart(request, resource_id):
    if request.method == "POST":
        try:
            # Fetch the resource asynchronously
            resource = await sync_to_async(Resource.objects.get)(id=resource_id)
        except Resource.DoesNotExist:
            return JsonResponse({'error': 'Resource not found'}, status=404)

        # Validate and process chart details
        chart_details = await create_chart_details(request, resource)
        if isinstance(chart_details, JsonResponse):
            return chart_details

        # Generate the chart using chart_base
        try:
            chart = await sync_to_async(chart_base)(chart_details)
            if chart:
                return JsonResponse(json.loads(chart.dump_options_with_quotes()), safe=False)
            else:
                return JsonResponse({'error': 'Failed to generate chart'}, status=400)
        except Exception as e:
            return JsonResponse({'error': f'Error generating chart: {e}'}, status=500)

    else:
        return JsonResponse({'error': 'Invalid HTTP method'}, status=405)
