"""LLM client for Azure OpenAI — direct HTTP calls to GPT-4.1-mini."""

import json
import httpx
from config import settings


async def call_llm(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int = 4000,
) -> str:
    """Raw HTTP client for Azure OpenAI GPT-4.1-mini. Retries up to 3 times on disconnect."""
    import asyncio as _aio

    endpoint = settings.chat_completions_url

    headers = {
        "Content-Type": "application/json",
        "api-key": settings.AZURE_OPENAI_API_KEY,
    }

    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    last_error = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(endpoint, json=payload, headers=headers)
                if response.status_code != 200:
                    error_detail = response.text
                    raise Exception(f"LLM API error ({response.status_code}): {error_detail[:500]}")
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


async def call_llm_text(system_prompt: str, user_prompt: str, temperature: float = 0.5, max_tokens: int = 2000) -> str:
    """Make an async call to Azure OpenAI returning raw markdown/text."""
    import asyncio as _aio
    endpoint = settings.AZURE_OPENAI_ENDPOINT.rstrip("/")
    if "/openai/deployments/" in endpoint:
        endpoint = endpoint.split("/openai/deployments/")[0].rstrip("/")
    elif "?" in endpoint:
        endpoint = endpoint.split("?")[0].rstrip("/")

    url = (
        f"{endpoint}/openai/deployments/{settings.AZURE_OPENAI_DEPLOYMENT}"
        f"/chat/completions?api-version={settings.AZURE_OPENAI_API_VERSION}"
    )

    headers = {
        "Content-Type": "application/json",
        "api-key": settings.AZURE_OPENAI_API_KEY,
    }

    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    last_error = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code != 200:
                    raise Exception(f"API error ({response.status_code}): {response.text[:500]}")
                result = response.json()
                return result["choices"][0]["message"]["content"]
        except Exception as e:
            last_error = e
            wait = 2 ** attempt
            await _aio.sleep(wait)

    raise Exception(f"LLM request failed after 3 attempts: {last_error}")


async def call_llm_json(system_prompt: str, user_prompt: str, temperature: float = 0.5, max_tokens: int = 3000) -> dict:
    """Call the LLM and parse response as JSON."""
    json_system = system_prompt + "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no code fences, no extra text."
    response_text = await call_llm(json_system, user_prompt, temperature, max_tokens)

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


async def get_embedding(text: str) -> list[float]:
    """Get vector embedding for a piece of text using Azure OpenAI."""
    import asyncio as _aio
    
    endpoint = settings.AZURE_OPENAI_ENDPOINT.rstrip("/")
    if "/openai/deployments/" in endpoint:
        endpoint = endpoint.split("/openai/deployments/")[0].rstrip("/")
    elif "?" in endpoint:
        endpoint = endpoint.split("?")[0].rstrip("/")

    url = (
        f"{endpoint}/openai/deployments/{settings.AZURE_OPENAI_EMBEDDING_DEPLOYMENT}"
        f"/embeddings?api-version={settings.AZURE_OPENAI_API_VERSION}"
    )

    headers = {
        "Content-Type": "application/json",
        "api-key": settings.AZURE_OPENAI_API_KEY,
    }

    payload = {
        "input": text,
    }

    last_error = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code != 200:
                    raise Exception(f"Embedding API error ({response.status_code}): {response.text[:500]}")
                result = response.json()
                return result["data"][0]["embedding"]
        except Exception as e:
            last_error = e
            wait = 2 ** attempt
            await _aio.sleep(wait)
    raise Exception(f"Embedding request failed: {last_error}")
