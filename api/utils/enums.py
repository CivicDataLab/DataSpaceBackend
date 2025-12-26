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


class AIModelType(models.TextChoices):
    TRANSLATION = "TRANSLATION"
    TEXT_GENERATION = "TEXT_GENERATION"
    SUMMARIZATION = "SUMMARIZATION"
    QUESTION_ANSWERING = "QUESTION_ANSWERING"
    SENTIMENT_ANALYSIS = "SENTIMENT_ANALYSIS"
    TEXT_CLASSIFICATION = "TEXT_CLASSIFICATION"
    NAMED_ENTITY_RECOGNITION = "NAMED_ENTITY_RECOGNITION"
    TEXT_TO_SPEECH = "TEXT_TO_SPEECH"
    SPEECH_TO_TEXT = "SPEECH_TO_TEXT"
    OTHER = "OTHER"


class AIModelStatus(models.TextChoices):
    DRAFT = "DRAFT"
    REGISTERED = "REGISTERED"
    VALIDATING = "VALIDATING"
    ACTIVE = "ACTIVE"
    AUDITING = "AUDITING"
    APPROVED = "APPROVED"
    FLAGGED = "FLAGGED"
    DEPRECATED = "DEPRECATED"


class AIModelProvider(models.TextChoices):
    OPENAI = "OPENAI"
    LLAMA_OLLAMA = "LLAMA_OLLAMA"
    LLAMA_TOGETHER = "LLAMA_TOGETHER"
    LLAMA_REPLICATE = "LLAMA_REPLICATE"
    LLAMA_CUSTOM = "LLAMA_CUSTOM"
    CUSTOM = "CUSTOM"
    HUGGINGFACE = "HUGGINGFACE"


class AIModelLifecycleStage(models.TextChoices):
    DEVELOPMENT = "DEVELOPMENT", "Development"
    TESTING = "TESTING", "Testing"
    BETA = "BETA", "Beta Testing"
    STAGING = "STAGING", "Staging"
    PRODUCTION = "PRODUCTION", "Production"
    DEPRECATED = "DEPRECATED", "Deprecated"
    RETIRED = "RETIRED", "Retired"


class AIModelFramework(models.TextChoices):
    PYTORCH = "pt", "PyTorch"
    TENSORFLOW = "tf", "TensorFlow"


class HFModelClass(models.TextChoices):
    CAUSAL_LM = "AutoModelForCausalLM", "Causal Language Modeling Head"
    SEQ2SEQ_LM = "AutoModelForSeq2SeqLM", "Sequence-To-Sequence Language Modeling Head"
    SEQUENCE_CLASSIFICATION = "AutoModelForSequenceClassification", "Sequence Classification Head"
    NEXT_SENTENCE_PREDICTION = "AutoModelForNextSentencePrediction", "Next Sentence Prediction Head"
    MULTIPLE_CHOICE = "AutoModelForMultipleChoice", "Multiple Choice Head"
    TOKEN_CLASSIFICATION = "AutoModelForTokenClassification", "Token Classification Head"
    QUESTION_ANSWERING = "AutoModelForQuestionAnswering", "Question Answering Head"
    MASKED_LM = "AutoModelForMaskedLM", "Masked Language Modeling Head"


class EndpointHTTPMethod(models.TextChoices):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"


class EndpointAuthType(models.TextChoices):
    BEARER = "BEARER"
    API_KEY = "API_KEY"
    BASIC = "BASIC"
    OAUTH2 = "OAUTH2"
    CUSTOM = "CUSTOM"
    NONE = "NONE"
