"""LLM client for Azure AI Foundry — provides both raw HTTP and AutoGen custom client."""

import json
import httpx
from autogen import ModelClient
from config import settings


async def call_llm(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int = 4000,
) -> str:
    """Raw HTTP client for the Azure-deployed Phi-4 model. Retries up to 3 times on disconnect."""
    import asyncio as _aio
    endpoint = settings.AZURE_PHI4_ENDPOINT
    if "?" in endpoint:
        base, params = endpoint.split("?", 1)
    else:
        base = endpoint
        params = ""

    if not base.rstrip("/").endswith("/chat/completions"):
        base = base.rstrip("/") + "/chat/completions"

    if "api-version" not in params:
        params = "api-version=2024-05-01-preview" + ("&" + params if params else "")

    endpoint = f"{base}?{params}" if params else base

    headers = {
        "Content-Type": "application/json",
        "api-key": settings.AZURE_PHI4_API_KEY,
    }

    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "model": "Phi-4",
    }

    last_error = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(endpoint, json=payload, headers=headers)
                if response.status_code != 200:
                    error_detail = response.text
                    raise Exception(f"LLM API error ({response.status_code}): {error_detail[:300]}")
                result = response.json()
                return result["choices"][0]["message"]["content"]
        except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError) as e:
            last_error = e
            wait = 2 ** attempt
            print(f"[LLM] Attempt {attempt+1} failed ({type(e).__name__}: {e}), retrying in {wait}s...")
            await _aio.sleep(wait)
        except Exception:
            raise
    raise Exception(f"LLM request failed after 3 attempts: {last_error}")


async def call_llm_json(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.3,
    max_tokens: int = 4000,
) -> dict:
    """Raw JSON parser."""
    json_system = system_prompt + "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no code fences, no extra text."
    response_text = await call_llm(json_system, user_message, temperature, max_tokens)

    cleaned = response_text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(cleaned[start:end])
        raise ValueError(f"Could not parse LLM response as JSON: {cleaned[:200]}")


class AzurePhi4CustomClient(ModelClient):
    """A custom AutoGen Model Client connecting to Azure AI Foundry Serverless using `api-key`."""
    
    def __init__(self, config, **kwargs):
        self.endpoint = settings.AZURE_PHI4_ENDPOINT
        self.api_key = settings.AZURE_PHI4_API_KEY
        print(f"[AutoGen Client] Initialized Phi-4 Custom Client")

    def create(self, params):
        """Synchronous create method called by AutoGen agents."""
        messages = params.get("messages", [])
        temperature = params.get("temperature", 0.3)
        max_tokens = params.get("max_tokens", 4000)

        endpoint = self.endpoint
        if "?" in endpoint:
            base, prm = endpoint.split("?", 1)
        else:
            base = endpoint
            prm = ""

        if not base.rstrip("/").endswith("/chat/completions"):
            base = base.rstrip("/") + "/chat/completions"

        if "api-version" not in prm:
            prm = "api-version=2024-05-01-preview" + ("&" + prm if prm else "")
            
        final_endpoint = f"{base}?{prm}" if prm else base

        headers = {
            "Content-Type": "application/json",
            "api-key": self.api_key,
        }

        # AutoGen sends unstructured complex list sometimes, sanitize to strictly what phi-4 wants
        sanitized_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            # Only append valid structured strings
            if isinstance(content, str) and content.strip():
                sanitized_messages.append({"role": role, "content": content})

        payload = {
            "messages": sanitized_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "model": "Phi-4"
        }

        # AutoGen is synchronous by default unless using aio, using sync httpx here
        import httpx as sync_httpx
        with sync_httpx.Client(timeout=600.0) as client:
            response = client.post(final_endpoint, json=payload, headers=headers)
            
            if response.status_code != 200:
                raise Exception(f"AutoGen LLM error: {response.text[:300]}")
                
            data = response.json()
            
        print(f"\n[DEBUG] Raw LLM Response from Azure Payload:\n{data['choices'][0]['message']['content'][:200]}\n")

        # Return exact structure AutoGen ModelClient expects (SimpleNamespace is often used)
        from types import SimpleNamespace
        
        reply = data["choices"][0]["message"]["content"]
        
        # Use a dict-like Choice object that AutoGen 0.2 expects
        choice = SimpleNamespace(message=SimpleNamespace(content=reply, function_call=None, role="assistant"))
        
        return SimpleNamespace(
            choices=[choice],
            model="Phi-4",
            usage=SimpleNamespace(
                prompt_tokens=data.get("usage", {}).get("prompt_tokens", 0),
                completion_tokens=data.get("usage", {}).get("completion_tokens", 0),
                total_tokens=data.get("usage", {}).get("total_tokens", 0)
            )
        )

    def message_retrieval(self, response):
        """Extract the message from the response object. Must return a list of strings."""
        try:
            return [response.choices[0].message.content]
        except AttributeError:
            # Handle cases where response might be wrapped differently internally by AutoGen
            if isinstance(response, list) and len(response) > 0:
                return [response[0]]
            if isinstance(response, str):
                return [response]
            return [str(response)]

    def cost(self, response) -> float:
        """Return the cost of the response."""
        return 0.0  # Serverless/Students Free Tier

    @staticmethod
    def get_usage(response):
        """Return token usage."""
        return {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
            "cost": 0.0,
            "model": "Phi-4"
        }
