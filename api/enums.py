from django.db import models


class RatingStatus(models.TextChoices):
    CREATED = "CREATED"
    REJECTED = "REJECTED"
    PUBLISHED = "PUBLISHED"


class SubscriptionUnits(models.TextChoices):
    LIMITEDDOWNLOAD = "LIMITEDDOWNLOAD"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    QUARTERLY = "QUARTERLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"


class ReviewType(models.TextChoices):
    REVIEW = "REVIEW"
    MODERATION = "MODERATION"


class AuthLocation(models.TextChoices):
    HEADER = "HEADER"
    PARAM = "PARAM"


class AuthType(models.TextChoices):
    CREDENTIALS = "CREDENTIALS"
    TOKEN = "TOKEN"
    NO_AUTH = "NO_AUTH"


class OrganizationRequestStatusType(models.TextChoices):
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DELETED = "DELETED"
    DISABLED = "DISABLED"


class OrganizationCreationStatusType(models.TextChoices):
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


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


class OrganizationSubTypes(models.TextChoices):
    MINISTRY = "MINISTRY"
    DEPARTMENT = "DEPARTMENT"
    ORGANISATION = "ORGANISATION"
    OTHER = "OTHER"


class GeoTypes(models.TextChoices):
    DISTRICT = "DISTRICT"
    STATE = "STATE"
    COUNTRY = "COUNTRY"
    UT = "UT"


class DataType(models.TextChoices):
    API = "API"
    FILE = "FILE"
    EXTERNAL = "EXTERNAL"


class ValidationUnits(models.TextChoices):
    LIFETIME = "LIFETIME"
    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"
    YEAR = "YEAR"


class DataAccessModelStatus(models.TextChoices):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class SubscriptionAction(models.TextChoices):
    SUBSCRIBE = "SUBSCRIBE"
    UNSUBSCRIBE = "UNSUBSCRIBE"


class ParameterTypes(models.TextChoices):
    EXPOSED = "EXPOSED"
    PAGINATION = "PAGINATION"
    PREVIEW = "PREVIEW"
    DOWNLOAD = "DOWNLOAD"


class FormatLocation(models.TextChoices):
    HEADER = "HEADER"
    PARAM = "PARAM"


class MetadataModels(models.TextChoices):
    DATASET = "DATASET"
    RESEOURCE = "RESOURCE"


class MetadataStandards(models.TextChoices):
    DCATV3 = "DCATV3"
    OCDS = "OCDS"
    OBDS = "OBDS"


class MetadataDataTypes(models.TextChoices):
    STRING = "STRING"
    NUMBER = "NUMBER"
    SELECT = "SELECT"
    MULTISELECT = "MULTISELECT"
    DATE = "DATE"


class MetadataTypes(models.TextChoices):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"
    ADVANCED = "ADVANCED"
