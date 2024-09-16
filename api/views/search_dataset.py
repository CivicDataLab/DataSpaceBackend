from elasticsearch_dsl import Q, Search
from rest_framework import serializers

from search.documents import DatasetDocument
from api.enums import MetadataModels
from api.models import DatasetMetadata, Metadata, Dataset
from api.views.paginated_elastic_view import PaginatedElasticSearchAPIView


class MetadataSerializer(serializers.Serializer):
    label = serializers.CharField()


class DatasetMetadataSerializer(serializers.ModelSerializer):
    metadata_item = MetadataSerializer()

    class Meta:
        model = DatasetMetadata
        fields = ["metadata_item", "value"]


class DatasetDocumentSerializer(serializers.ModelSerializer):
    metadata = DatasetMetadataSerializer(many=True)
    tags = serializers.ListField()
    categories = serializers.ListField()

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
        searchable_fields = [
            f"metadata.{e.label}" if e.model == MetadataModels.DATASET else f"resource.{e.label}"
            for e in enabled_metadata
        ]
        searchable_fields.extend(["tags", "description", "resource.description", "resource.name", "title"])
        aggregations = {"tags.raw": "terms", "categories.raw": "terms"}
        for metadata in enabled_metadata:
            if metadata.filterable:
                aggregations[f"metadata.{metadata.label}"] = "terms"
        return searchable_fields, aggregations

    def add_aggregations(self, search: Search):
        aggregate_fields = []
        for aggregation_field in self.aggregations:
            if aggregation_field.startswith('metadata.'):
                field_name = aggregation_field.split('.')[1]
                aggregate_fields.append(field_name)
            else:
                search.aggs.bucket(aggregation_field, self.aggregations[aggregation_field], field=aggregation_field)
        if aggregate_fields:
            metadata_bucket = search.aggs.bucket('metadata', 'nested', path='metadata')
            for field in aggregate_fields:
                label_bucket = metadata_bucket.bucket(field, 'terms', field='metadata.metadata_item.label')
                label_bucket.bucket(f'{field}_values', 'terms', field='metadata.value')
                # metadata_bucket.bucket(field, 'terms', field=f'metadata.value')
        return search
    def generate_q_expression(self, query):
        if query:
            queries = [Q("match", **{field: query}) for field in self.searchable_fields]
        else:
            queries = [Q("match_all")]
        return Q("bool", should=queries, minimum_should_match=1)

    # def add_aggregations(self, search: Search):
    #     for aggregation_field in self.aggregations:
    #         search.aggs.bucket(aggregation_field, self.aggregations[aggregation_field], field=aggregation_field)
    #     return search

    def add_filters(self, filters, search: Search):
        for filter in filters:
            raw_filter = filter + '.raw'
            if raw_filter in self.aggregations:
                search = search.filter("terms", **{raw_filter: filters[filter].split(',')})
            else:
                search = search.filter("term", **{filter: filters[filter]})
        return search
