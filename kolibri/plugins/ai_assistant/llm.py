# flake8: noqa: E501
import json
import logging
import os
import re

import requests
from django.conf import settings

from kolibri.utils.conf import KOLIBRI_HOME
from kolibri.utils.conf import OPTIONS


logger = logging.getLogger(__name__)

# PID file written by the ``serve_ai_models`` management command.
_AI_SERVER_PID_FILE = os.path.join(KOLIBRI_HOME, "ai_server.json")

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")

# Cache: prompt name -> (mtime, content)
_prompt_cache = {}


def load_prompt(name):
    """Load a prompt template from the prompts/ directory.

    In DEBUG mode, reloads from disk when the file's mtime changes.
    In production, caches after first load.
    """
    path = os.path.join(_PROMPTS_DIR, name)
    cached = _prompt_cache.get(name)

    if cached is not None:
        if not settings.DEBUG:
            return cached[1]
        mtime = os.path.getmtime(path)
        if mtime == cached[0]:
            return cached[1]

    mtime = os.path.getmtime(path)
    with open(path) as f:
        content = f.read().strip()
    _prompt_cache[name] = (mtime, content)
    return content


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

def robust_json_parser(json_str):

    if isinstance(json_str, list):
        json_str = json_str[0]
    if isinstance(json_str, dict):
        if "text" in json_str:
            json_str = json_str["text"]
    if not isinstance(json_str, str):
        raise ValueError("Input is not a dict, str, or a list of dicts or strs.")

    if not json_str:
        return None

    # remove everything before the first '{' or '[' and after the last '}' or ']'
    json_str_1 = json_str[json_str.find("{") : json_str.rfind("}") + 1]
    json_str_2 = json_str[json_str.find("[") : json_str.rfind("]") + 1]

    if len(json_str_1) > len(json_str_2):
        json_str = json_str_1
    elif len(json_str_1) < len(json_str_2):
        json_str = json_str_2

    # LLM responses often contain LaTeX with unescaped backslashes
    # (e.g. \frac, \sqrt, \text, \times) that are invalid JSON escapes.
    # Some collide with valid JSON escapes (\t = tab, \n = newline,
    # \r = CR, \f = form feed, \b = backspace) but in LLM output
    # these are almost always LaTeX commands (\text, \theta, \nabla,
    # \frac, \beta, etc.). We distinguish by checking if the escape
    # char is followed by a letter: \t + letter = LaTeX, \t + non-letter
    # = JSON tab. \f and \b are always treated as LaTeX since form feed
    # and backspace never appear in LLM text.
    # The first alternative (\\\\) consumes already-escaped backslash
    # pairs so they are kept as-is; the second alternative catches
    # lone backslashes that need escaping.
    fixed = re.sub(
        r'\\\\|(\\)(?!["\\/]|[nrt](?![a-zA-Z])|u[0-9a-fA-F]{4})',
        lambda m: '\\\\' if m.group(1) else m.group(),
        json_str,
    )
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        # Fall back to the original string in case our escaping broke it
        return json.loads(json_str)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def get_ai_chat_settings():

    assistant_settings = OPTIONS.get("Assistant", {})
    api_key = assistant_settings.get("AI_ASSISTANT_API_KEY", "")
    model = assistant_settings.get("AI_ASSISTANT_MODEL", "ollama/gemma3:12b")

    # Parse model format: provider/model-name
    if "/" in model:
        provider, model_name = model.split("/", 1)
    else:
        provider, model_name = "ollama", model

    if provider not in ("openai", "anthropic", "ollama", "litert") and not api_key:
        raise ValueError("AI_ASSISTANT_API_KEY not configured")

    if provider.lower() not in ["openai", "anthropic", "ollama", "litert"]:
        raise ValueError("Unsupported AI provider: {}".format(provider))

    return api_key, provider, model_name


# ---------------------------------------------------------------------------
# Inference server discovery
# ---------------------------------------------------------------------------

def _get_inference_server_url():
    """Read the local inference server URL from the PID file, or None."""
    try:
        with open(_AI_SERVER_PID_FILE) as f:
            data = json.load(f)
        url = data.get("url", "")
        pid = data.get("pid")
        # Quick sanity check: is the process still alive?
        if pid:
            os.kill(pid, 0)
        return url
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return None
    except OSError:
        # Process in PID file is not running
        return None


# ---------------------------------------------------------------------------
# Lightweight provider backends
# ---------------------------------------------------------------------------

def _openai_compatible_request(messages, model, api_key=None, base_url="https://api.openai.com", max_tokens=2000, temperature=0.1):
    """POST to an OpenAI-compatible /v1/chat/completions endpoint.

    Works for OpenAI, Ollama, and the local LiteRT inference server.
    """
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer {}".format(api_key)

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    url = "{}/v1/chat/completions".format(base_url.rstrip("/"))
    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _anthropic_request(messages, model, api_key, max_tokens=2000, temperature=0.1):
    """POST to the Anthropic /v1/messages endpoint."""
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    # Anthropic expects system as a top-level param, not in messages
    system_text = ""
    conversation = []
    for msg in messages:
        if msg["role"] == "system":
            system_text = msg["content"]
        else:
            conversation.append(msg)

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": conversation,
    }
    if system_text:
        payload["system"] = system_text

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        json=payload,
        headers=headers,
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    # Anthropic returns content as a list of blocks
    return "".join(block["text"] for block in data["content"] if block["type"] == "text")


# ---------------------------------------------------------------------------
# Unified query interface
# ---------------------------------------------------------------------------

def query_ai(prompt, system_prompt=None, parse_json=True, max_tokens=2000):
    api_key, provider, model_name = get_ai_chat_settings()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        if provider == "litert":
            server_url = _get_inference_server_url()
            if not server_url:
                return {"error": "AI inference server is not running. Start it with: kolibri manage serve_ai_models"}
            response_text = _openai_compatible_request(
                messages, model_name, base_url=server_url, max_tokens=max_tokens,
            )

        elif provider == "openai":
            response_text = _openai_compatible_request(
                messages, model_name, api_key=api_key, max_tokens=max_tokens,
            )

        elif provider == "ollama":
            response_text = _openai_compatible_request(
                messages, model_name, base_url="http://localhost:11434", max_tokens=max_tokens,
            )

        elif provider == "anthropic":
            response_text = _anthropic_request(
                messages, model_name, api_key=api_key, max_tokens=max_tokens,
            )

        else:
            return {"error": "Unsupported provider: {}".format(provider)}

    except requests.RequestException:
        logger.exception("HTTP request to %s provider failed", provider)
        return {"error": "Failed to reach the AI service"}
    except Exception:
        logger.exception("Unexpected error querying %s provider", provider)
        return {"error": "AI query failed"}

    if parse_json:
        try:
            return robust_json_parser(response_text)
        except json.JSONDecodeError:
            logger.exception("Failed to parse AI response as JSON. raw_content=%r", response_text)
            return {"error": "Failed to parse AI response"}
        except Exception:
            logger.exception("Unexpected error parsing AI response. raw_content=%r", response_text)
            return {"error": "Failed to parse AI response"}

    return response_text


# ---------------------------------------------------------------------------
# RAG pipeline (via inference server)
# ---------------------------------------------------------------------------

def _rag_pipeline(query, overrides=None, queryset=None):
    """Call the RAG pipeline, returning the full pipeline result dict or None.

    Args:
        query: the user's search query string.
        overrides: optional dict of pipeline config overrides
            (enrich, score, synthesize, top_docs, sub_chunks).
        queryset: optional base ContentNode queryset for keyword search.

    Returns:
        dict with content_ids, messages, results, enriched_queries,
        query_type, activity_filter, stages_run, timing.
        Or None if the inference server is unavailable.
    """
    server_url = _get_inference_server_url()
    if not server_url:
        return None

    from .rag_pipeline import run_pipeline
    return run_pipeline(query, server_url, overrides=overrides, queryset=queryset)
