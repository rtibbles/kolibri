import json

from rest_framework import decorators
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from kolibri.core.content.api import ContentNodeViewset
from kolibri.utils.conf import OPTIONS

from langchain.schema import SystemMessage
from langchain.schema import HumanMessage
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic


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


def get_ai_chat_model():
    """Get the configured AI model using langchain"""
    try:
        
        assistant_settings = OPTIONS.get("Assistant", {})
        api_key = assistant_settings.get("AI_ASSISTANT_API_KEY", "")
        model = assistant_settings.get("AI_ASSISTANT_MODEL", "openai/gpt-4o-mini")
        
        if not api_key:
            raise ValueError("AI_ASSISTANT_API_KEY not configured")
        
        # Parse model format: provider/model-name
        if "/" in model:
            provider, model_name = model.split("/", 1)
        else:
            provider = "openai"
            model_name = model
        
        # Create appropriate langchain model based on provider
        if provider.lower() == "openai":
            return ChatOpenAI(
                api_key=api_key,
                model=model_name,
                temperature=0.7,
                max_tokens=1000
            )
        elif provider.lower() == "anthropic":
            return ChatAnthropic(
                api_key=api_key,
                model=model_name,
                temperature=0.7,
                max_tokens=1000
            )
        else:
            raise ValueError(f"Unsupported AI provider: {provider}")
            
    except ImportError as e:
        raise ImportError(f"Required langchain packages not installed: {e}")
    except Exception as e:
        raise Exception(f"Failed to initialize AI model: {e}")

INITIAL_SYSTEM_PROMPT = """You are an AI assistant for Kolibri, an offline educational platform preloaded with educational content.
Your role is to assist users with questions about educational content, provide brief explanations, and help them find the most relevant resources.
You should keep your responses concise, informative, plaintext, max one paragraph, and focused on educational content. Along with answering the question,
you can provide a list of up to 10 simple search terms (as minimalist as possible, e.g. each a single word or simple term, as Kolibri's search is very strict)
that we will use to find potentially relevant learning resources in Kolibri. Structure your response as follows:
{
    "response": "Your answer to the user's question",
    "search_terms": [
        "term1",
        "term2",
        "term3",
        "term4",
    ]
}
"""

SEARCH_RESULTS_SYSTEM_PROMPT = """You are an AI assistant for Kolibri, an offline educational platform preloaded with educational content.
The user has asked a question about educational content, and you provided an answer along with a list of search terms to find relevant resources.
Your task is to process the list of resources returned from the search, filter them down to the most relevant ones, order them from most to least
relevant, and provide a note referencing the resources found, or note if no relevant resources were found.
The format of your response should be as follows:
{
    "content_intro": "Your brief intro to the discovered resources (they will be displayed as tiles below this message), or a note that no relevant resources were found.",
    "relevant_resources": ["<resource_id_1>", "<resource_id_2>", ...],
}
"""

SEARCH_RESULTS_PROMPT_TEMPLATE = """
The original response you provided was:
{original_response}

The keywords you provided for searching were:
{search_terms}

And the following resources were found:
{resources}

Please filter these resources down to the most relevant ones, order them from most to least relevant, and adapt your response to reference the
resources found, or to note in your response if no relevant resources were found. Only include the IDs of the resources in your response, not the full details.
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
        except json.JSONDecodeError:
            return {"error": "Failed to parse AI response"}
    return response.content


class AiAssistantViewSet(ViewSet):
    """
    API endpoints for AI assistant functionality
    """

    permission_classes = (IsAuthenticated,)

    @decorators.action(methods=["post"], detail=False)
    def chat(self, request):
        """
        Handle AI chat interactions with optional ContentNode context parameters
        
        Accepts message and optional ContentNode filter parameters for RAG:
        - message: The user's chat message
        - kind: Filter by content kind (video, audio, document, etc.)
        - grade_levels: Filter by grade levels
        - learning_activities: Filter by learning activities
        - categories: Filter by categories
        """

        message = request.data.get("message", "")

        if not message:
            return Response({"error": "Message is required"}, status=400)

        # Get the search terms to use for RAG
        initial_response = query_ai(
            prompt=message,
            system_prompt=INITIAL_SYSTEM_PROMPT,
        )

        candidate_content_list = []
        for keyword in initial_response.get("search_terms", []):
            if not isinstance(keyword, str):
                return Response({"error": "Invalid search term format"}, status=400)            
            query_params = {
                "keywords": keyword,
                "max_results": 5,  # Limit to first 5 results
            }
            new_candidates = (
                contentnode_viewset.serialize_list(request, query_params) or {}
            ).get("results", [])

            new_candidates = [
                node for node in new_candidates if isinstance(node, dict) and node["kind"] != "topic"
            ]

            # Use serialize_list to get filtered content nodes
            candidate_content_list.extend(new_candidates)

        # deduplicate content nodes and build a dictionary for easy access
        candidate_content = {node["id"]: node for node in candidate_content_list}

        candidate_content_minimal = [
            {"id": node["id"], "title": node["title"], "description": node["description"]}
            for node in candidate_content.values()
        ]

        # use AI to filter and rank content nodes
        prompt = SEARCH_RESULTS_PROMPT_TEMPLATE.format(
            original_response=initial_response.get("response", ""),
            search_terms=", ".join(initial_response.get("search_terms", [])),
            resources=json.dumps(candidate_content_minimal, indent=2),
        )
        try:
            result = query_ai(prompt=prompt, system_prompt=SEARCH_RESULTS_SYSTEM_PROMPT)
            content_intro = result.get("content_intro", "")
            relevant_content_ids = result.get("relevant_resources", [])
        except Exception as e:
            return Response({"error": f"AI processing failed: {str(e)}"}, status=500)

        # filter the candidate content based on AI response
        relevant_content = []
        for content_id in relevant_content_ids:
            if content_id in candidate_content:
                relevant_content.append(candidate_content[content_id])

        return Response(
            [
                {
                    "response": initial_response.get("response", ""),
                },
                {
                    "response": content_intro,
                    "relevant_content": relevant_content,
                },
            ]
        )

    @decorators.action(methods=["get"], detail=False)
    def status(self, request):
        """
        Check AI assistant status and configuration
        """
        return Response({
            "enabled": True,
            "model": "claude-3-haiku-20240307",
            "status": "ready"
        })
