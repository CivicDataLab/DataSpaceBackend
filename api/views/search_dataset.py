import ast

from elasticsearch_dsl import Q, Search, A
from rest_framework import serializers

from search.documents import DatasetDocument
from api.models import DatasetMetadata, Metadata, Dataset
from api.views.paginated_elastic_view import PaginatedElasticSearchAPIView


class MetadataSerializer(serializers.Serializer):
    label = serializers.CharField()


class DatasetMetadataSerializer(serializers.ModelSerializer):
    metadata_item = MetadataSerializer()

    class Meta:
        model = DatasetMetadata
        fields = ["metadata_item", "value"]

    # Override to convert list or stringified array to comma-separated string when representing
    def to_representation(self, instance):
        representation = super().to_representation(instance)

        # Check if the value is a stringified array and convert it into a list
        if isinstance(representation['value'], str):
            try:
                # Convert stringified array (e.g., "['Monthly']") to a list
                value_list = ast.literal_eval(representation['value'])
                # If it is a list, convert to comma-separated string
                if isinstance(value_list, list):
                    representation['value'] = ', '.join(value_list)
            except (ValueError, SyntaxError):
                # If it's not a stringified array, leave it as is
                pass

        return representation

    # Override to handle input and convert comma-separated string to list when validating
    def to_internal_value(self, data):
        if isinstance(data.get('value'), str):
            try:
                # If the value is a comma-separated string, convert it to a list
                data['value'] = data['value'].split(', ')
            except (ValueError, SyntaxError):
                # If there's an error, just keep the original string value
                pass

        return super().to_internal_value(data)


class DatasetDocumentSerializer(serializers.ModelSerializer):
    metadata = DatasetMetadataSerializer(many=True)
    tags = serializers.ListField()
    categories = serializers.ListField()
    formats = serializers.ListField()

    class Meta:
        model = Dataset
        fields = "__all__"


class SearchDataset(PaginatedElasticSearchAPIView):
    serializer_class = DatasetDocumentSerializer
    document_class = DatasetDocument

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.searchable_fields, self.aggregations = self.get_searchable_and_aggregations()

    @staticmethod
    def get_searchable_and_aggregations():
        enabled_metadata = Metadata.objects.filter(enabled=True).all()
        searchable_fields = []
        # searchable_fields = [
        #     f"metadata.{e.label}" if e.model == MetadataModels.DATASET else f"resource.{e.label}"
        #     for e in enabled_metadata
        # ]
        searchable_fields.extend(
            ["tags", "description", "resources.description", "resources.name", "title", "metadata.value"])
        aggregations = {"tags.raw": "terms", "categories.raw": "terms", "formats.raw": "terms"}
        for metadata in enabled_metadata:
            if metadata.filterable:
                aggregations[f"metadata.{metadata.label}"] = "terms"
        return searchable_fields, aggregations

    # def add_aggregations(self, search: Search):
    #     aggregate_fields = []
    #     for aggregation_field in self.aggregations:
    #         if aggregation_field.startswith('metadata.'):
    #             field_name = aggregation_field.split('.')[1]
    #             aggregate_fields.append(field_name)
    #         else:
    #             search.aggs.bucket(aggregation_field, self.aggregations[aggregation_field], field=aggregation_field)
    #     if aggregate_fields:
    #         metadata_bucket = search.aggs.bucket('metadata', 'nested', path='metadata')
    #         for field in aggregate_fields:
    #             metadata_bucket.bucket(field, 'multi_terms', terms={
    #                 'field': 'metadata.value',
    #                 'include': {
    #                     'filter': {
    #                         'term': {'metadata.metadata_item.label': field}
    #                     }
    #                 }
    #             })
    #             # metadata_bucket.bucket(field, 'terms', field=f'metadata.value')
    #     return search

    def add_aggregations(self, search: Search):
        """
        Add aggregations to the search query for metadata value and label using composite aggregation.
        """
        aggregate_fields = []
        for aggregation_field in self.aggregations:
            if aggregation_field.startswith('metadata.'):
                field_name = aggregation_field.split('.')[1]
                aggregate_fields.append(field_name)
            else:
                search.aggs.bucket(aggregation_field.replace(".raw", ""), self.aggregations[aggregation_field],
                                   field=aggregation_field)

        if aggregate_fields:
            filterable_metadata = Metadata.objects.filter(filterable=True).values('label')
            filterable_metadata = [meta['label'] for meta in filterable_metadata]

            metadata_bucket = search.aggs.bucket('metadata', 'nested', path='metadata')
            composite_agg = A('composite', sources=[
                {'metadata_label': {'terms': {'field': 'metadata.metadata_item.label'}}},
                {'metadata_value': {'terms': {'field': 'metadata.value'}}}
            ], size=10000)
            metadata_filter = A('filter', {
                'bool': {
                    'must': [
                        {'terms': {'metadata.metadata_item.label': filterable_metadata}}  # Exclude labels here
                    ]
                }
            })
            metadata_bucket.bucket('filtered_metadata', metadata_filter).bucket('composite_agg', composite_agg)
        return search

    def generate_q_expression(self, query):
        if query:
            queries = []
            for field in self.searchable_fields:
                if field.startswith('resources.name') or field.startswith('resources.description'):
                    # Combine both fuzzy and wildcard for resource fields
                    queries.append(
                        Q('nested', path='resources', query=Q("bool", should=[
                            Q("wildcard", **{
                                field: {
                                    "value": f"*{query}*"
                                }
                            }),
                            Q("fuzzy", **{
                                field: {
                                    "value": query,
                                    "fuzziness": "AUTO"
                                }
                            })
                        ]))
                    )
                else:
                    # For other fields, we can just use a regular match or fuzzy match
                    queries.append(Q("fuzzy", **{field: {"value": query, "fuzziness": "AUTO"}}))
        else:
            queries = [Q("match_all")]

        return Q("bool", should=queries, minimum_should_match=1)

    # def add_aggregations(self, search: Search):
    #     for aggregation_field in self.aggregations:
    #         search.aggs.bucket(aggregation_field, self.aggregations[aggregation_field], field=aggregation_field)
    #     return search

    def add_filters(self, filters, search: Search):
        non_filter_metadata = Metadata.objects.filter(filterable=False).all()
        excluded_labels = [e.label for e in non_filter_metadata]

        for filter in filters:
            if filter in excluded_labels:
                continue
            elif filter in ["tags", "categories", "formats"]:
                raw_filter = filter + '.raw'
                if raw_filter in self.aggregations:
                    search = search.filter("terms", **{raw_filter: filters[filter].split(',')})
                else:
                    search = search.filter("term", **{filter: filters[filter]})
            # TODO: Handle resource metadata
            else:
                search = search.filter(
                    'nested',
                    path='metadata',
                    query={
                        'bool': {
                            'must': {
                                'term': {f'metadata.value': filters[filter]}
                            }
                        }
                    }
                )
        return search

    def add_sort(self, sort, search):
        if sort == "alphabetical":
            search = search.sort({"title.raw": {"order": "asc"}})
        if sort == "recent":
            search = search.sort({"modified": {"order": "desc"}})
        return search
