"""
API Client for making requests to AI model endpoints.
Supports various authentication methods and providers.
Works with VersionProvider configuration.
"""

import asyncio
import time
from typing import Any, Dict, Optional

import httpx
import structlog
from asgiref.sync import sync_to_async
from django.utils import timezone
from tenacity import retry, stop_after_attempt, wait_exponential  # type: ignore

from api.models.AIModelVersion import VersionProvider
from api.utils.outbound_url import BlockedURLError, PublicTarget, resolve_public_url

logger = structlog.get_logger("dataspace.model_api_client")

NOT_JSON_MESSAGE = "The model provider did not return JSON."
UNREADABLE_MESSAGE = "Could not read the model provider's response."
UNREACHABLE_MESSAGE = "Could not get a response from the model provider."


class _ProviderReplyError(Exception):
    """A failed call whose message is safe to return to the caller."""


class ModelAPIClient:
    """Client for interacting with AI model APIs via VersionProvider configuration."""

    def __init__(self, provider: VersionProvider):
        """
        Initialize the API client with a VersionProvider.

        Args:
            provider: VersionProvider instance with API configuration
        """
        self.provider = provider
        self.version = provider.version
        self.model = provider.version.ai_model

        # Validate that we have an API endpoint configured
        if not provider.api_endpoint_url:
            raise ValueError(
                f"No API endpoint URL configured for provider {provider.provider} "
                f"on model {self.model.name}"
            )

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers including authentication."""
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            **(self.provider.api_headers or {}),
        }

        # Add authentication header
        if self.provider.api_key and self.provider.api_auth_type != "NONE":
            auth_value = self.provider.api_key
            if self.provider.api_auth_type == "BEARER":
                auth_value = f"{self.provider.api_key_prefix} {self.provider.api_key}".strip()
            elif self.provider.api_auth_type == "API_KEY":
                # Just use the key directly
                pass
            elif self.provider.api_auth_type == "BASIC":
                import base64

                auth_value = f"Basic {base64.b64encode(self.provider.api_key.encode()).decode()}"

            headers[self.provider.api_auth_header_name] = auth_value

        return headers

    def _build_request_body(
        self, input_text: str, parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Build request body based on provider and template."""
        body: Dict[str, Any]
        if self.provider.api_request_template:
            # Use custom template
            template_copy = self.provider.api_request_template.copy()
            # Replace placeholders
            body = self._replace_placeholders(template_copy, input_text, parameters or {})
        else:
            # Default templates based on provider
            body = self._get_default_template(input_text, parameters or {})

        return body

    def _replace_placeholders(self, template: Dict, input_text: str, parameters: Dict) -> Dict:
        """Replace placeholders in template"""
        result: Dict[str, Any] = {}
        for key, value in template.items():
            if isinstance(value, str):
                # template = {
                #   "model": "{model_id}",
                #   "messages": [{"role": "user", "content": "{input}"}]
                #   "temperature": {temperature},
                #   "max_tokens": {max_tokens}
                # }
                # parameters = {
                #   "temperature": 0.7,
                #   "max_tokens": 1000
                # }
                #
                replaced_value = value.replace("{input}", input_text)
                replaced_value = replaced_value.replace("{prompt}", input_text)
                replaced_value = replaced_value.replace(
                    "{model_id}", self.provider.provider_model_id
                )
                # Replace parameter placeholders
                for param_key, param_value in parameters.items():
                    replaced_value = replaced_value.replace(f"{{{param_key}}}", str(param_value))
                result[key] = replaced_value
            elif isinstance(value, dict):
                result[key] = self._replace_placeholders(value, input_text, parameters)
            elif isinstance(value, list):
                result[key] = [
                    (
                        self._replace_placeholders(item, input_text, parameters)
                        if isinstance(item, dict)
                        else item
                    )
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def _get_default_template(self, input_text: str, parameters: Dict) -> Dict[str, Any]:
        """Get default request template based on provider."""
        provider_type = self.provider.provider.upper()
        model_id = self.provider.provider_model_id
        max_tokens = self.version.max_tokens or 1000

        if provider_type == "OPENAI":
            return {
                "model": model_id or "gpt-3.5-turbo",
                "messages": [{"role": "user", "content": input_text}],
                "temperature": parameters.get("temperature", 0.7),
                "max_tokens": parameters.get("max_tokens", max_tokens),
            }
        elif "LLAMA" in provider_type:
            # Llama models - format depends on provider
            if "OLLAMA" in provider_type:
                return {
                    "model": model_id or "llama2",
                    "prompt": input_text,
                    "stream": False,
                    "options": {
                        "temperature": parameters.get("temperature", 0.7),
                        "num_predict": parameters.get("max_tokens", max_tokens),
                    },
                }
            elif "TOGETHER" in provider_type:
                return {
                    "model": model_id or "togethercomputer/llama-2-7b-chat",
                    "prompt": input_text,
                    "temperature": parameters.get("temperature", 0.7),
                    "max_tokens": parameters.get("max_tokens", max_tokens),
                }
            elif "REPLICATE" in provider_type:
                return {
                    "version": model_id,
                    "input": {
                        "prompt": input_text,
                        "temperature": parameters.get("temperature", 0.7),
                        "max_length": parameters.get("max_tokens", max_tokens),
                    },
                }
            else:
                # Generic Llama format (OpenAI-compatible)
                return {
                    "model": model_id or "llama-2-7b-chat",
                    "messages": [{"role": "user", "content": input_text}],
                    "temperature": parameters.get("temperature", 0.7),
                    "max_tokens": parameters.get("max_tokens", max_tokens),
                }
        else:
            # Generic template for custom APIs
            return {"input": input_text, "parameters": parameters}

    def _extract_response(self, response_data: Dict) -> str:
        """Extract text response from API response."""
        if self.provider.api_response_path:
            # Use custom response path
            result: Any = self._get_nested_value(response_data, self.provider.api_response_path)
            return str(result)

        # Default extraction based on provider
        provider_type = self.provider.provider.upper()

        try:
            if provider_type == "OPENAI":
                return str(response_data["choices"][0]["message"]["content"])
            elif "LLAMA" in provider_type:
                if "OLLAMA" in provider_type:
                    return str(response_data["response"])
                elif "TOGETHER" in provider_type:
                    return str(response_data["output"]["choices"][0]["text"])
                elif "REPLICATE" in provider_type:
                    # Replicate returns array of strings
                    output = response_data.get("output", [])
                    return "".join(output) if isinstance(output, list) else str(output)
                else:
                    # Try OpenAI-compatible format first
                    if "choices" in response_data:
                        return str(response_data["choices"][0]["message"]["content"])
                    elif "response" in response_data:
                        return str(response_data["response"])
                    elif "text" in response_data:
                        return str(response_data["text"])

            # Try common patterns for custom APIs
            if "text" in response_data:
                return str(response_data["text"])
            elif "output" in response_data:
                return str(response_data["output"])
            elif "response" in response_data:
                return str(response_data["response"])
            elif "content" in response_data:
                return str(response_data["content"])
            else:
                return str(response_data)
        except (KeyError, IndexError, TypeError) as e:
            raise ValueError(f"Could not extract response from API: {e}")

    def _get_nested_value(self, data: Dict, path: str) -> Any:
        """Get nested value from dict using dot notation (e.g., 'choices[0].message.content')"""
        import re

        keys = re.split(r"\.|\[|\]", path)
        keys = [k for k in keys if k]  # Remove empty strings

        current = data
        for key in keys:
            if key.isdigit():
                current = current[int(key)]
            else:
                current = current[key]

        return current

    async def _update_provider_success(self) -> None:
        """Update provider statistics on successful call (async-safe)."""

        def _update() -> None:
            # Update provider's updated_at timestamp
            self.provider.updated_at = timezone.now()
            self.provider.save(update_fields=["updated_at"])

        await sync_to_async(_update)()

    async def _update_provider_failure(self) -> None:
        """Update provider statistics on failed call (async-safe)."""

        def _update() -> None:
            # Update provider's updated_at timestamp
            self.provider.updated_at = timezone.now()
            self.provider.save(update_fields=["updated_at"])

        await sync_to_async(_update)()

    def _failure(
        self, error: str, start_time: float, status_code: Optional[int] = None
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "success": False,
            "error": error,
            "latency_ms": (time.time() - start_time) * 1000,
            "provider": self.provider.provider,
            "model_id": self.provider.provider_model_id,
        }
        if status_code is not None:
            result["status_code"] = status_code
        return result

    def _success(self, response: httpx.Response, start_time: float) -> Dict[str, Any]:
        response.raise_for_status()  # also refuses redirects, which are never followed
        if "application/json" not in response.headers.get("content-type", ""):
            raise _ProviderReplyError(NOT_JSON_MESSAGE)
        response_data = response.json()
        latency_ms = (time.time() - start_time) * 1000
        try:
            output_text = self._extract_response(response_data)
        except (ValueError, KeyError, IndexError, TypeError):
            raise _ProviderReplyError(UNREADABLE_MESSAGE)
        return {
            "success": True,
            "output": output_text,
            "raw_response": response_data,
            "latency_ms": latency_ms,
            "status_code": response.status_code,
            "provider": self.provider.provider,
            "model_id": self.provider.provider_model_id,
        }

    def _handle_error(self, error: Exception, start_time: float) -> Dict[str, Any]:
        """Client-safe result for a failed call. Raw error text could reveal internal
        hosts, ports or the API key (the URL may carry it), so it is only logged by type."""
        if isinstance(error, BlockedURLError):
            return self._failure(str(error), start_time)
        if isinstance(error, httpx.HTTPStatusError):
            code = error.response.status_code
            return self._failure(f"The model provider answered with HTTP {code}.", start_time, code)
        if isinstance(error, _ProviderReplyError):
            return self._failure(str(error), start_time)
        logger.warning(
            "model provider call failed",
            provider_id=self.provider.id,
            error_type=type(error).__name__,
        )
        return self._failure(UNREACHABLE_MESSAGE, start_time)

    def _send_kwargs(
        self, target: PublicTarget, input_text: str, parameters: Optional[Dict]
    ) -> Dict:
        method = self.provider.api_http_method
        if method not in ("POST", "GET"):
            raise _ProviderReplyError(f"Unsupported HTTP method: {method}")
        body = self._build_request_body(input_text, parameters)
        kwargs = target.request_kwargs()
        # The Host header always names the checked URL's host, whatever api_headers says.
        headers = {k: v for k, v in self._build_headers().items() if k.lower() != "host"}
        kwargs["headers"] = {**headers, **kwargs["headers"]}
        kwargs["json" if method == "POST" else "params"] = body
        return {"method": method, "url": target.url, **kwargs}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def call_async(
        self, input_text: str, parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make async API call to the model via the provider configuration."""
        start_time = time.time()
        try:
            # Resolve once and connect to that address only (see api/utils/outbound_url.py).
            target = await asyncio.to_thread(resolve_public_url, self._endpoint_url())
            async with httpx.AsyncClient(
                timeout=self.provider.api_timeout_seconds, follow_redirects=False
            ) as client:
                response = await client.request(**self._send_kwargs(target, input_text, parameters))
            result = self._success(response, start_time)
            await self._update_provider_success()
            return result
        except Exception as error:
            await self._update_provider_failure()
            return self._handle_error(error, start_time)

    def call(self, input_text: str, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make synchronous API call to the model using httpx sync client."""
        start_time = time.time()
        try:
            # Resolve once and connect to that address only (see api/utils/outbound_url.py).
            target = resolve_public_url(self._endpoint_url())
            with httpx.Client(
                timeout=self.provider.api_timeout_seconds, follow_redirects=False
            ) as client:
                response = client.request(**self._send_kwargs(target, input_text, parameters))
            result = self._success(response, start_time)
        except Exception as error:
            result = self._handle_error(error, start_time)
        self.provider.updated_at = timezone.now()
        self.provider.save(update_fields=["updated_at"])
        return result

    def _endpoint_url(self) -> str:
        return self.provider.api_endpoint_url  # type: ignore[return-value]
