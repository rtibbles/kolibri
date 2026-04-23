# flake8: noqa: E501
import json
import logging
import operator
from functools import reduce

from django.db import models

from kolibri.core.content.api import ContentNodeSearchFilter
from kolibri.core.content.api import ContentNodeViewset

from .llm import _rag_search
from .llm import get_ai_chat_settings  # noqa: F401 – re-exported for kolibri_plugin
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

        user_prompt = load_prompt("rag_user.txt").format(
            question=message,
            context=context_text,
        )

        response_text = query_ai(
            prompt=user_prompt,
            system_prompt=load_prompt("rag_system.txt"),
            parse_json=False,
        )

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
