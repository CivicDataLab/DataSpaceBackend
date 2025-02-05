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

    # Validate chart type
    if chart_type not in ChartTypes.values:
        return JsonResponse({'error': f'Unsupported chart type: {chart_type}'}, status=400)

    # Extract filters
    request_filters = request_details.get('filters', [])
    filters = []
    for request_filter in request_filters:
        filter = {}
        filter['column'] = await sync_to_async(ResourceSchema.objects.get)(field_name=request_filter['column'],
                                                                           resource=resource)
        filter['operator'] = request_filter['operator']
        filter['value'] = request_filter['value']
        filters.append(filter)

    # Build options dictionary
    options = {
        'x_axis_label': request_details.get('x_axis_label', 'X-Axis'),
        'y_axis_label': request_details.get('y_axis_label', 'Y-Axis'),
        'show_legend': request_details.get('show_legend', False),
        'aggregate_type': request_details.get('aggregate_type', 'none')
    }

    # Add column references to options
    if x_axis_column := request_details.get('x_axis_column'):
        options['x_axis_column'] = await sync_to_async(ResourceSchema.objects.get)(
            field_name=x_axis_column, resource=resource)

    # Handle y-axis columns
    y_axis_columns = []
    
    # Then check for y-axis column list
    if y_axis_column_list := request_details.get('y_axis_column_list'):
        columns = y_axis_column_list.split(',')
        for column in columns:
            if column not in [col.field_name for col in y_axis_columns]:  # Avoid duplicates
                y_axis_columns.append(await sync_to_async(ResourceSchema.objects.get)(
                    field_name=column, resource=resource))
    
    if y_axis_columns:
        options['y_axis_column'] = y_axis_columns

    if region_column := request_details.get('region_column'):
        options['region_column'] = await sync_to_async(ResourceSchema.objects.get)(
            field_name=region_column, resource=resource)

    if value_column := request_details.get('value_column'):
        options['value_column'] = await sync_to_async(ResourceSchema.objects.get)(
            field_name=value_column, resource=resource)

    # Validate required columns based on chart type
    if chart_type in ['BAR_VERTICAL', 'BAR_HORIZONTAL', 'LINE']:
        if 'x_axis_column' not in options or 'y_axis_column' not in options:
            return JsonResponse({'error': 'Missing required parameters: x_axis_column or y_axis_column'}, status=400)
        if chart_type != 'GROUPED_BAR_VERTICAL' and chart_type != 'GROUPED_BAR_HORIZONTAL' and len(options['y_axis_column']) > 1:
            return JsonResponse({'error': 'Single column charts can only have one y_axis_column'}, status=400)
    elif chart_type in ['GROUPED_BAR_VERTICAL', 'GROUPED_BAR_HORIZONTAL']:
        if 'x_axis_column' not in options or 'y_axis_column' not in options:
            return JsonResponse({'error': 'Missing required parameters: x_axis_column or y_axis_column'}, status=400)
        if len(options['y_axis_column']) <= 1:
            return JsonResponse({'error': 'Grouped bar charts require multiple y_axis_columns'}, status=400)
    elif chart_type in ['ASSAM_DISTRICT', 'ASSAM_RC']:
        if 'region_column' not in options or 'value_column' not in options:
            return JsonResponse({'error': 'Missing required parameters: region_column or value_column'}, status=400)

    # Create ResourceChartDetails instance without saving it
    return ResourceChartDetails(
        resource=resource,
        chart_type=chart_type,
        options=options,
        filters=filters
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
