# from typing import Any, Dict, List, Optional, Type, TypeVar, cast

# # type: ignore[import-untyped]
# from django_elasticsearch_dsl_drf.constants import (
#     LOOKUP_FILTER_TERMS,
#     LOOKUP_FILTER_RANGE,
#     LOOKUP_FILTER_PREFIX,
#     LOOKUP_FILTER_WILDCARD,
#     LOOKUP_QUERY_IN,
#     LOOKUP_QUERY_GT,
#     LOOKUP_QUERY_GTE,
#     LOOKUP_QUERY_LT,
#     LOOKUP_QUERY_LTE,
#     LOOKUP_QUERY_EXCLUDE,
# )
# # type: ignore[import-untyped]
# from django_elasticsearch_dsl_drf.filter_backends import (
#     FilteringFilterBackend,
#     IdsFilterBackend,
#     OrderingFilterBackend,
#     DefaultOrderingFilterBackend,
#     SearchFilterBackend,
#     CompoundSearchFilterBackend,
#     MultiMatchSearchFilterBackend,
#     FacetedSearchFilterBackend,
# )
# # type: ignore[import-untyped]
# from django_elasticsearch_dsl_drf.viewsets import BaseDocumentViewSet, DocumentViewSet
# # type: ignore[import-untyped]
# from django_elasticsearch_dsl_drf.pagination import PageNumberPagination

# from api.views.search_dataset import DatasetDocumentSerializer
# from search.documents import DatasetDocument


# class DatasetDocumentView(BaseDocumentViewSet):
#     """
#     The Dataset Document view.

#     This view provides a way to interact with the DatasetDocument.
#     """

#     document: Type[DatasetDocument] = DatasetDocument
#     serializer_class: Type[DatasetDocumentSerializer] = DatasetDocumentSerializer
#     pagination_class: Type[PageNumberPagination] = PageNumberPagination
#     lookup_field: str = 'id'
#     filter_backends: List[Any] = [
#         FilteringFilterBackend,
#         IdsFilterBackend,
#         OrderingFilterBackend,
#         DefaultOrderingFilterBackend,
#         SearchFilterBackend,
#         FacetedSearchFilterBackend
#     ]

#     # Define search fields
#     search_fields: tuple = (
#         'metadata.value',
#         'title',
#         'description',
#         'tags'
#     )

#     # Define filter fields
#     filter_fields: Dict[str, Dict[str, Any]] = {
#         'id': {
#             'field': 'id',
#             'lookups': [
#                 LOOKUP_QUERY_IN,
#             ],
#         },
#         'title': {
#             'field': 'title',
#             'lookups': [
#                 LOOKUP_FILTER_TERMS,
#                 LOOKUP_FILTER_PREFIX,
#                 LOOKUP_FILTER_WILDCARD,
#                 LOOKUP_QUERY_IN,
#                 LOOKUP_QUERY_EXCLUDE,
#             ],
#         },
#         'title.raw': {
#             'field': 'title.raw',
#             'lookups': [
#                 LOOKUP_FILTER_TERMS,
#                 LOOKUP_FILTER_PREFIX,
#                 LOOKUP_FILTER_WILDCARD,
#                 LOOKUP_QUERY_IN,
#                 LOOKUP_QUERY_EXCLUDE,
#             ],
#         },
#         'metadata': {
#             'field': 'metadata.value',
#             'lookups': [
#                 LOOKUP_FILTER_TERMS,
#                 LOOKUP_FILTER_PREFIX,
#                 LOOKUP_FILTER_WILDCARD,
#             ]
#         },
#         'tags': {
#             'field': 'tags',
#             'lookups': [
#                 LOOKUP_FILTER_TERMS,
#                 LOOKUP_FILTER_PREFIX,
#                 LOOKUP_FILTER_WILDCARD,
#                 LOOKUP_QUERY_IN,
#                 LOOKUP_QUERY_EXCLUDE,
#             ],
#         },
#         'tags.raw': {
#             'field': 'tags.raw',
#             'lookups': [
#                 LOOKUP_FILTER_TERMS,
#                 LOOKUP_FILTER_PREFIX,
#                 LOOKUP_FILTER_WILDCARD,
#                 LOOKUP_QUERY_IN,
#                 LOOKUP_QUERY_EXCLUDE,
#             ],
#         },
#     }

#     ordering_fields: Dict[str, str] = {
#         'id': 'id',
#         'title': 'title.raw',
#     }

#     ordering: tuple = ('_score', 'id',)


# class DatasetCompoundSearchBackendDocumentViewSet(BaseDocumentViewSet):
#     """
#     The Dataset Document view with compound search.

#     This view provides a way to interact with the DatasetDocument using compound search.
#     """

#     document: Type[DatasetDocument] = DatasetDocument
#     serializer_class: Type[DatasetDocumentSerializer] = DatasetDocumentSerializer
#     lookup_field: str = 'id'
#     multi_match_options: Dict[str, str] = {
#         'type': 'best_fields'
#     }
#     filter_backends: List[Any] = [
#         FilteringFilterBackend,
#         OrderingFilterBackend,
#         DefaultOrderingFilterBackend,
#         CompoundSearchFilterBackend,
#     ]

#     filter_fields: Dict[str, Dict[str, Any]] = {
#         'id': {
#             'field': 'id',
#             'lookups': [
#                 LOOKUP_QUERY_IN,
#             ],
#         },
#         'title': {
#             'field': 'title',
#             'lookups': [
#                 LOOKUP_FILTER_TERMS,
#                 LOOKUP_FILTER_PREFIX,
#                 LOOKUP_FILTER_WILDCARD,
#                 LOOKUP_QUERY_IN,
#                 LOOKUP_QUERY_EXCLUDE,
#             ],
#         },
#         'title.raw': {
#             'field': 'title.raw',
#             'lookups': [
#                 LOOKUP_FILTER_TERMS,
#                 LOOKUP_FILTER_PREFIX,
#                 LOOKUP_FILTER_WILDCARD,
#                 LOOKUP_QUERY_IN,
#                 LOOKUP_QUERY_EXCLUDE,
#             ],
#         },
#         'metadata': {
#             'field': 'metadata.value',
#             'lookups': [
#                 LOOKUP_FILTER_TERMS,
#                 LOOKUP_FILTER_PREFIX,
#                 LOOKUP_FILTER_WILDCARD,
#             ]
#         },
#         'tags': {
#             'field': 'tags',
#             'lookups': [
#                 LOOKUP_FILTER_TERMS,
#                 LOOKUP_FILTER_PREFIX,
#                 LOOKUP_FILTER_WILDCARD,
#                 LOOKUP_QUERY_IN,
#                 LOOKUP_QUERY_EXCLUDE,
#             ],
#         },
#         'tags.raw': {
#             'field': 'tags.raw',
#             'lookups': [
#                 LOOKUP_FILTER_TERMS,
#                 LOOKUP_FILTER_PREFIX,
#                 LOOKUP_FILTER_WILDCARD,
#                 LOOKUP_QUERY_IN,
#                 LOOKUP_QUERY_EXCLUDE,
#             ],
#         },
#     }

#     search_fields: Dict[str, Optional[Dict[str, str]]] = {
#         'title': {'fuzziness': 'AUTO'},
#         'description': {'fuzziness': 'AUTO'},
#         'tags': None,
#         'metadata.value': None
#     }

#     ordering_fields: Dict[str, str] = {
#         'id': 'id',
#         'title': 'title.raw',
#     }

#     ordering: tuple = ('_score', 'id',)
