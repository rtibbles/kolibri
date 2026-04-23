"""Multi-stage RAG pipeline orchestration.

Runs in the Kolibri process. Calls the inference server for embedding
search and LLM completions, uses Django ORM for content filtering.
"""
import json
import logging
import time

from kolibri.utils.conf import OPTIONS

from .llm import _get_inference_server_url
from .llm import load_prompt
from .llm import query_ai


logger = logging.getLogger(__name__)


def _get_pipeline_config(overrides=None):
    """Read pipeline config from OPTIONS, with optional per-request overrides."""
    settings = OPTIONS.get("Assistant", {})
    config = {
        "enrich": settings.get("AI_ASSISTANT_RAG_QUERY_ENRICHMENT", True),
        "score": settings.get("AI_ASSISTANT_RAG_LLM_SCORING", True),
        "synthesize": settings.get("AI_ASSISTANT_RAG_SYNTHESIS", True),
        "hard_min": settings.get("AI_ASSISTANT_RAG_SCORE_HARD_MIN", 3),
        "ideal_min": settings.get("AI_ASSISTANT_RAG_SCORE_IDEAL_MIN", 4),
    }
    if overrides:
        for key in ("enrich", "score", "synthesize"):
            if key in overrides:
                val = overrides[key]
                if isinstance(val, str):
                    config[key] = val not in ("0", "false", "False")
                else:
                    config[key] = bool(val)
        for key in ("hard_min", "ideal_min"):
            if key in overrides:
                try:
                    config[key] = int(overrides[key])
                except (ValueError, TypeError):
                    pass
    return config


def _parse_enriched_queries(raw_text, original_query):
    """Parse newline-delimited enriched queries from LLM output.

    Returns the original query as a singleton list on failure.
    """
    if not raw_text or not raw_text.strip():
        logger.warning("Query enrichment returned empty output, falling back to original query")
        return [original_query]
    queries = [line.strip() for line in raw_text.strip().split("\n") if line.strip()]
    if not queries:
        logger.warning("Query enrichment parsed to zero queries from: %r", raw_text)
        return [original_query]
    return queries


def _parse_scores(raw_text, results, hard_min):
    """Parse tab-separated scoring output from LLM.

    Returns list of results with 'score' and 'context_note' added,
    or None if the entire output is unparseable.
    """
    if not raw_text or not raw_text.strip():
        logger.warning("LLM scoring returned empty output")
        return None

    lines = [line for line in raw_text.strip().split("\n") if line.strip()]
    scored = []
    for i, result in enumerate(results):
        r = dict(result)
        if i < len(lines):
            parts = lines[i].rsplit("\t", 1)
            if len(parts) == 2:
                context_note = parts[0].strip()
                try:
                    score = max(1, min(5, int(parts[1].strip())))
                    r["score"] = score
                    r["context_note"] = context_note
                    scored.append(r)
                    continue
                except ValueError:
                    logger.warning("Non-integer score in line %d: %r", i, lines[i])
            else:
                logger.warning("Missing tab separator in score line %d: %r", i, lines[i])
        # Fallback for missing/malformed lines
        r["score"] = hard_min
        r["context_note"] = ""
        scored.append(r)
    return scored


def _threshold_filter(results, hard_min, ideal_min):
    """Apply two-tier, per-query threshold filtering on scored results.

    hard_min is global: always remove results below it.
    ideal_min is per-query: for each query's results, if any result from
    that query meets ideal_min, also remove that query's results below it.
    """
    # First pass: remove below hard_min globally
    results = [r for r in results if r.get("score", 0) >= hard_min]

    # Group by best_query_index for per-query ideal_min
    by_query = {}
    for r in results:
        qi = r.get("best_query_index", 0)
        by_query.setdefault(qi, []).append(r)

    # Per-query: apply ideal_min only if any result in that query meets it
    filtered = []
    for qi, query_results in sorted(by_query.items()):
        if any(r.get("score", 0) >= ideal_min for r in query_results):
            filtered.extend(r for r in query_results if r.get("score", 0) >= ideal_min)
        else:
            filtered.extend(query_results)

    # Sort by score descending
    filtered.sort(key=lambda r: r.get("score", 0), reverse=True)
    return filtered


def _select_results(candidates, available_cids, top_docs):
    """Select top_docs results with guaranteed-per-query representation.

    Args:
        candidates: list of dicts from RAG search, each with query_index,
            content_id, score, context.
        available_cids: set of content_ids that are available and non-coach.
        top_docs: max number of results to return.

    Returns:
        list of selected result dicts, each with best_query_index added.
    """
    # Filter to available content only
    candidates = [c for c in candidates if c["content_id"] in available_cids]

    # Group by query_index, sorted by score descending within each query
    queries = {}
    for c in candidates:
        qi = c["query_index"]
        queries.setdefault(qi, []).append(c)
    for qi in queries:
        queries[qi].sort(key=lambda r: r["score"], reverse=True)

    selected = {}  # content_id -> result dict (with best_query_index)
    reserved_cids = set()

    # Phase 1: guaranteed slot per query
    for qi in sorted(queries.keys()):
        if len(reserved_cids) >= top_docs:
            break
        for c in queries[qi]:
            if c["content_id"] not in reserved_cids:
                entry = dict(c)
                entry["best_query_index"] = qi
                selected[c["content_id"]] = entry
                reserved_cids.add(c["content_id"])
                break

    # Track best_query_index across all candidates for docs not yet selected
    best_scores = {}  # content_id -> (score, query_index, candidate)
    for c in candidates:
        cid = c["content_id"]
        if cid in reserved_cids:
            # Update best_query_index if this query has higher score
            if c["score"] > selected[cid].get("score", 0):
                selected[cid]["best_query_index"] = c["query_index"]
                selected[cid]["score"] = c["score"]
                selected[cid]["context"] = c["context"]
            continue
        if cid not in best_scores or c["score"] > best_scores[cid][0]:
            best_scores[cid] = (c["score"], c["query_index"], c)

    # Phase 2: fill remaining slots by best score
    remaining = sorted(best_scores.values(), key=lambda x: x[0], reverse=True)
    for score, qi, c in remaining:
        if len(selected) >= top_docs:
            break
        if c["content_id"] not in selected:
            entry = dict(c)
            entry["best_query_index"] = qi
            selected[c["content_id"]] = entry

    # Return in score-descending order
    result_list = sorted(selected.values(), key=lambda r: r["score"], reverse=True)
    return result_list


def _rag_search(queries, server_url, top_docs, sub_chunks):
    """Call the inference server's RAG search endpoint."""
    import requests

    resp = requests.post(
        "{}/v1/rag/search".format(server_url.rstrip("/")),
        json={"queries": queries, "top_docs": top_docs, "sub_chunks": sub_chunks},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def run_pipeline(query, server_url, overrides=None):
    """Run the multi-stage RAG pipeline.

    Args:
        query: the user's raw search query.
        server_url: base URL of the inference server.
        overrides: optional dict of config overrides.

    Returns:
        dict with content_ids, messages, results, enriched_queries,
        stages_run, timing.
    """
    from kolibri.core.content.models import ContentNode

    config = _get_pipeline_config(overrides)
    timing = {}
    stages_run = []
    t_total = time.perf_counter()

    top_docs = int((overrides or {}).get("top_docs", 6))
    sub_chunks = int((overrides or {}).get("sub_chunks", 2))

    # ---- Stage 1: Query Enrichment ----
    if config["enrich"]:
        t0 = time.perf_counter()
        stages_run.append("enrich")
        enrich_response = query_ai(
            prompt=query,
            system_prompt=load_prompt("enrich_system.txt"),
            parse_json=False,
            max_tokens=64,
        )
        enriched_queries = _parse_enriched_queries(enrich_response, query)
        timing["enrich_ms"] = round((time.perf_counter() - t0) * 1000)
        logger.info(
            "Pipeline enrich (%dms): %r -> %s",
            timing["enrich_ms"], query, enriched_queries,
        )
    else:
        enriched_queries = [query]

    # ---- Stage 2: Embedding Search ----
    t0 = time.perf_counter()
    stages_run.append("search")
    # Over-sample to have enough candidates after DB filtering
    oversample = top_docs * 3
    try:
        candidates = _rag_search(enriched_queries, server_url, oversample, sub_chunks)
    except Exception:
        logger.exception("RAG search request failed")
        return {
            "content_ids": [],
            "messages": ["I couldn't search for resources right now."],
            "results": [],
            "enriched_queries": enriched_queries,
            "stages_run": stages_run,
            "timing": timing,
        }
    timing["search_ms"] = round((time.perf_counter() - t0) * 1000)
    logger.info("Pipeline search (%dms): %d candidates", timing["search_ms"], len(candidates))

    # ---- Stage 3: DB Filter + Selection ----
    t0 = time.perf_counter()
    stages_run.append("db_filter")
    candidate_cids = list({c["content_id"] for c in candidates})
    available_info = {
        row["content_id"]: row
        for row in ContentNode.objects.filter(content_id__in=candidate_cids)
        .exclude(coach_content=True)
        .filter(available=True)
        .values("content_id", "title", "kind")
    }
    selected = _select_results(candidates, set(available_info.keys()), top_docs)

    # Enrich with DB metadata
    for r in selected:
        info = available_info.get(r["content_id"], {})
        r["title"] = info.get("title", "")
        r["kind"] = info.get("kind", "")

    timing["db_filter_ms"] = round((time.perf_counter() - t0) * 1000)
    logger.info(
        "Pipeline db_filter (%dms): %d available of %d candidates, %d selected",
        timing["db_filter_ms"], len(available_info), len(candidate_cids), len(selected),
    )

    if not selected:
        timing["total_ms"] = round((time.perf_counter() - t_total) * 1000)
        return {
            "content_ids": [],
            "messages": ["I couldn't find any relevant resources for your question."],
            "results": [],
            "enriched_queries": enriched_queries,
            "stages_run": stages_run,
            "timing": timing,
        }

    # ---- Stage 4: LLM Scoring ----
    if config["score"]:
        t0 = time.perf_counter()
        stages_run.append("score")

        resources_text = "\n".join(
            "{i}. [{kind}] {title}\n   {excerpt}".format(
                i=i + 1,
                kind=r.get("kind", ""),
                title=r.get("title", ""),
                excerpt=r.get("context", "")[:500],
            )
            for i, r in enumerate(selected)
        )
        score_prompt = load_prompt("score_user.txt").format(
            query=query,
            enriched_queries="\n".join("- " + q for q in enriched_queries),
            resources=resources_text,
        )
        score_response = query_ai(
            prompt=score_prompt,
            system_prompt=load_prompt("score_system.txt"),
            parse_json=False,
            max_tokens=256,
        )
        scored = _parse_scores(score_response, selected, config["hard_min"])
        if scored is not None:
            selected = scored
        else:
            logger.warning("Scoring parse failed entirely; keeping results unscored")

        timing["score_ms"] = round((time.perf_counter() - t0) * 1000)
        logger.info(
            "Pipeline score (%dms): %s",
            timing["score_ms"],
            ", ".join("{t}={s}".format(t=r.get("title", "?")[:20], s=r.get("score", "?")) for r in selected),
        )

    # ---- Stage 5: Threshold Filter ----
    if config["score"]:
        stages_run.append("threshold")
        before_count = len(selected)
        selected = _threshold_filter(selected, config["hard_min"], config["ideal_min"])
        logger.info("Pipeline threshold: %d -> %d results", before_count, len(selected))

    if not selected:
        timing["total_ms"] = round((time.perf_counter() - t_total) * 1000)
        return {
            "content_ids": [],
            "messages": ["I couldn't find any relevant resources for your question."],
            "results": [],
            "enriched_queries": enriched_queries,
            "stages_run": stages_run,
            "timing": timing,
        }

    # ---- Stage 6: Synthesis ----
    messages = []
    if config["synthesize"]:
        t0 = time.perf_counter()
        stages_run.append("synthesize")

        context_items = []
        for r in selected:
            item = {"title": r.get("title", ""), "kind": r.get("kind", "")}
            if r.get("context_note"):
                item["relevance"] = r["context_note"]
            if r.get("context"):
                item["excerpt"] = r["context"][:300]
            context_items.append(item)

        synth_prompt = load_prompt("rag_user.txt").format(
            question=query,
            context=json.dumps(context_items, indent=2),
        )
        synth_response = query_ai(
            prompt=synth_prompt,
            system_prompt=load_prompt("rag_system.txt"),
            parse_json=False,
            max_tokens=256,
        )
        if synth_response and synth_response.strip():
            messages.append(synth_response.strip())
        else:
            logger.warning("Synthesis returned empty output")

        timing["synthesize_ms"] = round((time.perf_counter() - t0) * 1000)
        logger.info("Pipeline synthesize (%dms): %d chars", timing["synthesize_ms"], len(messages[0]) if messages else 0)

    timing["total_ms"] = round((time.perf_counter() - t_total) * 1000)
    logger.info(
        "Pipeline complete (%dms): %d results, stages=%s, timing=%s",
        timing["total_ms"], len(selected), stages_run, timing,
    )

    return {
        "content_ids": [r["content_id"] for r in selected],
        "messages": messages,
        "results": selected,
        "enriched_queries": enriched_queries,
        "stages_run": stages_run,
        "timing": timing,
    }
