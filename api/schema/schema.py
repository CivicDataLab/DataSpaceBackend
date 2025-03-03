from typing import List

import strawberry
import strawberry_django
from strawberry.tools import merge_types
from strawberry.types import Info
from strawberry_django.optimizer import DjangoOptimizerExtension

import api.schema.access_model_schema
import api.schema.category_schema
import api.schema.dataset_schema
import api.schema.dataspace_schema
import api.schema.metadata_schema
import api.schema.organization_schema
import api.schema.resource_chart_schema
import api.schema.resource_schema
import api.schema.resoure_chart_image_schema
import api.schema.usecase_schema
from api.models import DataSpace, Metadata, Organization, Resource, Tag
from api.types import TypeMetadata, TypeResource
from api.types.type_dataset import TypeTag
from api.types.type_dataspace import TypeDataSpace
from api.types.type_organization import TypeOrganization


@strawberry.type
class DefaultQuery:
    @strawberry_django.field
    def organisations(self, info: Info) -> List[TypeOrganization]:
        orgs = Organization.objects.all()
        return [TypeOrganization.from_django(org) for org in orgs]

    @strawberry_django.field
    def dataspaces(self, info: Info) -> List[TypeDataSpace]:
        spaces = DataSpace.objects.all()
        return [TypeDataSpace.from_django(space) for space in spaces]

    @strawberry_django.field
    def metadata(self, info: Info) -> List[TypeMetadata]:
        metadata_list = Metadata.objects.all()
        return [TypeMetadata.from_django(meta) for meta in metadata_list]

    @strawberry_django.field
    def resources(self, info: Info) -> List[TypeResource]:
        resources = Resource.objects.all()
        return [TypeResource.from_django(resource) for resource in resources]

    @strawberry_django.field
    def tags(self, info: Info) -> List[TypeTag]:
        tags = Tag.objects.all()
        return [TypeTag.from_django(tag) for tag in tags]


Query = merge_types(
    "Query",
    (
        DefaultQuery,
        api.schema.dataset_schema.Query,
        api.schema.resource_schema.Query,
        api.schema.access_model_schema.Query,
        api.schema.category_schema.Query,
        api.schema.resource_chart_schema.Query,
        api.schema.usecase_schema.Query,
        api.schema.resoure_chart_image_schema.Query,
    ),
)

Mutation = merge_types(
    "Mutation",
    (
        api.schema.dataset_schema.Mutation,
        api.schema.metadata_schema.Mutation,
        api.schema.resource_schema.Mutation,
        api.schema.access_model_schema.Mutation,
        api.schema.category_schema.Mutation,
        api.schema.organization_schema.Mutation,
        api.schema.dataspace_schema.Mutation,
        api.schema.resource_chart_schema.Mutation,
        api.schema.usecase_schema.Mutation,
        api.schema.resoure_chart_image_schema.Mutation,
    ),
)

schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    extensions=[
        DjangoOptimizerExtension,
        # MaskErrors,
        # OpenTelemetryExtension
    ],
)
