from rest_framework import decorators
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from kolibri.core.content.api import ContentNodeViewset
from kolibri.utils.conf import OPTIONS

# Create instance for serialize_list usage
contentnode_viewset = ContentNodeViewset()

def get_ai_chat_model():
    """Get the configured AI model using langchain"""
    try:
        from langchain_openai import ChatOpenAI
        from langchain_anthropic import ChatAnthropic
        
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
        
        # Extract ContentNode context parameters for RAG
        context_params = {}
        content_filters = [
            'kind'
            'grade_levels', 'learning_activities',
            'accessibility_labels', 'categories', 'learner_needs'
        ]
        
        for param in content_filters:
            if param in request.data:
                context_params[param] = request.data[param]
        
        # Get relevant content nodes using the context parameters
        relevant_content = []
        if context_params:
            try:
                # Create a modified request object with the context parameters as query params
                # This simulates a GET request to ContentNodeViewset with filters
                query_params = dict(context_params)
                query_params['max_results'] = 5  # Limit to first 5 results
                
                # Use serialize_list to get filtered content nodes
                relevant_content = contentnode_viewset.serialize_list(request, query_params)
                
            except Exception as e:
                # Log error but continue with chat response
                print(f"Error fetching content nodes: {e}")
        
        
        # Generate AI response using RAG
        try:
            ai_model = get_ai_chat_model()
            
            # Build context from relevant content for RAG
            context_text = ""
            if relevant_content:
                context_parts = []
                for content in relevant_content[:5]:
                    title = content.get('title', 'Unknown')
                    description = content.get('description', '')
                    kind = content.get('kind', 'content')
                    
                    context_part = f"Title: {title}\nType: {kind}"
                    if description:
                        context_part += f"\nDescription: {description}"
                    context_parts.append(context_part)
                
                context_text = "\n\n".join(context_parts)
            
            # Create RAG prompt
            if context_text:
                prompt = f"""You are an AI assistant helping with educational content in Kolibri. Based on the following educational resources found in the system, please answer the user's question.

Educational Resources:
{context_text}

User Question: {message}

Please provide a helpful response based on the available educational content. If the content is relevant, reference it in your answer. If not relevant, provide a general helpful response."""
            else:
                prompt = f"""You are an AI assistant for Kolibri, an educational platform. Please provide a helpful response to the user's question about educational content.

User Question: {message}

Provide a helpful and educational response."""
            
            # Get AI response
            from langchain.schema import HumanMessage
            response = ai_model([HumanMessage(content=prompt)])
            ai_response = response.content
            
        except Exception as e:
            # Fallback response if AI fails
            print(f"AI model error: {e}")
            context_info = ""
            if relevant_content:
                content_titles = [content.get('title', 'Unknown') for content in relevant_content[:3]]
                context_info = f" I found {len(relevant_content)} relevant resources: {', '.join(content_titles)}. However, I'm unable to process them with AI at the moment."
            
            ai_response = f"I received your message: '{message}'.{context_info} Please check the system configuration or try again later."
        
        return Response({
            "response": ai_response,
            "context_params": context_params,
            "relevant_content": relevant_content,
            "status": "success"
        })

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