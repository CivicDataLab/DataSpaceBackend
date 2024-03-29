from elasticsearch_dsl import Q
from rest_framework import serializers

from api.documents import DatasetDocument
from api.models import DatasetMetadata, Metadata, Dataset
from api.views.paginated_elastic_view import PaginatedElasticSearchAPIView


class MetadataSerializer(serializers.Serializer):
    label = serializers.CharField()
# class MetadataSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Metadata
#         fields = "__all__"


class DatasetMetadataSerializer(serializers.ModelSerializer):
    metadata_item = MetadataSerializer()

    class Meta:
        model = DatasetMetadata
        fields = ["metadata_item", "value"]


class DatasetSerializer(serializers.ModelSerializer):
    metadata = DatasetMetadataSerializer(many=True)

    class Meta:
        model = Dataset
        fields = "__all__"


class SearchDataset(PaginatedElasticSearchAPIView):
    serializer_class = DatasetSerializer
    document_class = DatasetDocument

    def generate_q_expression(self, query):
        return Q("bool",
                 should=[
                     Q("match", **{"metadata.value": query}),
                 ], minimum_should_match=1)
