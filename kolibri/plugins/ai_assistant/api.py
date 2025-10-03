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

# Best ollama models:
# - gemma3:12b
# - granite3.3:8b
# - mistral:7b

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

    if provider != "ollama" and not api_key:
        raise ValueError("AI_ASSISTANT_API_KEY not configured")

    if provider.lower() not in ["openai", "anthropic", "ollama"]:
        raise ValueError(f"Unsupported AI provider: {provider}")

    return api_key, provider, model_name


def get_ai_chat_model():
    """Get the configured AI model using langchain"""
    try:
        api_key, provider, model_name = get_ai_chat_settings()

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


HALLUCINATION_AVOIDANCE_SYSTEM_PROMPT = """
# ———— Hallucination Avoidance ————
For any question, you may only state facts you are fully confident in.
Before answering, check whether you have verifiable knowledge of the topic.
If you have any doubt—even a 1% chance you might be wrong—you must not attempt an answer.
Instead you must reply exactly in JSON as:

{
  "response": "I don't know",
  "search_terms": []
}

Do not add any other text or attempt to guess.
# ——————————————————————
"""

CONFIDENCE_GUARDRAIL_SYSTEM_PROMPT = """
# ———— Confidence Guardrail ————
Before you generate any factual claim, assess whether you can be fully confident (e.g. ≥90%) in its accuracy.
If you have any doubt or cannot verify it against your internal knowledge, you must reply exactly:
“I don’t know.”
Under no circumstances should you fabricate or guess. Lives depend on your accuracy. Always err on the side of caution.
# ——————————————————————
"""

INITIAL_SYSTEM_PROMPT = """
You are "Kolippy", an AI assistant for Kolibri, an offline educational platform preloaded with educational content.
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
}
""".strip()

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


def query_ai(prompt, system_prompt=None, parse_json=True):
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


class LLMContentNodeSearchFilter(ContentNodeSearchFilter):
    _search_terms = None

    def get_search_terms(self, request):
        if self._search_terms:
            return self._search_terms
        return super().get_search_terms(request)

    def filter_queryset(self, request, queryset, view):
        message = self.get_cleaned_search_value(request)
        search_fields = self.get_search_fields(view, request)
        
        if not message:
            return super().filter_queryset(request, queryset, view)

        # Get the search terms to use for RAG
        initial_response = query_ai(
            prompt=message
            + "\n\nBe sure to return your response as a JSON object with the structure shown above.",
            system_prompt=HALLUCINATION_AVOIDANCE_SYSTEM_PROMPT + INITIAL_SYSTEM_PROMPT,
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

            # Use serialize_list to get filtered content nodes
            candidate_content_list.extend(new_candidates)

        # deduplicate content nodes by content_id and build a dictionary for easy access
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
            # search_terms=", ".join(initial_response.get("search_terms", [])),
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

        # display debugging information to the console
        print("Initial AI response:", initial_response)
        print("Candidate content nodes:", candidate_content_minimal)
        print("Filtered relevant content IDs:", relevant_content_ids)

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