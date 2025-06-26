import json

from rest_framework import decorators
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from kolibri.core.content.api import ContentNodeViewset
from kolibri.utils.conf import OPTIONS

from langchain.schema import SystemMessage
from langchain.schema import HumanMessage


# Create instance for serialize_list usage
contentnode_viewset = ContentNodeViewset()

# Best ollama models:
# - gemma3:12b
# - granite3.3:8b
# - mistral:7b

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
            return ChatOpenAI(
                api_key=api_key,
                model=model_name,
                temperature=0.9,
                max_tokens=1000
            )
        elif provider.lower() == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                api_key=api_key,
                model=model_name,
                temperature=0.9,
                max_tokens=1000
            )
        elif provider.lower() == "ollama":
            from langchain_ollama import ChatOllama
            return ChatOllama(
                model=model_name,
                temperature=0.9,
                max_tokens=1000
            )
    except ImportError as e:
        raise ImportError(f"Required langchain packages not installed: {e}")
    except Exception as e:
        raise Exception(f"Failed to initialize AI model: {e}")

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
    "relevant_resources": ["<resource_id_1>", "<resource_id_2>", ...],
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
            print("Failed to parse AI response as JSON:", response.content)
            return {"error": "Failed to parse AI response"}
    return response.content


class AiAssistantViewSet(ViewSet):
    """
    API endpoints for AI assistant functionality
    """

    # permission_classes = (IsAuthenticated,)

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
            prompt=message
            + "\n\nBe sure to return your response as a JSON object with the structure shown above.",
            system_prompt=HALLUCINATION_AVOIDANCE_SYSTEM_PROMPT + INITIAL_SYSTEM_PROMPT,
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
                node
                for node in new_candidates
                if isinstance(node, dict)
                and node["kind"] != "topic"
                and not node["coach_content"]
            ]

            # Use serialize_list to get filtered content nodes
            candidate_content_list.extend(new_candidates)

        # deduplicate content nodes by content_id and build a dictionary for easy access
        candidate_content = {
            node["content_id"][:10]: node for node in candidate_content_list
        }

        candidate_content_minimal = [
            {"id": node["content_id"][:10], "title": node["title"], "description": node["description"], "kind": node["kind"]}
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
            return Response({"error": f"AI processing failed: {str(e)}"}, status=500)

        # filter the candidate content based on AI response
        relevant_content = []
        for content_id in relevant_content_ids:
            if content_id in candidate_content:
                relevant_content.append(candidate_content[content_id])

        # display debugging information to the console
        print("Initial AI response:", initial_response)
        print("Candidate content nodes:", candidate_content_minimal)
        print("Filtered relevant content IDs:", relevant_content_ids)

        # include the initial informational AI response
        response = [
            {
                "response": initial_response.get("response", ""),
            }
        ]

        # if there are relevant content nodes, include and explain them in the response
        if relevant_content:
            response.append(
                {
                    "response": content_intro,
                    "relevant_content": relevant_content,
                }
            )

        return Response(response)

    @decorators.action(methods=["get"], detail=False)
    def status(self, request):
        """
        Check AI assistant status and configuration
        """
        _, provider, model_name = get_ai_chat_settings()
        return Response({
            "enabled": True,
            "provider": provider,
            "model": model_name,
            "status": "ready"
        })
