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


async def call_llm_json(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.3,
    max_tokens: int = 4000,
) -> dict:
    """Call the LLM and parse response as JSON."""
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
