"""
API Client for making requests to AI model endpoints.
Supports various authentication methods and providers.
"""

import json
import time
from typing import Any, Dict, Optional

import httpx
from asgiref.sync import sync_to_async
from django.utils import timezone
from tenacity import retry, stop_after_attempt, wait_exponential  # type: ignore

from api.models import AIModel, ModelAPIKey, ModelEndpoint


class ModelAPIClient:
    """Client for interacting with AI model APIs"""

    def __init__(self, model: AIModel):
        self.model = model
        self.endpoint = model.get_primary_endpoint()
        if not self.endpoint:
            raise ValueError(f"No primary endpoint configured for model {model.name}")

        # Get API key if available
        self.api_key = self._get_api_key()

    def _get_api_key(self) -> Optional[str]:
        """Get the active API key for this model"""
        api_key_obj = self.model.api_keys.filter(is_active=True).first()
        if api_key_obj:
            return api_key_obj.get_key()
        return None

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers including authentication"""
        headers = {"Content-Type": "application/json", **self.endpoint.headers}

        # Add authentication header
        if self.api_key and self.endpoint.auth_type != "NONE":
            if self.endpoint.auth_type == "BEARER":
                headers[self.endpoint.auth_header_name] = f"Bearer {self.api_key}"
            elif self.endpoint.auth_type == "API_KEY":
                headers[self.endpoint.auth_header_name] = self.api_key
            elif self.endpoint.auth_type == "CUSTOM":
                # Custom headers should be in endpoint.headers
                pass

        return headers

    def _build_request_body(
        self, input_text: str, parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Build request body based on provider and template"""
        body: Dict[str, Any]
        if self.endpoint.request_template:
            # Use custom template
            template_copy = self.endpoint.request_template.copy()
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
        """Get default request template based on provider"""
        provider = self.model.provider.upper()

        if provider == "OPENAI":
            return {
                "model": self.model.provider_model_id or "gpt-3.5-turbo",
                "messages": [{"role": "user", "content": input_text}],
                "temperature": parameters.get("temperature", 0.7),
                "max_tokens": parameters.get("max_tokens", self.model.max_tokens or 1000),
            }
        elif "LLAMA" in provider:
            # Llama models - format depends on provider
            if "OLLAMA" in provider:
                return {
                    "model": self.model.provider_model_id or "llama2",
                    "prompt": input_text,
                    "stream": False,
                    "options": {
                        "temperature": parameters.get("temperature", 0.7),
                        "num_predict": parameters.get("max_tokens", self.model.max_tokens or 1000),
                    },
                }
            elif "TOGETHER" in provider:
                return {
                    "model": self.model.provider_model_id or "togethercomputer/llama-2-7b-chat",
                    "prompt": input_text,
                    "temperature": parameters.get("temperature", 0.7),
                    "max_tokens": parameters.get("max_tokens", self.model.max_tokens or 1000),
                }
            elif "REPLICATE" in provider:
                return {
                    "version": self.model.provider_model_id,
                    "input": {
                        "prompt": input_text,
                        "temperature": parameters.get("temperature", 0.7),
                        "max_length": parameters.get("max_tokens", self.model.max_tokens or 1000),
                    },
                }
            else:
                # Generic Llama format (OpenAI-compatible)
                return {
                    "model": self.model.provider_model_id or "llama-2-7b-chat",
                    "messages": [{"role": "user", "content": input_text}],
                    "temperature": parameters.get("temperature", 0.7),
                    "max_tokens": parameters.get("max_tokens", self.model.max_tokens or 1000),
                }
        else:
            # Generic template for custom APIs
            return {"input": input_text, "parameters": parameters}

    def _extract_response(self, response_data: Dict) -> str:
        """Extract text response from API response"""
        if self.endpoint.response_path:
            # Use custom response path
            result: Any = self._get_nested_value(response_data, self.endpoint.response_path)
            return str(result)

        # Default extraction based on provider
        provider = self.model.provider.upper()

        try:
            if provider == "OPENAI":
                return str(response_data["choices"][0]["message"]["content"])
            elif "LLAMA" in provider:
                if "OLLAMA" in provider:
                    return str(response_data["response"])
                elif "TOGETHER" in provider:
                    return str(response_data["output"]["choices"][0]["text"])
                elif "REPLICATE" in provider:
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

    async def _update_endpoint_success(self) -> None:
        """Update endpoint statistics on successful call (async-safe)"""

        def _update() -> None:
            self.endpoint.total_requests += 1
            self.endpoint.last_success_at = timezone.now()
            self.endpoint.save(update_fields=["total_requests", "last_success_at"])

        await sync_to_async(_update)()

    async def _update_endpoint_failure(self) -> None:
        """Update endpoint statistics on failed call (async-safe)"""

        def _update() -> None:
            self.endpoint.failed_requests += 1
            self.endpoint.last_failure_at = timezone.now()
            self.endpoint.save(update_fields=["failed_requests", "last_failure_at"])

        await sync_to_async(_update)()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def call_async(
        self, input_text: str, parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make async API call to the model"""
        start_time = time.time()

        headers = self._build_headers()
        body = self._build_request_body(input_text, parameters)

        try:
            async with httpx.AsyncClient(timeout=self.endpoint.timeout_seconds) as client:
                if self.endpoint.http_method == "POST":
                    response = await client.post(self.endpoint.url, headers=headers, json=body)
                elif self.endpoint.http_method == "GET":
                    response = await client.get(self.endpoint.url, headers=headers, params=body)
                else:
                    raise ValueError(f"Unsupported HTTP method: {self.endpoint.http_method}")

                response.raise_for_status()
                response_data = response.json()

                latency_ms = (time.time() - start_time) * 1000

                # Update endpoint statistics (async-safe)
                await self._update_endpoint_success()

                # Extract response text
                output_text = self._extract_response(response_data)

                return {
                    "success": True,
                    "output": output_text,
                    "raw_response": response_data,
                    "latency_ms": latency_ms,
                    "status_code": response.status_code,
                }

        except httpx.HTTPStatusError as e:
            # Update failure statistics (async-safe)
            await self._update_endpoint_failure()

            return {
                "success": False,
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
                "status_code": e.response.status_code,
                "latency_ms": (time.time() - start_time) * 1000,
            }
        except Exception as e:
            # Update failure statistics (async-safe)
            await self._update_endpoint_failure()

            return {
                "success": False,
                "error": str(e),
                "latency_ms": (time.time() - start_time) * 1000,
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
