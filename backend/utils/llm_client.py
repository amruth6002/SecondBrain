"""LLM client for Azure AI Foundry — direct HTTP calls to Phi-4."""

import json
import httpx
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
