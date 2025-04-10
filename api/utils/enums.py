from typing import List, Tuple

from django.db import models


class OrganizationTypes(models.TextChoices):
    STATE_GOVERNMENT = "STATE GOVERNMENT"
    UNION_TERRITORY_GOVERNMENT = "UNION TERRITORY GOVERNMENT"
    URBAN_LOCAL_BODY = "URBAN LOCAL BODY"
    ACADEMIC_INSTITUTION = "ACADEMIC INSTITUTION"
    CENTRAL_GOVERNMENT = "CENTRAL GOVERNMENT"
    CITIZENS_GROUP = "CITIZENS GROUP"
    CIVIL_SOCIETY_ORGANISATION = "CIVIL SOCIETY ORGANISATION"
    INDUSTRY_BODY = "INDUSTRY BODY"
    MEDIA_ORGANISATION = "MEDIA ORGANISATION"
    OPEN_DATA_TECHNOLOGY_COMMUNITY = "OPEN DATA/TECHNOLOGY COMMUNITY"
    PRIVATE_COMPANY = "PRIVATE COMPANY"
    PUBLIC_SECTOR_COMPANY = "PUBLIC SECTOR COMPANY"
    OTHERS = "OTHERS"
    STARTUP = "STARTUP"
    GOVERNMENT = "GOVERNMENT"
    CORPORATIONS = "CORPORATIONS"
    NGO = "NGO"


class GeoTypes(models.TextChoices):
    DISTRICT = "DISTRICT"
    STATE = "STATE"
    COUNTRY = "COUNTRY"
    UT = "UT"


class DataType(models.TextChoices):
    API = "API"
    FILE = "FILE"
    EXTERNAL = "EXTERNAL"


class MetadataModels(models.TextChoices):
    DATASET = "DATASET"
    RESEOURCE = "RESOURCE"
    USECASE = "USECASE"


class MetadataStandards(models.TextChoices):
    DCATV3 = "DCATV3"
    OCDS = "OCDS"
    OBDS = "OBDS"
    NA = "NA"


class MetadataDataTypes(models.TextChoices):
    STRING = "STRING"
    NUMBER = "NUMBER"
    SELECT = "SELECT"
    MULTISELECT = "MULTISELECT"
    DATE = "DATE"
    URL = "URL"


class MetadataTypes(models.TextChoices):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"
    ADVANCED = "ADVANCED"


class AccessTypes(models.TextChoices):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    PROTECTED = "PROTECTED"


class FieldTypes(models.TextChoices):
    STRING = "STRING"
    NUMBER = "NUMBER"
    INTEGER = "INTEGER"
    DATE = "DATE"
    BOOLEAN = "BOOLEAN"


class DatasetStatus(models.TextChoices):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class UseCaseStatus(models.TextChoices):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class UseCaseRunningStatus(models.TextChoices):
    INITIATED = "INITIATED"
    ON_GOING = "ON_GOING"
    COMPLETED = "COMPLETED"
    ON_HOLD = "ON_HOLD"
    CANCELLED = "CANCELLED"


class ChartTypes(models.TextChoices):
    BAR_VERTICAL = "BAR_VERTICAL"
    BAR_HORIZONTAL = "BAR_HORIZONTAL"
    GROUPED_BAR_VERTICAL = "GROUPED_BAR_VERTICAL"
    GROUPED_BAR_HORIZONTAL = "GROUPED_BAR_HORIZONTAL"
    LINE = "LINE"
    MULTILINE = "MULTILINE"
    ASSAM_DISTRICT = "ASSAM_DISTRICT"
    ASSAM_RC = "ASSAM_RC"
    TREEMAP = "TREEMAP"


class AggregateType(models.TextChoices):
    NONE = "NONE"
    SUM = "SUM"
    AVERAGE = "AVG"
    COUNT = "COUNT"
