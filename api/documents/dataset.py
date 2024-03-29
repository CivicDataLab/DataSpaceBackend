from django_elasticsearch_dsl import Document, fields
from django_elasticsearch_dsl.registries import registry
from api.models import Dataset, Resource, Metadata, DatasetMetadata


@registry.register_document
class DatasetDocument(Document):
    metadata = fields.ObjectField(
        properties={
            'value': fields.TextField(),
            'metadata_item': fields.ObjectField(
                properties={'label': fields.TextField()}
            )
        }
    )

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

        related_models = [Resource, Metadata, DatasetMetadata]

    # def get_queryset(self):
    #     return super(DatasetDocument, self).get_queryset().select_related(
    #         'DatasetMetadata'
    #     )

    def get_instances_from_related(self, related_instance):
        if isinstance(related_instance, Resource):
            return related_instance.dataset
        elif isinstance(related_instance, Metadata):
            ds_metadata_objects = related_instance.datasetmetadata_set.all()
            return [obj.dataset_set.all() for obj in ds_metadata_objects]
        elif isinstance(related_instance, DatasetMetadata):
            return related_instance.dataset
