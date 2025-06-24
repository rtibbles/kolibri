from rest_framework import routers

from .api import AiAssistantViewSet

router = routers.SimpleRouter()

router.register(r"ai_assistant", AiAssistantViewSet, basename="ai_assistant")

urlpatterns = router.urls