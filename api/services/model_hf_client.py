"""
Hugging Face Client for running local or remote model inference.
Supports both pipeline-based and model-class-based inference.
Works with VersionProvider configuration.
"""

import time
from typing import Any, Dict, Optional, Tuple

import torch  # type: ignore
from asgiref.sync import sync_to_async
from django.utils import timezone
from tenacity import retry, stop_after_attempt, wait_exponential  # type: ignore
from transformers import (  # type: ignore
    AutoModelForCausalLM,
    AutoModelForMaskedLM,
    AutoModelForMultipleChoice,
    AutoModelForNextSentencePrediction,
    AutoModelForQuestionAnswering,
    AutoModelForSeq2SeqLM,
    AutoModelForSequenceClassification,
    AutoModelForTokenClassification,
    AutoTokenizer,
    pipeline,
)

from api.models.AIModelVersion import VersionProvider


class ModelHFClient:
    """Client for interacting with Hugging Face models via VersionProvider configuration."""

    def __init__(self, provider: VersionProvider):
        """
        Initialize the HuggingFace client with a VersionProvider.

        Args:
            provider: VersionProvider instance with HuggingFace configuration
        """
        self.provider = provider
        self.version = provider.version
        self.model = provider.version.ai_model
        self.device = self._get_device()

        # Validate provider type
        if provider.provider != "HUGGINGFACE":
            raise ValueError(
                f"ModelHFClient requires HUGGINGFACE provider, got {provider.provider}"
            )

        # Validate model ID is set
        if not provider.provider_model_id:
            raise ValueError(
                f"No provider_model_id configured for HuggingFace provider on model {self.model.name}"
            )

        self.model_map = {
            "AutoModelForCausalLM": AutoModelForCausalLM,
            "AutoModelForSeq2SeqLM": AutoModelForSeq2SeqLM,
            "AutoModelForSequenceClassification": AutoModelForSequenceClassification,
            "AutoModelForNextSentencePrediction": AutoModelForNextSentencePrediction,
            "AutoModelForMultipleChoice": AutoModelForMultipleChoice,
            "AutoModelForTokenClassification": AutoModelForTokenClassification,
            "AutoModelForQuestionAnswering": AutoModelForQuestionAnswering,
            "AutoModelForMaskedLM": AutoModelForMaskedLM,
        }
        self.task_map = {
            "TRANSLATION": "translation",
            "TEXT_GENERATION": "text-generation",
            "SUMMARIZATION": "summarization",
            "QUESTION_ANSWERING": "question-answering",
            "SENTIMENT_ANALYSIS": "sentiment-analysis",
            "TEXT_CLASSIFICATION": "text-classification",
            "NAMED_ENTITY_RECOGNITION": "ner",
            "TEXT_TO_SPEECH": "text-to-speech",
            "SPEECH_TO_TEXT": "automatic-speech-recognition",
            "OTHER": "",
        }

    def _get_device(self) -> int:
        """Select device (0 for GPU if available, else CPU)."""
        return 0 if torch.cuda.is_available() else -1

    def _get_torch_dtype(self) -> Any:
        """Get torch dtype based on provider configuration."""
        dtype_map = {
            "auto": "auto",
            "float16": torch.float16,
            "float32": torch.float32,
            "bfloat16": torch.bfloat16,
        }
        dtype_str = self.provider.hf_torch_dtype or "auto"
        if dtype_str == "auto":
            return torch.float16 if torch.cuda.is_available() else torch.float32
        return dtype_map.get(dtype_str, torch.float32)

    def _load_pipeline(self) -> Any:
        """Initialize a Hugging Face pipeline."""
        framework = self.provider.framework or "pt"
        return pipeline(
            task=self.task_map.get(self.model.model_type, "text-generation"),
            model=self.provider.provider_model_id,
            framework=framework,
            device=self.device,
            trust_remote_code=self.provider.hf_trust_remote_code,
            token=self.provider.hf_auth_token or None,
        )

    def _load_model_and_tokenizer(self) -> Tuple[Any, Any]:
        """Load model and tokenizer for manual inference."""
        tokenizer = AutoTokenizer.from_pretrained(
            self.provider.provider_model_id,
            trust_remote_code=self.provider.hf_trust_remote_code,
            token=self.provider.hf_auth_token or None,
        )

        model_class = self.model_map.get(
            self.provider.hf_model_class or "AutoModelForCausalLM", AutoModelForCausalLM
        )

        # Build model loading kwargs
        model_kwargs: Dict[str, Any] = {
            "pretrained_model_name_or_path": self.provider.provider_model_id,
            "trust_remote_code": self.provider.hf_trust_remote_code,
            "torch_dtype": self._get_torch_dtype(),
            "token": self.provider.hf_auth_token or None,
            "device_map": self.provider.hf_device_map or "auto",
        }

        # Add attention implementation if specified
        if self.provider.hf_attn_implementation:
            model_kwargs["attn_implementation"] = self.provider.hf_attn_implementation

        model = model_class.from_pretrained(**model_kwargs)

        return model, tokenizer

    def _generate_from_model(self, model: Any, tokenizer: Any, input_text: str) -> str:
        """Run generation with tokenizer/model."""
        inputs = tokenizer(
            input_text,
            padding=True,
            truncation=True,
            return_tensors="pt",
        )

        with torch.no_grad():
            outputs = model.generate(**inputs, use_cache=False)

        decoded_text: str = tokenizer.batch_decode(outputs, skip_special_tokens=True)[0]
        return decoded_text

    async def _update_success(self) -> None:
        """Update provider statistics for successful inference."""

        def _update() -> None:
            self.provider.updated_at = timezone.now()
            self.provider.save(update_fields=["updated_at"])

        await sync_to_async(_update)()

    async def _update_failure(self) -> None:
        """Update provider statistics for failed inference."""

        def _update() -> None:
            self.provider.updated_at = timezone.now()
            self.provider.save(update_fields=["updated_at"])

        await sync_to_async(_update)()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def call_async(self, input_text: str) -> Dict[str, Any]:
        """
        Run asynchronous inference on the model.
        Supports both pipeline and manual model modes based on provider configuration.
        """
        start_time = time.time()
        try:
            if self.provider.hf_use_pipeline:
                pipe = self._load_pipeline()
                result = pipe(input_text)
                output_text = result if isinstance(result, str) else str(result)
            else:
                model, tokenizer = self._load_model_and_tokenizer()
                output_text = self._generate_from_model(model, tokenizer, input_text)

            latency_ms = (time.time() - start_time) * 1000
            await self._update_success()

            return {
                "success": True,
                "output": output_text,
                "latency_ms": latency_ms,
                "provider": self.provider.provider,
                "model_id": self.provider.provider_model_id,
            }

        except Exception as e:
            await self._update_failure()
            return {
                "success": False,
                "error": str(e),
                "latency_ms": (time.time() - start_time) * 1000,
                "provider": self.provider.provider,
                "model_id": self.provider.provider_model_id,
            }

    def call(self, input_text: str) -> Dict[str, Any]:
        """Run synchronous inference by wrapping async call."""
        import asyncio

        import nest_asyncio  # type: ignore

        try:
            # Case 1: We're in a normal sync context (Django shell, Python script)
            return asyncio.run(self.call_async(input_text))
        except RuntimeError as e:
            if "asyncio.run() cannot be called from a running event loop" in str(e):
                # Case 2: We're inside Jupyter/IPython or any async event loop
                nest_asyncio.apply()
                loop = asyncio.get_event_loop()
                return loop.run_until_complete(self.call_async(input_text))
            elif "no current event loop" in str(e).lower():
                # Case 3: No loop exists (Python ≥3.12)
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(self.call_async(input_text))
            else:
                raise
