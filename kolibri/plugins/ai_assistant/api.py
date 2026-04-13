# flake8: noqa: E501
import json
import logging
import operator
from functools import reduce

from django.db import models
from langchain.schema import HumanMessage
from langchain.schema import SystemMessage

from kolibri.core.content.api import ContentNodeSearchFilter
from kolibri.core.content.api import ContentNodeViewset
from kolibri.utils.conf import OPTIONS


logger = logging.getLogger(__name__)

# Singleton for LiteRT-LM engine (expensive to initialize)
_litert_engine = None
_litert_conversation = None

# Create instance for serialize_list usage
contentnode_viewset = ContentNodeViewset()


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

    return json.loads(json_str)


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
        raise ValueError(f"Unsupported AI provider: {provider}")

    return api_key, provider, model_name


def get_litert_engine():
    """Get or create the singleton LiteRT-LM engine with GPU backend."""
    global _litert_engine
    if _litert_engine is not None:
        return _litert_engine

    import litert_lm

    assistant_settings = OPTIONS.get("Assistant", {})
    model_path = assistant_settings.get("AI_ASSISTANT_MODEL_PATH", "")
    if not model_path:
        raise ValueError(
            "AI_ASSISTANT_MODEL_PATH must be set for the litert provider"
        )

    litert_lm.set_min_log_severity(litert_lm.LogSeverity.ERROR)
    _litert_engine = litert_lm.Engine(
        model_path,
        backend=litert_lm.Backend.GPU,
        cache_dir="/tmp/litert-lm-cache",
    )
    logger.info("LiteRT-LM engine initialized with GPU backend: %s", model_path)
    return _litert_engine


def query_litert(prompt, system_prompt=None, parse_json=True):
    """Query the LiteRT-LM engine directly."""
    engine = get_litert_engine()

    # System message goes in create_conversation; user prompt goes in send_message
    messages = []
    if system_prompt:
        messages.append(
            {"role": "system", "content": [{"type": "text", "text": system_prompt}]}
        )

    global _litert_conversation
    # Create a fresh conversation for each query to avoid context buildup
    if _litert_conversation is not None:
        try:
            _litert_conversation.__exit__(None, None, None)
        except Exception:
            pass
    _litert_conversation = engine.create_conversation(messages=messages)
    conversation = _litert_conversation.__enter__()

    response = conversation.send_message(prompt)
    response_text = response["content"][0]["text"]

    if parse_json:
        try:
            return robust_json_parser(response_text)
        except json.JSONDecodeError:
            logger.exception(
                "Failed to parse LiteRT response as JSON. raw_content=%r",
                response_text,
            )
            return {"error": "Failed to parse AI response"}
        except Exception:
            logger.exception(
                "Unexpected error parsing LiteRT response. raw_content=%r",
                response_text,
            )
            return {"error": "Failed to parse AI response"}
    return response_text


def get_ai_chat_model():
    """Get the configured AI model using langchain"""
    try:
        api_key, provider, model_name = get_ai_chat_settings()

        if provider.lower() == "litert":
            # LiteRT uses its own query path, not langchain
            return None

        # Create appropriate langchain model based on provider
        if provider.lower() == "openai":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(api_key=api_key, model=model_name, max_tokens=2000)

        elif provider.lower() == "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                api_key=api_key, model=model_name, temperature=0.1, max_tokens=2000
            )
        elif provider.lower() == "ollama":
            from langchain_ollama import ChatOllama

            return ChatOllama(model=model_name, temperature=0.1, max_tokens=1500)
    except ImportError as e:
        logger.exception("Required langchain packages missing for AI assistant")
        raise ImportError(f"Required langchain packages not installed: {e}") from e
    except Exception as e:
        logger.exception("Failed to initialize AI model")
        raise Exception(f"Failed to initialize AI model: {e}") from e


def query_ai(prompt, system_prompt=None, parse_json=True):
    _, provider, _ = get_ai_chat_settings()

    if provider.lower() == "litert":
        return query_litert(prompt, system_prompt=system_prompt, parse_json=parse_json)

    ai_model = get_ai_chat_model()
    messages = [HumanMessage(content=prompt)]
    if system_prompt:
        messages.insert(0, SystemMessage(content=system_prompt))
    response = ai_model.invoke(messages)
    if parse_json:
        try:
            return robust_json_parser(response.content)
        except json.JSONDecodeError as exc:
            logger.exception(
                "Failed to parse AI response as JSON. raw_content=%r", response.content
            )
            return {"error": "Failed to parse AI response"}
        except Exception:
            # Ensure unexpected parsing errors do not get swallowed silently.
            logger.exception(
                "Unexpected error while parsing AI response. raw_content=%r",
                response.content,
            )
            return {"error": "Failed to parse AI response"}
    return response.content


# ── RAG-aware prompts ────────────────────────────────────────────────────────

RAG_SYSTEM_PROMPT = """You are "Kolippy", a helpful AI assistant for Kolibri, an offline educational platform for K-12 students.

You will receive the student's question along with relevant excerpts from educational resources available on this device. Use these excerpts to give a clear, accurate, and concise answer.

Guidelines:
- Answer in plain language appropriate for the student's level.
- Keep your response to one short paragraph (2-4 sentences).
- Base your answer on the provided context. If the context is helpful, use it. If it is not relevant or insufficient, answer from your own knowledge but note that you are less certain.
- Do NOT mention "the context", "the excerpts", or "the passage". Just answer naturally.
- If you truly cannot answer, say so honestly.
- Briefly mention that the resources shown below may help them learn more about the topic.

Respond in raw JSON (no markdown, no backticks):
{
    "response": "Your answer to the student's question."
}""".strip()

RAG_USER_PROMPT_TEMPLATE = """Student's question: {question}

Relevant excerpts from learning resources on this device:
{context}

Answer the question using the excerpts above. Respond as JSON.""".strip()

# ── Fallback prompts (no RAG data available) ─────────────────────────────────

FALLBACK_SYSTEM_PROMPT = """You are "Kolippy", an AI assistant for Kolibri, an offline educational platform preloaded with educational content.
Your role is to assist users with questions about educational content, provide brief explanations, and help them find the most relevant resources.
You should keep your responses concise, informative, plaintext, max one paragraph, and focused on educational content. Along with answering the question,
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


# ── RAG index helpers ────────────────────────────────────────────────────────

def _get_rag_data_path():
    """Return configured RAG data path, or None if not set."""
    assistant_settings = OPTIONS.get("Assistant", {})
    path = assistant_settings.get("AI_ASSISTANT_RAG_DATA_PATH", "")
    return path if path else None


def _get_rag_index():
    """Get the singleton RAG index, or None if not configured."""
    data_path = _get_rag_data_path()
    if not data_path:
        return None
    try:
        from .rag import RAGIndex
        return RAGIndex.get(data_path)
    except Exception:
        logger.exception("Failed to load RAG index from %s", data_path)
        return None


# ── Search filter ────────────────────────────────────────────────────────────

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

        rag_index = _get_rag_index()
        if rag_index is not None:
            return self._filter_with_rag(request, queryset, message, rag_index)
        else:
            return self._filter_with_keywords(request, queryset, view, message)

    def _filter_with_rag(self, request, queryset, message, rag_index):
        """RAG-based search: embed query, find relevant docs, ask LLM with context."""

        # Step 1: Semantic search for relevant documents
        rag_results = rag_index.search(message, top_docs=5, sub_chunks=2)
        logger.debug("RAG results for %r: %s", message, [(r["content_id"][:8], r["score"]) for r in rag_results])

        if not rag_results:
            setattr(request, "messages", ["I couldn't find any relevant resources for your question."])
            return queryset.none()

        # Step 2: Build context from top results
        context_parts = []
        for i, result in enumerate(rag_results[:3], 1):
            if result["context"]:
                context_parts.append(
                    "Resource {n}:\n{ctx}".format(n=i, ctx=result["context"])
                )

        context_text = "\n\n".join(context_parts) if context_parts else "No relevant excerpts found."

        # Step 3: Single LLM call with RAG context
        user_prompt = RAG_USER_PROMPT_TEMPLATE.format(
            question=message,
            context=context_text,
        )

        ai_response = query_ai(
            prompt=user_prompt,
            system_prompt=RAG_SYSTEM_PROMPT,
        )

        # Extract response text
        response_text = ""
        if isinstance(ai_response, dict):
            response_text = ai_response.get("response", "")
        if not response_text and isinstance(ai_response, dict):
            response_text = ai_response.get("error", "Sorry, I could not generate a response.")

        logger.debug("RAG AI response: %s", response_text[:200])

        # Step 4: Set messages on request for frontend
        messages = []
        if response_text:
            messages.append(response_text)
        setattr(request, "messages", messages)

        # Step 5: Return queryset filtered to RAG result content_ids
        content_ids = [r["content_id"] for r in rag_results]
        filtered = queryset.filter(content_id__in=content_ids).distinct()

        if not filtered.exists():
            # Content might not be in this channel's queryset; return empty
            logger.warning(
                "RAG returned content_ids not in queryset: %s", content_ids[:3]
            )
            return queryset.none()

        return filtered

    def _filter_with_keywords(self, request, queryset, view, message):
        """Fallback: keyword-based search with two LLM calls (original flow)."""
        search_fields = self.get_search_fields(view, request)

        # Get the search terms from LLM
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

        # deduplicate content nodes by content_id
        candidate_content = {
            node["content_id"][:6]: node for node in candidate_content_list
        }

        candidate_content_minimal = [
            {"id": node["content_id"][:6], "title": node["title"], "description": node["description"][:350], "kind": node["kind"]}
            for node in candidate_content.values()
        ]

        # use AI to filter and rank content nodes
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
            raise Exception(f"Error: AI processing failed: {str(e)}")

        # filter the candidate content based on AI response
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
