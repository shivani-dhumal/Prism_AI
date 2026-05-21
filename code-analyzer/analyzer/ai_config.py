import json
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

from dotenv import load_dotenv


_ENV_LOADED = False
_CLIENT = None
_CLIENT_LOCK = threading.Lock()


def _load_env_once() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    # ai_config.py lives in code-analyzer/analyzer/, so .env lives one level up.
    code_analyzer_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    env_path = os.path.join(code_analyzer_root, ".env")
    load_dotenv(dotenv_path=env_path, override=False)
    _ENV_LOADED = True


@dataclass
class Settings:
    OPENWEBUI_BASE_URL: str
    OPENWEBUI_API_KEY: str
    LLM_MODEL: str
    inter_call_delay_s: float = 0.25
    request_timeout_s: float = 20.0


def get_settings() -> Settings:
    _load_env_once()
    return Settings(
        OPENWEBUI_BASE_URL=os.environ.get("OPENWEBUI_BASE_URL", "").strip(),
        OPENWEBUI_API_KEY=os.environ.get("OPENWEBUI_API_KEY", "").strip(),
        LLM_MODEL=os.environ.get("LLM_MODEL", "gemma-3").strip(),
        inter_call_delay_s=float(os.environ.get("INTER_CALL_DELAY_S", "0.25")),
        request_timeout_s=float(os.environ.get("AI_REQUEST_TIMEOUT_S", "20")),
    )


class RateLimiter:
    """
    Shared inter-call delay across threads.
    """

    def __init__(self, delay_s: float):
        self.delay_s = delay_s
        self._lock = threading.Lock()
        self._last_call_ts = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.time()
            elapsed = now - self._last_call_ts
            if elapsed < self.delay_s:
                time.sleep(self.delay_s - elapsed)
            self._last_call_ts = time.time()


_RATE_LIMITER: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    global _RATE_LIMITER
    if _RATE_LIMITER is None:
        s = get_settings()
        _RATE_LIMITER = RateLimiter(delay_s=s.inter_call_delay_s)
    return _RATE_LIMITER


def get_openai_client():
    """
    Singleton OpenAI-compatible client.
    """
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    settings = get_settings()
    placeholder_keys = {"replace-with-your-openwebui-api-key", "changeme", "your-api-key"}
    if (
        not settings.OPENWEBUI_BASE_URL
        or not settings.OPENWEBUI_API_KEY
        or settings.OPENWEBUI_API_KEY.lower() in placeholder_keys
    ):
        raise RuntimeError(
            "Missing OpenWebUI config. Set OPENWEBUI_BASE_URL and OPENWEBUI_API_KEY in code-analyzer/.env"
        )

    # Import lazily so unit tests can import this module without openai installed.
    from openai import OpenAI

    with _CLIENT_LOCK:
        if _CLIENT is None:
            _CLIENT = OpenAI(
                base_url=settings.OPENWEBUI_BASE_URL,
                api_key=settings.OPENWEBUI_API_KEY,
                timeout=settings.request_timeout_s,
            )
    return _CLIENT


def _strip_markdown_fences(text: str) -> str:
    if "```" not in text:
        return text
    # Remove opening ```json / ``` and closing ```
    # Keep this simple and tolerant.
    text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text.strip())
    text = re.sub(r"```$", "", text.strip())
    # Sometimes there is leading text before the fence; strip anything before the first fence.
    if "```" in text:
        parts = text.split("```")
        # Usually: [preamble, lang, content, ...]
        if len(parts) >= 3:
            text = parts[-2]
    return text.strip()


def _extract_first_json(text: str) -> Union[Dict[str, Any], List[Any]]:
    # Strategy 1: try direct
    try:
        return json.loads(text)
    except Exception:
        pass

    # Strategy 2: strip fences
    cleaned = _strip_markdown_fences(text)
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # Strategy 3: locate first { ... } or [ ... ]
    start_obj = cleaned.find("{")
    end_obj = cleaned.rfind("}")
    if start_obj != -1 and end_obj != -1 and end_obj > start_obj:
        candidate = cleaned[start_obj : end_obj + 1]
        try:
            return json.loads(candidate)
        except Exception:
            pass

    start_arr = cleaned.find("[")
    end_arr = cleaned.rfind("]")
    if start_arr != -1 and end_arr != -1 and end_arr > start_arr:
        candidate = cleaned[start_arr : end_arr + 1]
        try:
            return json.loads(candidate)
        except Exception:
            pass

    # Strategy 4: very light repair — remove trailing commas.
    repaired = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    try:
        return json.loads(repaired)
    except Exception:
        pass

    raise ValueError("Could not extract valid JSON from AI response")


def call_ai_json(messages: List[Dict[str, str]], max_retries: int = 5) -> Any:
    """
    Calls the local OpenWebUI via OpenAI SDK and returns parsed JSON.
    Retries on API errors and JSON extraction failures.
    """
    settings = get_settings()
    client = get_openai_client()
    limiter = get_rate_limiter()

    last_err: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            limiter.wait()
            resp = client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                temperature=0.2,
            )
            text = resp.choices[0].message.content or ""
            return _extract_first_json(text)
        except Exception as e:
            last_err = e
            # Backoff slightly on retries.
            time.sleep(0.75 * (attempt + 1))

    raise RuntimeError(f"AI call failed after {max_retries} retries: {last_err}")


def call_ai(messages: List[Dict[str, str]], max_retries: int = 5) -> Any:
    """
    Backwards-compatible public helper requested by the build spec.
    Returns parsed JSON from the OpenAI-compatible local LLM.
    """
    return call_ai_json(messages=messages, max_retries=max_retries)
