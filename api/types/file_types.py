"""GraphQL types for file and image fields, without `path` (#284).

strawberry-django gives every FileField/ImageField its own `DjangoFileType` /
`DjangoImageType`, whose `path` reads `FieldFile.path`: the file's location on
the server's disk. Media lives on S3, which has none, so asking for `path`
always failed with "This backend doesn't support absolute paths." A disk
location is of no use to API clients anyway (`name` is the storage key, `url`
opens the file), so these types keep the same names and every other field, and
leave `path` out.
"""

import strawberry
from django.db import models
from strawberry_django.fields import types as field_types


@strawberry.type(name="DjangoFileType")
class StorageFileType:
    name: str
    size: int
    url: str


@strawberry.type(name="DjangoImageType")
class StorageImageType(StorageFileType):
    width: int
    height: int


def use_storage_file_types() -> None:
    """Make every file/image field defined after this call use the types above.

    Called from `ApiConfig.ready()`, before any GraphQL type module is imported.
    """
    field_types.field_type_map[models.FileField] = StorageFileType
    field_types.field_type_map[models.ImageField] = StorageImageType
