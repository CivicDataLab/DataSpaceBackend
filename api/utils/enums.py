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
    REGION = "REGION"
    COUNTRY = "COUNTRY"
    STATE = "STATE"
    DISTRICT = "DISTRICT"
    UT = "UT"


class DataType(models.TextChoices):
    API = "API"
    FILE = "FILE"
    EXTERNAL = "EXTERNAL"


class MetadataModels(models.TextChoices):
    DATASET = "DATASET"
    RESEOURCE = "RESOURCE"
    USECASE = "USECASE"
    COLLABORATIVE = "COLLABORATIVE"


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


class DatasetAccessType(models.TextChoices):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    RESTRICTED = "RESTRICTED"


class DatasetLicense(models.TextChoices):
    GOVERNMENT_OPEN_DATA_LICENSE = "GOVERNMENT_OPEN_DATA_LICENSE"
    CC_BY_4_0_ATTRIBUTION = "CC_BY_4_0_ATTRIBUTION"
    CC_BY_SA_4_0_ATTRIBUTION_SHARE_ALIKE = "CC_BY_SA_4_0_ATTRIBUTION_SHARE_ALIKE"
    OPEN_DATA_COMMONS_BY_ATTRIBUTION = "OPEN_DATA_COMMONS_BY_ATTRIBUTION"
    OPEN_DATABASE_LICENSE = "OPEN_DATABASE_LICENSE"


class UseCaseStatus(models.TextChoices):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class CollaborativeStatus(models.TextChoices):
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
    # New simplified chart types
    BAR = "BAR"
    LINE = "LINE"
    BIG_NUMBER = "BIG_NUMBER"

    # Map and other specialized charts
    ASSAM_DISTRICT = "ASSAM_DISTRICT"
    ASSAM_RC = "ASSAM_RC"
    TREEMAP = "TREEMAP"

    # Enhanced map chart types
    POLYGON_MAP = "POLYGON_MAP"
    POINT_MAP = "POINT_MAP"
    GEOSPATIAL_MAP = "GEOSPATIAL_MAP"


class ChartStatus(models.TextChoices):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class AggregateType(models.TextChoices):
    NONE = "NONE"
    SUM = "SUM"
    AVERAGE = "AVG"
    COUNT = "COUNT"


class OrganizationRelationshipType(models.TextChoices):
    SUPPORTER = "SUPPORTER"
    PARTNER = "PARTNER"
