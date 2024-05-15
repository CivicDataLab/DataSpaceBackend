from elasticsearch_dsl import Q
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

    class Meta:
        model = Dataset
        fields = "__all__"


class SearchDataset(PaginatedElasticSearchAPIView):
    serializer_class = DatasetDocumentSerializer
    document_class = DatasetDocument

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        enabled_metadata = Metadata.objects.filter(enabled=True).all()
        self.searchable_fields = [f"metadata.{e.label}" if e.model == MetadataModels.DATASET else f"resoource.{e.label}"
                                  for e in enabled_metadata]
        self.searchable_fields.append("tags")
        self.searchable_fields.append("description")
        self.searchable_fields.append("resource.description")
        self.searchable_fields.append("resource.name")
        self.searchable_fields.append("title")

    def generate_q_expression(self, query):
        if query:
            queries = [Q("match", **{field: query}) for field in self.searchable_fields]
        else:
            queries = [Q("match_all")]
        return Q("bool", should=queries, minimum_should_match=1)
        # return Q(
        #     "multi_match", query=query,
        #     fields=self.searchable_fields, fuzziness="auto")
