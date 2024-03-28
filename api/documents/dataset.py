from django_elasticsearch_dsl import Document
from django_elasticsearch_dsl.registries import registry
from api.models import Dataset


@registry.register_document
class DatasetDocument(Document):
    class Index:
        name = 'dataset'
        # See Elasticsearch Indices API reference for available settings
        settings = {'number_of_shards': 1,
                    'number_of_replicas': 0}

    class Django:
        model = Dataset

        fields = [
            'id',
            'created',
            'modified'
        ]
