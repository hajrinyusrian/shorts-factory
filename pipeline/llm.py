"""Thin Gemini wrapper: JSON-schema output, retries for the free-tier rate limits, model fallback."""
from __future__ import annotations

import json
import os
import re
import time
from typing import Type, TypeVar

from pydantic import BaseModel

from .utils import log

T = TypeVar("T", bound=BaseModel)


def is_model_unavailable(exc: Exception) -> bool:
    """True when the model itself is gone / not allowed for this key (retrying cannot help)."""
    code = getattr(exc, "code", None)
    if code in (403, 404):
        return True
    msg = str(exc)
    return "NOT_FOUND" in msg or "PERMISSION_DENIED" in msg


class LLM:
    def __init__(self, models: list[str], api_key: str | None = None):
        from google import genai  # imported lazily so tests can run without the SDK configured
        self.genai = genai
        self.client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"])
        self.models = models
        self.dead: set[str] = set()   # models that answered 404/403: skipped for the rest of the run

    def json(self, prompt: str, schema: Type[T], *, system: str | None = None, temperature: float = 0.3,
             retries: int = 4) -> T:
        from google.genai import types
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=schema,
        )
        last: Exception | None = None
        for attempt in range(retries):
            alive = [m for m in self.models if m not in self.dead]
            if not alive:
                raise RuntimeError(
                    f"No usable Gemini model (unavailable: {sorted(self.dead)}). Google restricts/retires models; "
                    "update llm.models in config.yaml (ai.google.dev/gemini-api/docs/deprecations). "
                    f"Last error: {last}")
            for model in alive:
                try:
                    resp = self.client.models.generate_content(model=model, contents=prompt, config=cfg)
                    parsed = getattr(resp, "parsed", None)
                    if isinstance(parsed, schema):
                        return parsed
                    text = (resp.text or "").strip()
                    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
                    return schema.model_validate(json.loads(text))
                except Exception as exc:  # noqa: BLE001 - we retry on anything transient
                    last = exc
                    msg = str(exc)
                    transient = any(k in msg for k in ("429", "500", "502", "503", "504", "RESOURCE_EXHAUSTED",
                                                       "UNAVAILABLE", "DEADLINE", "overloaded"))
                    log.warning("Gemini %s failed (attempt %d): %s", model, attempt + 1, msg[:160])
                    if is_model_unavailable(exc):
                        self.dead.add(model)
                        log.warning("model %s marked unavailable for this run", model)
                        continue
                    if not transient and not isinstance(exc, (ValueError, json.JSONDecodeError)):
                        continue
            time.sleep(min(60, 8 * (attempt + 1)))
        raise RuntimeError(f"Gemini failed after {retries} attempts: {last}")
