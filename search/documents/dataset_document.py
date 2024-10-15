from django_elasticsearch_dsl import Document, fields, Index, KeywordField
from elasticsearch_dsl import Keyword

from api.enums import DatasetStatus
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
    metadata = fields.NestedField(properties={
        'value': KeywordField(multi=True),
        'raw': KeywordField(multi=True),
        'metadata_item': fields.ObjectField(properties={
            'label': KeywordField(multi=False)
        })
    })

    resources = fields.NestedField(
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
            'raw': KeywordField(multi=False),
        }
    )

    description = fields.TextField(
        analyzer=html_strip,
        fields={
            'raw': fields.TextField(analyzer='keyword'),
        }
    )

    status = fields.KeywordField()

    tags = fields.TextField(
        attr='tags_indexing',
        analyzer=ngram_analyser,
        fields={
            'raw': fields.KeywordField(multi=True),
            'suggest': fields.CompletionField(multi=True),
        },
        multi=True
    )

    categories = fields.TextField(
        attr='categories_indexing',
        analyzer=ngram_analyser,
        fields={
            'raw': fields.KeywordField(multi=True),
            'suggest': fields.CompletionField(multi=True),
        },
        multi=True
    )
    formats = fields.TextField(
        attr='formats_indexing',
        analyzer=ngram_analyser,
        fields={
            'raw': fields.KeywordField(multi=True),
            'suggest': fields.CompletionField(multi=True),
        },
        multi=True
    )

    # tags = Keyword(multi=True)

    def prepare_metadata(self, instance):
        """Preprocess comma-separated metadata values into arrays."""
        processed_metadata = []
        for meta in instance.metadata.all():
            value_list = [val.strip() for val in meta.value.split(",")] if "," in meta.value else [meta.value]
            processed_metadata.append({
                'value': value_list,
                'metadata_item': {'label': meta.metadata_item.label}
            })
        return processed_metadata

    class Django:
        model = Dataset

        fields = [
            'id',
            'created',
            'modified',
        ]

        related_models = [Resource, Metadata, DatasetMetadata]

    def should_index_object(self, **kwargs):
        return self.status == DatasetStatus.PUBLISHED

    def save(self,*args,**kwargs,):
        if self.status == "PUBLISHED":
            super().save(*args, **kwargs)
        else:
            self.delete(ignore=404)

    def delete(self, *args, **kwargs):
        # Remove the document from Elasticsearch index
        super().delete(*args, **kwargs)

    # def get_queryset(self):
    #     return super(DatasetDocument, self).get_queryset().select_related(
    #         'DatasetMetadata'
    #     )

    def get_instances_from_related(self, related_instance):
        if isinstance(related_instance, Resource):
            return related_instance.dataset
        elif isinstance(related_instance, Metadata):
            ds_metadata_objects = related_instance.datasetmetadata_set.all()
            return [obj.dataset for obj in ds_metadata_objects]
        elif isinstance(related_instance, DatasetMetadata):
            return related_instance.dataset
