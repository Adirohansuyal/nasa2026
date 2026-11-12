"""OpenRouter client for vision-grounded EARTHPULSE-X explanations."""

import os
import requests
from dotenv import load_dotenv


load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


def _headers() -> dict[str, str]:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("Set OPENROUTER_API_KEY in the environment or local .env file.")
    return {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}


def explain_image(prompt: str, image_data_uri: str, max_tokens: int = 700) -> str:
    """Send a plotted image and its project context to a Llama vision model."""
    response = requests.post(
        OPENROUTER_CHAT_URL,
        headers=_headers(),
        json={
            "model": OPENROUTER_MODEL,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_data_uri}},
                ],
            }],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        },
        timeout=90,
    )
    response.raise_for_status()
    payload = response.json()
    text = payload["choices"][0]["message"]["content"]
    if not isinstance(text, str) or not text.strip():
        raise ValueError("OpenRouter returned an empty explanation.")
    return text.strip()


def explain_text(
    prompt: str,
    max_tokens: int = 1100,
    system_prompt: str | None = None,
) -> str:
    """Ask the configured Llama model to explain structured project context."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    response = requests.post(
        OPENROUTER_CHAT_URL,
        headers=_headers(),
        json={
            "model": OPENROUTER_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.15,
        },
        timeout=90,
    )
    response.raise_for_status()
    payload = response.json()
    text = payload["choices"][0]["message"]["content"]
    if not isinstance(text, str) or not text.strip():
        raise ValueError("OpenRouter returned an empty explanation.")
    return text.strip()
