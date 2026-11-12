"""LLM access. Production = Google Gemini API free tier (official REST endpoint).
Demo = deterministic mock answers supplied by each agent, clearly labelled."""
from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Optional

import requests

from .config import demo_mode, env, redact

DEFAULT_MODELS = "gemini-3.5-flash,gemini-3-flash-preview,gemini-3.8-flash,gemini-3.1-flash-lite,gemini-flash-latest"  # 3.5 first: fast + reliable on free tier (3.8 often 503)


class LLMError(RuntimeError):
    pass


def _extract_json(text: str) -> Any:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=0)
    return json.loads(text[start:])


def gemini_json(system: str, prompt: str, temperature: float = 0.9, session: Any = requests) -> Any:
    key = env("GEMINI_API_KEY")
    if not key:
        raise LLMError("GEMINI_API_KEY missing")
    models = [m.strip() for m in env("GEMINI_MODELS", DEFAULT_MODELS).split(",") if m.strip()]
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    last = ""
    for model in models:
        for attempt in range(3):
            try:
                r = session.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"x-goog-api-key": key, "content-type": "application/json"},
                    json=body, timeout=90)
            except requests.RequestException as e:  # transient network error → backoff
                last = f"{model}: {e}"
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 404:
                last = f"{model}: not found"
                break  # model not available → next model, no retry
            if r.status_code == 503 and model != models[-1]:  # overloaded → try the next model right away
                last = f"{model}: HTTP 503"
                break
            if r.status_code in (429, 500, 502, 503, 504):
                last = f"{model}: HTTP {r.status_code}"
                time.sleep(min(30, 2 ** (attempt + 2)))
                continue
            if r.status_code != 200:
                last = f"{model}: HTTP {r.status_code} {r.text[:200]}"
                break
            try:
                parts = r.json()["candidates"][0]["content"]["parts"]
                return _extract_json("".join(p.get("text", "") for p in parts))
            except Exception as e:
                last = f"{model}: bad JSON ({e})"
                continue
    raise LLMError(redact(f"all Gemini models failed — {last}"))


def ask_json(system: str, prompt: str, mock: Optional[Callable[[], Any]] = None, temperature: float = 0.9) -> Any:
    if demo_mode():
        if mock is None:
            raise LLMError("no mock answer for demo mode")
        return mock()
    return gemini_json(system, prompt, temperature)
