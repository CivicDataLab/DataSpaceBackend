from django_elasticsearch_dsl import Document, fields, Index
from elasticsearch_dsl import Keyword

from api.models import Dataset, Resource, Metadata, DatasetMetadata
from dataexbackend import settings
from search.documents.analysers import html_strip, ngram_analyser

# from elasticsearch_dsl.search_base import AggsProxy

INDEX = Index(settings.ELASTICSEARCH_INDEX_NAMES[__name__])
INDEX.settings(
    number_of_shards=1,
    number_of_replicas=0
)


@INDEX.doc_type
class DatasetDocument(Document):
    metadata = fields.ObjectField(
        properties={
            'value': fields.TextField(
                analyzer=ngram_analyser
            ),
            'raw': fields.KeywordField(multi=True),
            'metadata_item': fields.ObjectField(
                properties={'label': fields.TextField(
                    analyzer=ngram_analyser
                )}
            )
        }
    )

    resources = fields.ObjectField(
        properties={
            'name': fields.TextField(
                analyzer=ngram_analyser
            ),
            'description': fields.TextField(
                analyzer=html_strip
            )
        }
    )

    title = fields.TextField(
        analyzer=ngram_analyser,
        fields={
            'raw': fields.TextField(analyzer='keyword'),
        }
    )

    description = fields.TextField(
        analyzer=html_strip,
        fields={
            'raw': fields.TextField(analyzer='keyword'),
        }
    )

    tags = fields.TextField(
        attr='tags_indexing',
        analyzer=ngram_analyser,
        fields={
            'raw': fields.KeywordField(multi=True),
            'suggest': fields.CompletionField(multi=True),
        },
        multi=True
    )

    # tags = Keyword(multi=True)

    class Django:
        model = Dataset

        fields = [
            'id',
            'created',
            'modified',
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
