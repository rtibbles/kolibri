# flake8: noqa: E501
import json
import logging
import operator
from functools import reduce

from django.db import models

from kolibri.core.content.api import ContentNodeSearchFilter
from kolibri.core.content.api import ContentNodeViewset

from .llm import _rag_pipeline
from .llm import get_ai_chat_settings  # noqa: F401 – re-exported for kolibri_plugin
from .llm import _get_inference_server_url
from .llm import load_prompt
from .llm import query_ai


logger = logging.getLogger(__name__)

# Create instance for serialize_list usage
contentnode_viewset = ContentNodeViewset()


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
        message = request.query_params.get("question", "")

        if not message:
            return super().filter_queryset(request, queryset, view)

        if _get_inference_server_url():
            return self._filter_with_rag(request, queryset, message)
        else:
            return self._filter_with_keywords(request, queryset, view, message)

    def _filter_with_rag(self, request, queryset, message):
        """RAG pipeline search: enrichment, scoring, filtering, synthesis."""

        # Collect per-request overrides from query params
        overrides = {}
        for key in ("enrich", "score", "synthesize", "top_docs", "sub_chunks"):
            val = request.query_params.get(key)
            if val is not None:
                overrides[key] = val

        pipeline_result = _rag_pipeline(message, overrides=overrides, queryset=queryset)

        if pipeline_result is None:
            logger.warning("RAG pipeline unavailable, falling back to keyword search")
            return queryset.none()

        content_ids = pipeline_result.get("content_ids", [])
        messages = pipeline_result.get("messages", [])
        timing = pipeline_result.get("timing", {})

        logger.info(
            "RAG pipeline: %d results, timing=%s",
            len(content_ids), timing,
        )

        setattr(request, "messages", messages)

        if not content_ids:
            return queryset.none()

        # Use a subquery to pick one node per content_id, avoiding
        # duplicates when the same content exists in multiple channels.
        from django.db.models import Case
        from django.db.models import IntegerField
        from django.db.models import Min
        from django.db.models import When

        deduped_pks = (
            queryset.filter(content_id__in=content_ids)
            .values("content_id")
            .annotate(pk=Min("id"))
            .values_list("pk", flat=True)
        )

        # Preserve pipeline result ordering (keyword results first,
        # then embedding supplements; or score-ranked for complex path)
        ordering = Case(
            *[When(content_id=cid, then=pos) for pos, cid in enumerate(content_ids)],
            default=len(content_ids),
            output_field=IntegerField(),
        )
        return queryset.filter(id__in=deduped_pks).annotate(
            _pipeline_order=ordering
        ).order_by("_pipeline_order")

    def _filter_with_keywords(self, request, queryset, view, message):
        """Fallback: keyword-based search with two LLM calls (original flow)."""
        search_fields = self.get_search_fields(view, request)

        initial_response = query_ai(
            prompt=message
            + "\n\nBe sure to return your response as a JSON object with the structure shown above.",
            system_prompt=load_prompt("fallback_system.txt"),
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

        prompt = load_prompt("search_results_user.txt").format(
            message=message,
            original_response=initial_response.get("response", ""),
            resources=json.dumps(candidate_content_minimal, indent=2),
        )
        try:
            result = query_ai(prompt=prompt, system_prompt=load_prompt("search_results_system.txt"))
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
