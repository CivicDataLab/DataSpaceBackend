import json

from asgiref.sync import sync_to_async
from django.http import JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt

from api.models import ResourceChartDetails, ResourceSchema, Resource
from api.types.type_resource_chart import chart_base
from api.utils.enums import ChartTypes
from api.views.download_view import generate_chart


async def create_chart_details(request_details: dict, resource: Resource) -> ResourceChartDetails:
    """
    Create chart details from request
    """
    options = {}

    # Set chart type
    chart_type = request_details.get('chart_type')

    # Validate chart type
    if chart_type not in ChartTypes.values:
        return JsonResponse({'error': f'Unsupported chart type: {chart_type}'}, status=400)

    # Set basic options
    options['x_axis_label'] = request_details.get('x_axis_label', 'X-Axis')
    options['y_axis_label'] = request_details.get('y_axis_label', 'Y-Axis')
    options['show_legend'] = request_details.get('show_legend', False)
    options['aggregate_type'] = request_details.get('aggregate_type', 'none')

    # Handle x-axis column
    if x_axis_column := request_details.get('x_axis_column'):
        options['x_axis_column'] = await sync_to_async(ResourceSchema.objects.get)(
            field_name=x_axis_column, resource=resource)

    # Handle y-axis columns with configurations
    if y_axis_configs := request_details.get('y_axis_column', []):
        y_axis_columns = []
        for config in y_axis_configs:
            field = await sync_to_async(ResourceSchema.objects.get)(
                field_name=config['field_name'], resource=resource)
            
            # Convert value mapping from list of mappings
            value_mapping = {}
            value_mapping={}
            raw_mappings = config.get('value_mapping', [])
            if len(raw_mappings):
                value_mapping = {
                    str(mapping['key']): str(mapping['value'])
                    for mapping in raw_mappings
                    if mapping.get('key') is not None and mapping.get('value') is not None
                }
            
            y_axis_columns.append({
                'field': field,
                'label': config.get('label', field.field_name),
                'color': config.get('color'),
                'value_mapping': value_mapping,
                'aggregate_type': config.get('aggregate_type', 'none')
            })

    if y_axis_columns:
        options['y_axis_column'] = y_axis_columns

    # Handle region column
    if region_column := request_details.get('region_column'):
        options['region_column'] = await sync_to_async(ResourceSchema.objects.get)(
            field_name=region_column, resource=resource)

    # Handle value column
    if value_column := request_details.get('value_column'):
        options['value_column'] = await sync_to_async(ResourceSchema.objects.get)(
            field_name=value_column, resource=resource)

    # Handle time column for timeline
    if time_column := request_details.get('time_column'):
        options['time_column'] = await sync_to_async(ResourceSchema.objects.get)(
            field_name=time_column, resource=resource)

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
