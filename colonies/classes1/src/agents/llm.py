import os

import httpx


class LLMError(Exception):
    pass


async def call_llm(
    system_prompt: str,
    user_prompt: str,
    backend: str,
    model: str,
    history: list[dict] | None = None,
) -> str:
    """Call LLM and return raw response text."""
    if backend == "ollama":
        return await _call_ollama(system_prompt, user_prompt, model, history)
    elif backend == "openai":
        return await _call_openai(system_prompt, user_prompt, model, history)
    else:
        raise LLMError(f"Unknown backend: {backend}")


async def _call_ollama(
    system_prompt: str,
    user_prompt: str,
    model: str,
    history: list[dict] | None = None,
) -> str:
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_prompt})
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{ollama_url}/api/chat", json=payload)
            response.raise_for_status()
            return response.json()["message"]["content"]
    except httpx.HTTPError as e:
        raise LLMError(f"Ollama request failed: {e}") from e
    except (KeyError, ValueError) as e:
        raise LLMError(f"Ollama response parse error: {e}") from e


async def _call_openai(
    system_prompt: str,
    user_prompt: str,
    model: str,
    history: list[dict] | None = None,
) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMError("OPENAI_API_KEY not set")
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_prompt})
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
        )
        return response.choices[0].message.content
    except Exception as e:
        raise LLMError(f"OpenAI request failed: {e}") from e
