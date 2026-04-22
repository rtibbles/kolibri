# flake8: noqa: E501
import json
import logging
import operator
import os
import re
from functools import reduce

import requests
from django.db import models

from kolibri.core.content.api import ContentNodeSearchFilter
from kolibri.core.content.api import ContentNodeViewset
from kolibri.utils.conf import KOLIBRI_HOME
from kolibri.utils.conf import OPTIONS


logger = logging.getLogger(__name__)

# Create instance for serialize_list usage
contentnode_viewset = ContentNodeViewset()

# PID file written by the ``serve_ai_models`` management command.
_AI_SERVER_PID_FILE = os.path.join(KOLIBRI_HOME, "ai_server.json")


# ---------------------------------------------------------------------------
# Utilities
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

def query_ai(prompt, system_prompt=None, parse_json=True):
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
                messages, model_name, base_url=server_url,
            )

        elif provider == "openai":
            response_text = _openai_compatible_request(
                messages, model_name, api_key=api_key,
            )

        elif provider == "ollama":
            response_text = _openai_compatible_request(
                messages, model_name, base_url="http://localhost:11434",
            )

        elif provider == "anthropic":
            response_text = _anthropic_request(
                messages, model_name, api_key=api_key,
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
# RAG search (via inference server)
# ---------------------------------------------------------------------------

def _rag_search(query, top_docs=5, sub_chunks=2):
    """Call the inference server's RAG search endpoint.

    Returns a list of result dicts, or None if the server is unavailable.
    """
    server_url = _get_inference_server_url()
    if not server_url:
        return None

    try:
        resp = requests.post(
            "{}/v1/rag/search".format(server_url.rstrip("/")),
            json={"query": query, "top_docs": top_docs, "sub_chunks": sub_chunks},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("results", [])
    except requests.RequestException:
        logger.exception("RAG search request failed")
        return None


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

RAG_SYSTEM_PROMPT = """You are "Kolippy", a helpful AI assistant for Kolibri, an offline educational platform for K-12 students.

You will receive the student's question or search terms along with relevant excerpts from educational resources available on this device. Use these excerpts to give a clear, accurate, and concise answer.

Guidelines:
- Answer in plain language appropriate for the student's level.
- Use LaTeX notation (e.g. $y = mx + b$) for any mathematical expressions.
- Keep your response to one short paragraph (2-4 sentences).
- Base your answer on the provided resources. If the resources are helpful, use them. If they are not relevant or insufficient, answer from your own knowledge but note that you are less certain.
- Do NOT mention "the context", "the excerpts", or "the passage". You can refer to the resources by title, however, where appropriate.
- If you do not have enough information to answer or are not confident, say so honestly.
- Briefly mention how the resources shown, if any, may help them learn more about the topic.

Respond in raw JSON (no markdown, no backticks):
{
    "response": "Your answer to the student."
}""".strip()

RAG_USER_PROMPT_TEMPLATE = """Student's query: {question}

Relevant resources found on this device:
{context}

Answer the question using the resources above. Respond as JSON.""".strip()

FALLBACK_SYSTEM_PROMPT = """You are "Kolippy", an AI assistant for Kolibri, an offline educational platform preloaded with educational content.
Your role is to assist users with questions about educational content, provide brief explanations, and help them find the most relevant resources.
You should keep your responses concise, informative, max one paragraph, and focused on educational content. Use LaTeX notation (e.g. $y = mx + b$) for any mathematical expressions. Along with answering the question,
you can provide a list of up to 5 simple search terms (as minimalist as possible, e.g. each a single word or simple term, as Kolibri's search is very strict)
that we will use to find potentially relevant learning resources in Kolibri. Do not mention anything about Kolibri in your response.

If you are not certain of the answer, you MUST say "I don't know" or "I am not sure", but you should still provide search terms that might help find relevant resources.

Structure your response as follows:
{
    "response": "Your answer to the user's question",
    "search_terms": [
        "term1",
        "term2",
        "term3",
        "term4",
    ]
}""".strip()

SEARCH_RESULTS_SYSTEM_PROMPT = """You are an AI assistant for Kolibri, an offline educational platform preloaded with educational content.
The user has asked a question about educational content, and you provided an answer along with a list of search terms to find relevant resources.
Your task is to process the list of resources returned from the search, filter them down to the most relevant ones, order them from most to least
relevant, and provide a note referencing the resources found ("The resources below..."), or note if no relevant resources were found. Explanation
should be at most one sentence long, should be targeted to the user themselves (2nd person) and should not mention the ordering of the resources
or other meta-information.

Prioritize resources that contain similar keywords to the user's question, or are likely to contain information that would help answer the question.

The format of your response must be in raw JSON (no backticks etc), as follows:
{
    "content_intro": "Your brief intro to the discovered resources (they will be displayed as tiles below this message), or a note that no relevant resources were found.",
    "relevant_resources": ["<resource_index_1>", "<resource_index_2>", ...],
}
"""

SEARCH_RESULTS_PROMPT_TEMPLATE = """
The user's query was:
<message>{message}</message>

The original response you provided was:
<ai_response>{original_response}</ai_response>

And the following resources were found:
<candidate_content>{resources}</candidate_content>

Please filter these resources down to the most relevant ones, order them from most to least relevant, and adapt your response to reference the
resources found, or to note in your response if no relevant resources were found. Only include the list of indices of the resources in your response, not the full details.
"""


# ---------------------------------------------------------------------------
# Search filter
# ---------------------------------------------------------------------------

class LLMContentNodeSearchFilter(ContentNodeSearchFilter):
    _search_terms = None

    def get_search_terms(self, request):
        if self._search_terms:
            return self._search_terms
        return super().get_search_terms(request)

    def filter_queryset(self, request, queryset, view):
        message = self.get_cleaned_search_value(request)

        if not message:
            return super().filter_queryset(request, queryset, view)

        rag_results = _rag_search(message)
        if rag_results is not None:
            return self._filter_with_rag(request, queryset, message, rag_results)
        else:
            return self._filter_with_keywords(request, queryset, view, message)

    def _filter_with_rag(self, request, queryset, message, rag_results):
        """RAG-based search: use pre-fetched results, ask LLM with context."""

        logger.info(
            "RAG search returned %d results: %s",
            len(rag_results),
            ", ".join(
                "{cid} (score={score})".format(cid=r["content_id"][:8], score=r["score"])
                for r in rag_results
            ),
        )

        if not rag_results:
            logger.info("RAG search found no results for query: %r", message)
            setattr(request, "messages", ["I couldn't find any relevant resources for your question."])
            return queryset.none()

        # Filter RAG results to only content that is available and non-coach,
        # and enrich with title/kind from the DB (not stored in RAG metadata).
        all_content_ids = [r["content_id"] for r in rag_results]
        content_info = {
            row["content_id"]: row
            for row in queryset.filter(content_id__in=all_content_ids)
            .exclude(coach_content=True)
            .values("content_id", "title", "kind")
        }
        for r in rag_results:
            info = content_info.get(r["content_id"])
            if info:
                r["title"] = info["title"]
                r["kind"] = info["kind"]
        rag_results = [r for r in rag_results if r["content_id"] in content_info]
        logger.info("RAG results after availability filter: %d of %d", len(rag_results), len(all_content_ids))

        if not rag_results:
            setattr(request, "messages", ["I couldn't find any relevant resources for your question."])
            return queryset.none()

        # Build context from filtered results, staying within token budget
        max_context_chars = 7500
        context_items = []
        context_chars = 0
        for result in rag_results:
            item = {
                "title": result.get("title", ""),
                "kind": result.get("kind", ""),
                "excerpt": result.get("context", ""),
            }
            item_chars = len(item["title"]) + len(item["kind"]) + len(item["excerpt"])
            if context_chars + item_chars > max_context_chars and context_items:
                break
            context_items.append(item)
            context_chars += item_chars

        context_text = json.dumps(context_items, indent=2)
        logger.info("RAG assembled context from %d of %d resources (%d chars)", len(context_items), len(rag_results), len(context_text))

        user_prompt = RAG_USER_PROMPT_TEMPLATE.format(
            question=message,
            context=context_text,
        )

        ai_response = query_ai(
            prompt=user_prompt,
            system_prompt=RAG_SYSTEM_PROMPT,
        )

        response_text = ""
        if isinstance(ai_response, dict):
            response_text = ai_response.get("response", "")
        if not response_text and isinstance(ai_response, dict):
            response_text = ai_response.get("error", "Sorry, I could not generate a response.")

        logger.info("RAG LLM response (%d chars): %r", len(response_text), response_text[:300])

        messages = []
        if response_text:
            messages.append(response_text)
        setattr(request, "messages", messages)

        content_ids = [r["content_id"] for r in rag_results]
        filtered = queryset.filter(content_id__in=content_ids).exclude(coach_content=True).distinct()
        logger.info("RAG returning %d content nodes for query: %r", filtered.count(), message)

        return filtered

    def _filter_with_keywords(self, request, queryset, view, message):
        """Fallback: keyword-based search with two LLM calls (original flow)."""
        search_fields = self.get_search_fields(view, request)

        initial_response = query_ai(
            prompt=message
            + "\n\nBe sure to return your response as a JSON object with the structure shown above.",
            system_prompt=FALLBACK_SYSTEM_PROMPT,
        )

        logger.debug(initial_response)

        search_terms = (
            initial_response.get("search_terms", []) if initial_response else None
        )

        if not search_terms:
            logger.warning(
                "No search terms returned by AI, falling back to default search"
            )
            return super().filter_queryset(request, queryset, view)

        orm_lookups = [
            self.construct_search(str(search_field)) for search_field in search_fields
        ]

        candidate_content_list = []
        for keyword in search_terms:
            if not isinstance(keyword, str):
                raise Exception(r"Error: Invalid search term format: {keyword}")

            query = reduce(
                operator.or_,
                (models.Q(**{orm_lookup: keyword}) for orm_lookup in orm_lookups),
            )

            new_candidates = queryset.filter(query).exclude(kind="topic").exclude(coach_content=True).values()[:5]

            candidate_content_list.extend(new_candidates)

        candidate_content = {
            node["content_id"][:6]: node for node in candidate_content_list
        }

        candidate_content_minimal = [
            {"id": node["content_id"][:6], "title": node["title"], "description": node["description"][:350], "kind": node["kind"]}
            for node in candidate_content.values()
        ]

        prompt = SEARCH_RESULTS_PROMPT_TEMPLATE.format(
            message=message,
            original_response=initial_response.get("response", ""),
            resources=json.dumps(candidate_content_minimal, indent=2),
        )
        try:
            result = query_ai(prompt=prompt, system_prompt=SEARCH_RESULTS_SYSTEM_PROMPT)
            content_intro = result.get("content_intro", "")
            relevant_content_ids = result.get("relevant_resources", [])
        except Exception as e:
            raise Exception("Error: AI processing failed: {}".format(str(e)))

        relevant_content = []
        for content_id in relevant_content_ids:
            if content_id in candidate_content:
                relevant_content.append(candidate_content[content_id])

        messages = []
        if initial_response.get("response"):
            messages.append(initial_response.get("response"))

        if content_intro:
            messages.append(content_intro)

        setattr(request, "messages", messages)

        full_content_ids = [node["content_id"] for node in relevant_content]

        if not relevant_content:
            return queryset.none()
        else:
            return queryset.filter(content_id__in=full_content_ids).distinct()
