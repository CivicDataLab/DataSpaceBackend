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


class DatasetType(models.TextChoices):
    DATA = "DATA"
    PROMPT = "PROMPT"


class PromptTaskType(models.TextChoices):
    TEXT_GENERATION = "TEXT_GENERATION"
    TEXT_CLASSIFICATION = "TEXT_CLASSIFICATION"
    QUESTION_ANSWERING = "QUESTION_ANSWERING"
    SUMMARIZATION = "SUMMARIZATION"
    TRANSLATION = "TRANSLATION"
    SENTIMENT_ANALYSIS = "SENTIMENT_ANALYSIS"
    NAMED_ENTITY_RECOGNITION = "NAMED_ENTITY_RECOGNITION"
    CODE_GENERATION = "CODE_GENERATION"
    CONVERSATION = "CONVERSATION"
    INSTRUCTION_FOLLOWING = "INSTRUCTION_FOLLOWING"
    REASONING = "REASONING"
    CREATIVE_WRITING = "CREATIVE_WRITING"
    DATA_EXTRACTION = "DATA_EXTRACTION"
    OTHER = "OTHER"


class PromptPurpose(models.TextChoices):
    RESEARCH = "RESEARCH"
    EDUCATION = "EDUCATION"
    EVALUATION = "EVALUATION"
    OTHER = "OTHER"


class PromptDomain(models.TextChoices):
    HEALTHCARE = "HEALTHCARE"
    EDUCATION = "EDUCATION"
    LEGAL = "LEGAL"
    FINANCE = "FINANCE"
    AGRICULTURE = "AGRICULTURE"
    ENVIRONMENT = "ENVIRONMENT"
    GOVERNMENT = "GOVERNMENT"
    TECHNOLOGY = "TECHNOLOGY"
    SCIENCE = "SCIENCE"
    SOCIAL_SERVICES = "SOCIAL_SERVICES"
    TRANSPORTATION = "TRANSPORTATION"
    ENERGY = "ENERGY"
    GENERAL = "GENERAL"
    OTHER = "OTHER"


class PromptFormat(models.TextChoices):
    INSTRUCTION = "INSTRUCTION"
    CHAT = "CHAT"
    COMPLETION = "COMPLETION"
    FEW_SHOT = "FEW_SHOT"
    CHAIN_OF_THOUGHT = "CHAIN_OF_THOUGHT"
    ZERO_SHOT = "ZERO_SHOT"
    OTHER = "OTHER"


class TargetLanguage(models.TextChoices):
    ENGLISH = "ENGLISH"
    HINDI = "HINDI"
    TAMIL = "TAMIL"
    TELUGU = "TELUGU"
    BENGALI = "BENGALI"
    MARATHI = "MARATHI"
    GUJARATI = "GUJARATI"
    KANNADA = "KANNADA"
    MALAYALAM = "MALAYALAM"
    PUNJABI = "PUNJABI"
    ODIA = "ODIA"
    ASSAMESE = "ASSAMESE"
    URDU = "URDU"
    OTHER = "OTHER"


class TargetModelType(models.TextChoices):
    GPT = "GPT"
    LLAMA = "LLAMA"
    MISTRAL = "MISTRAL"
    GEMINI = "GEMINI"
    CLAUDE = "CLAUDE"
    FALCON = "FALCON"
    BLOOM = "BLOOM"
    INDIC_LLM = "INDIC_LLM"
    CUSTOM = "CUSTOM"
    OTHER = "OTHER"


class DatasetAccessType(models.TextChoices):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    RESTRICTED = "RESTRICTED"


class DatasetLicense(models.TextChoices):
    """One value per row of contracts/licenses.csv (matched by its dataspace_enum alt code)."""

    GOVERNMENT_OPEN_DATA_LICENSE = (
        "GOVERNMENT_OPEN_DATA_LICENSE",
        "Government Open Data License – India",
    )
    CC_BY_4_0_ATTRIBUTION = "CC_BY_4_0_ATTRIBUTION", "Creative Commons Attribution 4.0"
    CC_BY_SA_4_0_ATTRIBUTION_SHARE_ALIKE = (
        "CC_BY_SA_4_0_ATTRIBUTION_SHARE_ALIKE",
        "Creative Commons Attribution-ShareAlike 4.0",
    )
    OPEN_DATA_COMMONS_BY_ATTRIBUTION = (
        "OPEN_DATA_COMMONS_BY_ATTRIBUTION",
        "Open Data Commons Attribution License 1.0",
    )
    OPEN_DATABASE_LICENSE = "OPEN_DATABASE_LICENSE", "Open Database License 1.0"
    CC_PDM_1_0 = "CC_PDM_1_0", "Creative Commons Public Domain Mark 1.0 Universal"
    CC_BY_1_0 = "CC_BY_1_0", "Creative Commons Attribution 1.0 Generic"
    CC_BY_2_0 = "CC_BY_2_0", "Creative Commons Attribution 2.0 Generic"
    CC_BY_2_5_AU = "CC_BY_2_5_AU", "Creative Commons Attribution 2.5 Australia"
    CC_BY_2_5 = "CC_BY_2_5", "Creative Commons Attribution 2.5 Generic"
    CC_BY_3_0_AU = "CC_BY_3_0_AU", "Creative Commons Attribution 3.0 Australia"
    CC_BY_3_0_AT = "CC_BY_3_0_AT", "Creative Commons Attribution 3.0 Austria"
    CC_BY_3_0_DE = "CC_BY_3_0_DE", "Creative Commons Attribution 3.0 Germany"
    CC_BY_3_0_IGO = "CC_BY_3_0_IGO", "Creative Commons Attribution 3.0 IGO"
    CC_BY_3_0_NL = "CC_BY_3_0_NL", "Creative Commons Attribution 3.0 Netherlands"
    CC_BY_3_0_US = "CC_BY_3_0_US", "Creative Commons Attribution 3.0 United States"
    CC_BY_3_0 = "CC_BY_3_0", "Creative Commons Attribution 3.0 Unported"
    CC_BY_ND_1_0 = "CC_BY_ND_1_0", "Creative Commons Attribution No Derivatives 1.0 Generic"
    CC_BY_ND_2_0 = "CC_BY_ND_2_0", "Creative Commons Attribution No Derivatives 2.0 Generic"
    CC_BY_ND_2_5 = "CC_BY_ND_2_5", "Creative Commons Attribution No Derivatives 2.5 Generic"
    CC_BY_ND_3_0_DE = "CC_BY_ND_3_0_DE", "Creative Commons Attribution No Derivatives 3.0 Germany"
    CC_BY_ND_3_0 = "CC_BY_ND_3_0", "Creative Commons Attribution No Derivatives 3.0 Unported"
    CC_BY_ND_4_0 = "CC_BY_ND_4_0", "Creative Commons Attribution No Derivatives 4.0 International"
    CC_BY_NC_1_0 = "CC_BY_NC_1_0", "Creative Commons Attribution Non Commercial 1.0 Generic"
    CC_BY_NC_2_0 = "CC_BY_NC_2_0", "Creative Commons Attribution Non Commercial 2.0 Generic"
    CC_BY_NC_2_5 = "CC_BY_NC_2_5", "Creative Commons Attribution Non Commercial 2.5 Generic"
    CC_BY_NC_3_0_DE = "CC_BY_NC_3_0_DE", "Creative Commons Attribution Non Commercial 3.0 Germany"
    CC_BY_NC_3_0_IGO = "CC_BY_NC_3_0_IGO", "Creative Commons Attribution Non Commercial 3.0 IGO"
    CC_BY_NC_3_0 = "CC_BY_NC_3_0", "Creative Commons Attribution Non Commercial 3.0 Unported"
    CC_BY_NC_4_0 = "CC_BY_NC_4_0", "Creative Commons Attribution Non Commercial 4.0 International"
    CC_BY_NC_ND_1_0 = (
        "CC_BY_NC_ND_1_0",
        "Creative Commons Attribution Non Commercial No Derivatives 1.0 Generic",
    )
    CC_BY_NC_ND_2_0 = (
        "CC_BY_NC_ND_2_0",
        "Creative Commons Attribution Non Commercial No Derivatives 2.0 Generic",
    )
    CC_BY_NC_ND_2_5 = (
        "CC_BY_NC_ND_2_5",
        "Creative Commons Attribution Non Commercial No Derivatives 2.5 Generic",
    )
    CC_BY_NC_ND_3_0_DE = (
        "CC_BY_NC_ND_3_0_DE",
        "Creative Commons Attribution Non Commercial No Derivatives 3.0 Germany",
    )
    CC_BY_NC_ND_3_0_IGO = (
        "CC_BY_NC_ND_3_0_IGO",
        "Creative Commons Attribution Non Commercial No Derivatives 3.0 IGO",
    )
    CC_BY_NC_ND_3_0 = (
        "CC_BY_NC_ND_3_0",
        "Creative Commons Attribution Non Commercial No Derivatives 3.0 Unported",
    )
    CC_BY_NC_ND_4_0 = (
        "CC_BY_NC_ND_4_0",
        "Creative Commons Attribution Non Commercial No Derivatives 4.0 International",
    )
    CC_BY_NC_SA_1_0 = (
        "CC_BY_NC_SA_1_0",
        "Creative Commons Attribution Non Commercial Share Alike 1.0 Generic",
    )
    CC_BY_NC_SA_2_0_UK = (
        "CC_BY_NC_SA_2_0_UK",
        "Creative Commons Attribution Non Commercial Share Alike 2.0 England and Wales",
    )
    CC_BY_NC_SA_2_0 = (
        "CC_BY_NC_SA_2_0",
        "Creative Commons Attribution Non Commercial Share Alike 2.0 Generic",
    )
    CC_BY_NC_SA_2_0_DE = (
        "CC_BY_NC_SA_2_0_DE",
        "Creative Commons Attribution Non Commercial Share Alike 2.0 Germany",
    )
    CC_BY_NC_SA_2_5 = (
        "CC_BY_NC_SA_2_5",
        "Creative Commons Attribution Non Commercial Share Alike 2.5 Generic",
    )
    CC_BY_NC_SA_3_0_DE = (
        "CC_BY_NC_SA_3_0_DE",
        "Creative Commons Attribution Non Commercial Share Alike 3.0 Germany",
    )
    CC_BY_NC_SA_3_0_IGO = (
        "CC_BY_NC_SA_3_0_IGO",
        "Creative Commons Attribution Non Commercial Share Alike 3.0 IGO",
    )
    CC_BY_NC_SA_3_0 = (
        "CC_BY_NC_SA_3_0",
        "Creative Commons Attribution Non Commercial Share Alike 3.0 Unported",
    )
    CC_BY_NC_SA_4_0 = (
        "CC_BY_NC_SA_4_0",
        "Creative Commons Attribution Non Commercial Share Alike 4.0 International",
    )
    CC_BY_SA_1_0 = "CC_BY_SA_1_0", "Creative Commons Attribution Share Alike 1.0 Generic"
    CC_BY_SA_2_0_UK = (
        "CC_BY_SA_2_0_UK",
        "Creative Commons Attribution Share Alike 2.0 England and Wales",
    )
    CC_BY_SA_2_0 = "CC_BY_SA_2_0", "Creative Commons Attribution Share Alike 2.0 Generic"
    CC_BY_SA_2_1_JP = "CC_BY_SA_2_1_JP", "Creative Commons Attribution Share Alike 2.1 Japan"
    CC_BY_SA_2_5 = "CC_BY_SA_2_5", "Creative Commons Attribution Share Alike 2.5 Generic"
    CC_BY_SA_3_0_AT = "CC_BY_SA_3_0_AT", "Creative Commons Attribution Share Alike 3.0 Austria"
    CC_BY_SA_3_0_DE = "CC_BY_SA_3_0_DE", "Creative Commons Attribution Share Alike 3.0 Germany"
    CC_BY_SA_3_0 = "CC_BY_SA_3_0", "Creative Commons Attribution Share Alike 3.0 Unported"
    CC_BY_NC_SA_2_0_FR = (
        "CC_BY_NC_SA_2_0_FR",
        "Creative Commons Attribution-NonCommercial-ShareAlike 2.0 France",
    )
    CC_BY_SA_3_0_IGO = "CC_BY_SA_3_0_IGO", "Creative Commons Attribution-ShareAlike 3.0 IGO"
    CC_PDDC = "CC_PDDC", "Creative Commons Public Domain Dedication and Certification"
    CC_SA_1_0 = "CC_SA_1_0", "Creative Commons Share Alike 1.0 Generic"
    CC0_1_0 = "CC0_1_0", "Creative Commons Zero v1.0 Universal"
    PDDL_1_0 = "PDDL_1_0", "Open Data Commons Public Domain Dedication & License 1.0"


class UseCaseStatus(models.TextChoices):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class PublicationStatus(models.TextChoices):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"


class EventStatus(models.TextChoices):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"


class PublicationBlockType(models.TextChoices):
    FILE = "FILE"
    YOUTUBE = "YOUTUBE"


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


class ImportPlatform(models.TextChoices):
    """Third-party platforms a dataset can be imported (link-only) from."""

    KAGGLE = "KAGGLE"
    HUGGINGFACE = "HUGGINGFACE"
    GITHUB = "GITHUB"
