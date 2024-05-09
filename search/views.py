from django_elasticsearch_dsl_drf.constants import (
    LOOKUP_FILTER_TERMS,
    LOOKUP_FILTER_RANGE,
    LOOKUP_FILTER_PREFIX,
    LOOKUP_FILTER_WILDCARD,
    LOOKUP_QUERY_IN,
    LOOKUP_QUERY_GT,
    LOOKUP_QUERY_GTE,
    LOOKUP_QUERY_LT,
    LOOKUP_QUERY_LTE,
    LOOKUP_QUERY_EXCLUDE,
)
from django_elasticsearch_dsl_drf.filter_backends import (
    FilteringFilterBackend,
    IdsFilterBackend,
    OrderingFilterBackend,
    DefaultOrderingFilterBackend,
    SearchFilterBackend, CompoundSearchFilterBackend, MultiMatchSearchFilterBackend, FacetedSearchFilterBackend,
)
from django_elasticsearch_dsl_drf.viewsets import BaseDocumentViewSet, DocumentViewSet
from django_elasticsearch_dsl_drf.pagination import PageNumberPagination

from api.views.search_dataset import DatasetDocumentSerializer
from search.documents import DatasetDocument


class DatasetDocumentView(BaseDocumentViewSet):
    """The BookDocument view."""

    document = DatasetDocument
    serializer_class = DatasetDocumentSerializer
    pagination_class = PageNumberPagination
    lookup_field = 'id'
    filter_backends = [
        FilteringFilterBackend,
        IdsFilterBackend,
        OrderingFilterBackend,
        DefaultOrderingFilterBackend,
        SearchFilterBackend,
        FacetedSearchFilterBackend
    ]
    # Define search fields
    search_fields = (
        'metadata.value',
        'title',
        'description',
        'tags'
        # 'summary',
    )
    # Define filter fields
    filter_fields = {
        'id': {
            'field': 'id',
            # Note, that we limit the lookups of id field in this example,
            # to  `in` filters.
            'lookups': [
                LOOKUP_QUERY_IN,
            ],
        },
        'title': 'title.raw',
        # 'publisher': 'publisher.raw',
        # 'publication_date': 'publication_date',
        # 'state': 'state.raw',
        # 'isbn': 'isbn.raw',
        # 'price': {
        #     'field': 'price.raw',
        #     # Note, that we limit the lookups of `price` field in this
        #     # example, to `range`, `gt`, `gte`, `lt` and `lte` filters.
        #     'lookups': [
        #         LOOKUP_FILTER_RANGE,
        #         LOOKUP_QUERY_GT,
        #         LOOKUP_QUERY_GTE,
        #         LOOKUP_QUERY_LT,
        #         LOOKUP_QUERY_LTE,
        #     ],
        # },
        # 'pages': {
        #     'field': 'pages',
        #     # Note, that we limit the lookups of `pages` field in this
        #     # example, to `range`, `gt`, `gte`, `lt` and `lte` filters.
        #     'lookups': [
        #         LOOKUP_FILTER_RANGE,
        #         LOOKUP_QUERY_GT,
        #         LOOKUP_QUERY_GTE,
        #         LOOKUP_QUERY_LT,
        #         LOOKUP_QUERY_LTE,
        #     ],
        # },
        # 'stock_count': {
        #     'field': 'stock_count',
        #     # Note, that we limit the lookups of `stock_count` field in
        #     # this example, to `range`, `gt`, `gte`, `lt` and `lte`
        #     # filters.
        #     'lookups': [
        #         LOOKUP_FILTER_RANGE,
        #         LOOKUP_QUERY_GT,
        #         LOOKUP_QUERY_GTE,
        #         LOOKUP_QUERY_LT,
        #         LOOKUP_QUERY_LTE,
        #     ],
        # },
        'metadata': {
            'field': 'metadata.value',
            # Note, that we limit the lookups of `metadata` field
            # to `terms, `prefix`, `wildcard`, `in` and `exclude` filters.
            'lookups': [
                LOOKUP_FILTER_TERMS,
                LOOKUP_FILTER_PREFIX,
                LOOKUP_FILTER_WILDCARD,
            ]
        },
        'tags': {
            'field': 'tags',
            # Note, that we limit the lookups of `tags` field in
            # this example, to `terms, `prefix`, `wildcard`, `in` and
            # `exclude` filters.
            'lookups': [
                LOOKUP_FILTER_TERMS,
                LOOKUP_FILTER_PREFIX,
                LOOKUP_FILTER_WILDCARD,
                LOOKUP_QUERY_IN,
                LOOKUP_QUERY_EXCLUDE,
            ],
        },
        'tags.raw': {
            'field': 'tags.raw',
            # Note, that we limit the lookups of `tags.raw` field in
            # this example, to `terms, `prefix`, `wildcard`, `in` and
            # `exclude` filters.
            'lookups': [
                LOOKUP_FILTER_TERMS,
                LOOKUP_FILTER_PREFIX,
                LOOKUP_FILTER_WILDCARD,
                LOOKUP_QUERY_IN,
                LOOKUP_QUERY_EXCLUDE,
            ],
        },
    }
    # Define ordering fields
    ordering_fields = {
        'id': 'id',
        'title': 'title.raw',
        # 'price': 'price.raw',
        # 'state': 'state.raw',
        # 'publication_date': 'publication_date',
    }
    # Specify default ordering
    # TODO: add title and created date to ordering
    ordering = ('_score', 'id',)


class DatasetCompoundSearchBackendDocumentViewSet(DocumentViewSet):
    document = DatasetDocument
    serializer_class = DatasetDocumentSerializer
    lookup_field = 'id'
    multi_match_options = {
        'type': 'best_fields'
    }
    filter_backends = [
        FilteringFilterBackend,
        OrderingFilterBackend,
        DefaultOrderingFilterBackend,
        CompoundSearchFilterBackend,
        # MultiMatchSearchFilterBackend,
    ]

    filter_fields = {
        'id': {
            'field': 'id',
            # Note, that we limit the lookups of id field in this example,
            # to  `in` filters.
            'lookups': [
                LOOKUP_QUERY_IN,
            ],
        },
        'title': {
            'field': 'title',
            'lookups': [
                LOOKUP_FILTER_TERMS,
                LOOKUP_FILTER_PREFIX,
                LOOKUP_FILTER_WILDCARD,
                LOOKUP_QUERY_IN,
                LOOKUP_QUERY_EXCLUDE,
            ],
        },
        'title.raw': {
            'field': 'title.raw',
            'lookups': [
                LOOKUP_FILTER_TERMS,
                LOOKUP_FILTER_PREFIX,
                LOOKUP_FILTER_WILDCARD,
                LOOKUP_QUERY_IN,
                LOOKUP_QUERY_EXCLUDE,
            ],
        },
        # 'title': 'title.raw',
        # 'publisher': 'publisher.raw',
        # 'publication_date': 'publication_date',
        # 'state': 'state.raw',
        # 'isbn': 'isbn.raw',
        # 'price': {
        #     'field': 'price.raw',
        #     # Note, that we limit the lookups of `price` field in this
        #     # example, to `range`, `gt`, `gte`, `lt` and `lte` filters.
        #     'lookups': [
        #         LOOKUP_FILTER_RANGE,
        #         LOOKUP_QUERY_GT,
        #         LOOKUP_QUERY_GTE,
        #         LOOKUP_QUERY_LT,
        #         LOOKUP_QUERY_LTE,
        #     ],
        # },
        # 'pages': {
        #     'field': 'pages',
        #     # Note, that we limit the lookups of `pages` field in this
        #     # example, to `range`, `gt`, `gte`, `lt` and `lte` filters.
        #     'lookups': [
        #         LOOKUP_FILTER_RANGE,
        #         LOOKUP_QUERY_GT,
        #         LOOKUP_QUERY_GTE,
        #         LOOKUP_QUERY_LT,
        #         LOOKUP_QUERY_LTE,
        #     ],
        # },
        # 'stock_count': {
        #     'field': 'stock_count',
        #     # Note, that we limit the lookups of `stock_count` field in
        #     # this example, to `range`, `gt`, `gte`, `lt` and `lte`
        #     # filters.
        #     'lookups': [
        #         LOOKUP_FILTER_RANGE,
        #         LOOKUP_QUERY_GT,
        #         LOOKUP_QUERY_GTE,
        #         LOOKUP_QUERY_LT,
        #         LOOKUP_QUERY_LTE,
        #     ],
        # },
        'metadata': {
            'field': 'metadata.value',
            # Note, that we limit the lookups of `metadata` field
            # to `terms, `prefix`, `wildcard`, `in` and `exclude` filters.
            'lookups': [
                LOOKUP_FILTER_TERMS,
                LOOKUP_FILTER_PREFIX,
                LOOKUP_FILTER_WILDCARD,
            ]
        },
        'tags': {
            'field': 'tags',
            # Note, that we limit the lookups of `tags` field in
            # this example, to `terms, `prefix`, `wildcard`, `in` and
            # `exclude` filters.
            'lookups': [
                LOOKUP_FILTER_TERMS,
                LOOKUP_FILTER_PREFIX,
                LOOKUP_FILTER_WILDCARD,
                LOOKUP_QUERY_IN,
                LOOKUP_QUERY_EXCLUDE,
            ],
        },
        'tags.raw': {
            'field': 'tags.raw',
            # Note, that we limit the lookups of `tags.raw` field in
            # this example, to `terms, `prefix`, `wildcard`, `in` and
            # `exclude` filters.
            'lookups': [
                LOOKUP_FILTER_TERMS,
                LOOKUP_FILTER_PREFIX,
                LOOKUP_FILTER_WILDCARD,
                LOOKUP_QUERY_IN,
                LOOKUP_QUERY_EXCLUDE,
            ],
        },
    }

    search_fields = {
        'title': {'fuzziness': 'AUTO'},
        'description': {'fuzziness': 'AUTO'},
        'tags': None,
        'metadata.value': None
    }

    # multi_match_search_fields = {
    #     'metadata.value': {'fuzziness': 'AUTO', 'boost': 2},
    #     'title': {'fuzziness': 'AUTO', 'boost': 4},
    #     'description': None,
    #     'tags': None
    # }

    ordering_fields = {
        'id': 'id',
        'title': 'title.raw',
        # 'price': 'price.raw',
        # 'state': 'state.raw',
        # 'publication_date': 'publication_date',
    }

    ordering = ('_score', 'id',)
