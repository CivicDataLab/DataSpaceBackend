"""
API Client for making requests to AI model endpoints.
Supports various authentication methods and providers.
Works with VersionProvider configuration.
"""

import time
from typing import Any, Dict, Optional

import httpx
from asgiref.sync import sync_to_async
from django.utils import timezone
from tenacity import retry, stop_after_attempt, wait_exponential  # type: ignore

from api.models.AIModelVersion import VersionProvider


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
                replaced_value = value.replace("{input}", input_text)
                replaced_value = replaced_value.replace("{prompt}", input_text)
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

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def call_async(
        self, input_text: str, parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make async API call to the model via the provider configuration."""
        start_time = time.time()

        headers = self._build_headers()
        body = self._build_request_body(input_text, parameters)

        endpoint_url: str = self.provider.api_endpoint_url  # type: ignore[assignment]

        try:
            async with httpx.AsyncClient(timeout=self.provider.api_timeout_seconds) as client:
                if self.provider.api_http_method == "POST":
                    response = await client.post(endpoint_url, headers=headers, json=body)
                elif self.provider.api_http_method == "GET":
                    response = await client.get(endpoint_url, headers=headers, params=body)
                else:
                    raise ValueError(f"Unsupported HTTP method: {self.provider.api_http_method}")

                response.raise_for_status()
                response_data = response.json()

                latency_ms = (time.time() - start_time) * 1000

                # Update provider statistics (async-safe)
                await self._update_provider_success()

                # Extract response text
                output_text = self._extract_response(response_data)

                return {
                    "success": True,
                    "output": output_text,
                    "raw_response": response_data,
                    "latency_ms": latency_ms,
                    "status_code": response.status_code,
                    "provider": self.provider.provider,
                    "model_id": self.provider.provider_model_id,
                }

        except httpx.HTTPStatusError as e:
            # Update failure statistics (async-safe)
            await self._update_provider_failure()

            return {
                "success": False,
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
                "status_code": e.response.status_code,
                "latency_ms": (time.time() - start_time) * 1000,
                "provider": self.provider.provider,
                "model_id": self.provider.provider_model_id,
            }
        except Exception as e:
            # Update failure statistics (async-safe)
            await self._update_provider_failure()

            return {
                "success": False,
                "error": str(e),
                "latency_ms": (time.time() - start_time) * 1000,
                "provider": self.provider.provider,
                "model_id": self.provider.provider_model_id,
            }

    def call(self, input_text: str, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make synchronous API call to the model"""
        import asyncio

        # Run async call in sync context
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is already running, use nest_asyncio
                import nest_asyncio  # type: ignore

                nest_asyncio.apply()
                return loop.run_until_complete(self.call_async(input_text, parameters))
            else:
                return asyncio.run(self.call_async(input_text, parameters))
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(self.call_async(input_text, parameters))
