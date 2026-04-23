# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2025-11-12

### Added

- **AI Model Execution Support**
  - `call_model(model_id, input_text, parameters)` - Synchronous model execution via SDK
  - `call_model_async(model_id, input_text, parameters)` - Asynchronous execution (placeholder)
  - Support for multiple providers: OpenAI, Llama (Ollama, Together AI, Replicate), HuggingFace, Custom APIs
  - New API endpoints: `POST /api/aimodels/{id}/call/` and `POST /api/aimodels/{id}/call-async/`

- **HuggingFace Integration**
  - `hf_use_pipeline` field - Use Pipeline inference API
  - `hf_auth_token` field - Authentication token for gated models
  - `hf_model_class` field - Model head specification (8 variants)
  - `hf_attn_implementation` field - Attention function configuration
  - `framework` field - PyTorch or TensorFlow selection
  - Support for 8 model classes: CausalLM, Seq2SeqLM, SequenceClassification, etc.

- **CRUD Operations for AIModels**
  - `create(data)` - Create new AI models
  - `update(model_id, data)` - Update existing models
  - `delete_model(model_id)` - Delete models
  - PATCH HTTP method support in base client

- **Backend Services**
  - `ModelAPIClient` - Multi-provider API client with retry logic and statistics tracking
  - `ModelHFClient` - HuggingFace inference client with pipeline and manual loading support
  - Automatic GPU/CPU device selection
  - Request template system with placeholder replacement

- **New Enums**
  - `AIModelProvider.HUGGINGFACE` - HuggingFace provider
  - `AIModelFramework` - PyTorch/TensorFlow framework selection
  - `HFModelClass` - 8 model head types

- **Security & Access Control**
  - Organization-based model access control
  - Enhanced authentication checks for private models
  - Secure API key storage with encryption

### Changed

- Enhanced GraphQL queries to include HuggingFace-specific fields
- Improved error handling for missing endpoints
- Updated response format with standardized structure

### Fixed

- Type annotations for full mypy compatibility
- Async/sync execution context handling
- Response extraction for various providers
- Union type issues with AnonymousUser

### Technical

- Full mypy type checking compatibility
- Comprehensive type annotations throughout codebase
- Connection pooling with httpx
- Retry logic with exponential backoff (3 attempts)
- Endpoint statistics tracking
- Proper handling of Union types

### Dependencies

- Added `httpx>=0.28.1` - Async HTTP client
- Added `tenacity>=9.1.2` - Retry logic
- Added `torch>=2.9.0` - PyTorch support (optional)
- Added `transformers>=4.57.1` - HuggingFace models (optional)
- Added `nest-asyncio>=1.6.0` - Nested event loop support

## [0.1.0] - 2025-XX-XX

### Added

- Initial release of DataSpace SDK
- Basic AIModel CRUD operations (read-only)
- Dataset management
- UseCase management
- Search functionality
- GraphQL support
- Keycloak authentication
- Organization and user management
- Base API client with authentication

[0.2.0]: https://github.com/CivicDataLab/DataSpaceBackend/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/CivicDataLab/DataSpaceBackend/releases/tag/v0.1.0
