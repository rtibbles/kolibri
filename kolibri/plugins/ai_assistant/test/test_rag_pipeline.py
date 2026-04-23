"""Tests for the multi-stage RAG pipeline."""
import numpy as np
import pytest

from kolibri.plugins.ai_assistant.rag import RAGIndex


class FakeRAGIndex(RAGIndex):
    """RAGIndex with fake data, no ONNX model needed."""

    def __init__(self, docs, chunks_by_cid=None):
        dim = len(docs[0][1]) if docs else 8
        self.doc_embeddings = np.array(
            [d[1] for d in docs], dtype=np.float16
        )
        self.doc_metadata = [
            {"content_id": d[0], "node_id": d[0], "channel_id": "ch1"}
            for d in docs
        ]
        all_chunk_embs = []
        self.chunk_index = {}
        self.chunk_texts = {}
        offset = 0
        for cid, _ in docs:
            chunks = (chunks_by_cid or {}).get(cid, [])
            if chunks:
                self.chunk_index[cid] = {"offset": offset, "count": len(chunks)}
                self.chunk_texts[cid] = [c[0] for c in chunks]
                all_chunk_embs.extend([c[1] for c in chunks])
                offset += len(chunks)
        if all_chunk_embs:
            self.chunk_embeddings = np.array(all_chunk_embs, dtype=np.float16)
        else:
            self.chunk_embeddings = np.zeros((0, dim), dtype=np.float16)

    def embed(self, texts):
        raise NotImplementedError("FakeRAGIndex.embed() should not be called directly in tests")


def _make_index_with_embed(doc_vecs, query_vecs_by_text):
    idx = FakeRAGIndex(doc_vecs)
    def fake_embed(texts):
        vecs = []
        for t in texts:
            if t in query_vecs_by_text:
                vecs.append(query_vecs_by_text[t])
            else:
                raise ValueError("Unexpected text in embed: {!r}".format(t))
        result = np.array(vecs, dtype=np.float16)
        norms = np.linalg.norm(result, axis=1, keepdims=True).clip(min=1e-9)
        return (result / norms).astype(np.float16)
    idx.embed = fake_embed
    return idx


def _unit_vec(dim, index):
    v = np.zeros(dim, dtype=np.float32)
    v[index] = 1.0
    return v


class TestSearchBatch:

    def test_single_query_returns_ranked_results(self):
        dim = 4
        docs = [
            ("doc_a", _unit_vec(dim, 0)),
            ("doc_b", _unit_vec(dim, 1)),
            ("doc_c", _unit_vec(dim, 2)),
        ]
        query_vecs = {"q1": _unit_vec(dim, 0)}
        idx = _make_index_with_embed(docs, query_vecs)
        results = idx.search_batch(["q1"], top_docs=3, sub_chunks=0)
        assert len(results) == 3
        q0_results = [r for r in results if r["query_index"] == 0]
        assert len(q0_results) == 3
        assert q0_results[0]["content_id"] == "doc_a"
        assert q0_results[0]["score"] > q0_results[1]["score"]

    def test_multi_query_returns_per_query_results(self):
        dim = 4
        docs = [
            ("doc_a", _unit_vec(dim, 0)),
            ("doc_b", _unit_vec(dim, 1)),
            ("doc_c", _unit_vec(dim, 2)),
        ]
        query_vecs = {
            "q1": _unit_vec(dim, 0),
            "q2": _unit_vec(dim, 1),
        }
        idx = _make_index_with_embed(docs, query_vecs)
        results = idx.search_batch(["q1", "q2"], top_docs=2, sub_chunks=0)
        q0 = [r for r in results if r["query_index"] == 0]
        q1 = [r for r in results if r["query_index"] == 1]
        assert q0[0]["content_id"] == "doc_a"
        assert q1[0]["content_id"] == "doc_b"

    def test_batch_embed_called_once(self):
        dim = 4
        docs = [("doc_a", _unit_vec(dim, 0))]
        call_count = [0]
        query_vecs = {"q1": _unit_vec(dim, 0), "q2": _unit_vec(dim, 1)}
        idx = _make_index_with_embed(docs, query_vecs)
        original_embed = idx.embed
        def counting_embed(texts):
            call_count[0] += 1
            return original_embed(texts)
        idx.embed = counting_embed
        idx.search_batch(["q1", "q2"], top_docs=1, sub_chunks=0)
        assert call_count[0] == 1, "embed() should be called exactly once for batch"


from unittest.mock import patch
from kolibri.plugins.ai_assistant.rag_pipeline import _threshold_filter
from kolibri.plugins.ai_assistant.rag_pipeline import _parse_scores
from kolibri.plugins.ai_assistant.rag_pipeline import _parse_enriched_queries
from kolibri.plugins.ai_assistant.rag_pipeline import _get_pipeline_config
from kolibri.plugins.ai_assistant.rag_pipeline import _select_results


class TestThresholdFilter:

    def test_single_query_hard_and_ideal(self):
        results = [
            {"score": 5, "best_query_index": 0},
            {"score": 4, "best_query_index": 0},
            {"score": 3, "best_query_index": 0},
            {"score": 2, "best_query_index": 0},
            {"score": 1, "best_query_index": 0},
        ]
        filtered = _threshold_filter(results, hard_min=3, ideal_min=4)
        scores = [r["score"] for r in filtered]
        assert scores == [5, 4]

    def test_single_query_no_ideal_met(self):
        results = [
            {"score": 3, "best_query_index": 0},
            {"score": 3, "best_query_index": 0},
            {"score": 2, "best_query_index": 0},
        ]
        filtered = _threshold_filter(results, hard_min=3, ideal_min=4)
        scores = [r["score"] for r in filtered]
        assert scores == [3, 3]

    def test_all_below_hard_min_returns_empty(self):
        results = [
            {"score": 2, "best_query_index": 0},
            {"score": 1, "best_query_index": 0},
        ]
        filtered = _threshold_filter(results, hard_min=3, ideal_min=4)
        assert filtered == []

    def test_per_query_ideal_independent(self):
        """ideal_min applied per query: query 0 has a 5 so its 3 is dropped,
        but query 1 has no result >= 4 so its 3s are kept."""
        results = [
            {"score": 5, "best_query_index": 0},
            {"score": 3, "best_query_index": 0},
            {"score": 3, "best_query_index": 1},
            {"score": 3, "best_query_index": 1},
        ]
        filtered = _threshold_filter(results, hard_min=3, ideal_min=4)
        scores = [r["score"] for r in filtered]
        # query 0: ideal_min applies, keeps only 5
        # query 1: ideal_min does not apply, keeps both 3s
        assert scores == [5, 3, 3]


class TestParseScores:

    def test_valid_output(self):
        raw = "covers basic concepts\t3\nstep by step guide\t5"
        results = [{"content_id": "a"}, {"content_id": "b"}]
        scored = _parse_scores(raw, results, hard_min=3)
        assert scored[0]["score"] == 3
        assert scored[0]["context_note"] == "covers basic concepts"
        assert scored[1]["score"] == 5
        assert scored[1]["context_note"] == "step by step guide"

    def test_missing_tab_uses_hard_min(self):
        raw = "no tab here\nvalid note\t4"
        results = [{"content_id": "a"}, {"content_id": "b"}]
        scored = _parse_scores(raw, results, hard_min=3)
        assert scored[0]["score"] == 3
        assert scored[1]["score"] == 4

    def test_non_integer_score_uses_hard_min(self):
        raw = "some note\tabc\nother note\t5"
        results = [{"content_id": "a"}, {"content_id": "b"}]
        scored = _parse_scores(raw, results, hard_min=2)
        assert scored[0]["score"] == 2
        assert scored[1]["score"] == 5

    def test_fewer_lines_than_results(self):
        raw = "only one line\t4"
        results = [{"content_id": "a"}, {"content_id": "b"}, {"content_id": "c"}]
        scored = _parse_scores(raw, results, hard_min=3)
        assert scored[0]["score"] == 4
        assert scored[1]["score"] == 3
        assert scored[2]["score"] == 3

    def test_score_clamped_to_1_5(self):
        raw = "too high\t7\ntoo low\t0"
        results = [{"content_id": "a"}, {"content_id": "b"}]
        scored = _parse_scores(raw, results, hard_min=3)
        assert scored[0]["score"] == 5  # clamped from 7
        assert scored[1]["score"] == 1  # clamped from 0

    def test_empty_output_returns_unscored(self):
        raw = ""
        results = [{"content_id": "a"}, {"content_id": "b"}]
        scored = _parse_scores(raw, results, hard_min=3)
        assert scored is None


class TestParseEnrichedQueries:

    def test_valid_multiline(self):
        raw = "fraction concepts\nadding fractions step by step"
        result = _parse_enriched_queries(raw, "original query")
        assert result == ["fraction concepts", "adding fractions step by step"]

    def test_empty_returns_original(self):
        result = _parse_enriched_queries("", "original query")
        assert result == ["original query"]

    def test_whitespace_only_returns_original(self):
        result = _parse_enriched_queries("  \n  \n  ", "original query")
        assert result == ["original query"]

    def test_blank_lines_filtered(self):
        raw = "query one\n\n\nquery two\n"
        result = _parse_enriched_queries(raw, "original")
        assert result == ["query one", "query two"]


class TestGetPipelineConfig:

    @patch("kolibri.plugins.ai_assistant.rag_pipeline.OPTIONS", {"Assistant": {}})
    def test_defaults(self):
        config = _get_pipeline_config()
        assert config["enrich"] is True
        assert config["score"] is True
        assert config["synthesize"] is True
        assert config["hard_min"] == 3
        assert config["ideal_min"] == 4

    @patch("kolibri.plugins.ai_assistant.rag_pipeline.OPTIONS", {"Assistant": {}})
    def test_string_false_overrides(self):
        config = _get_pipeline_config({"enrich": "0", "score": "false", "synthesize": "False"})
        assert config["enrich"] is False
        assert config["score"] is False
        assert config["synthesize"] is False

    @patch("kolibri.plugins.ai_assistant.rag_pipeline.OPTIONS", {"Assistant": {}})
    def test_string_true_overrides(self):
        config = _get_pipeline_config({"enrich": "1", "score": "true"})
        assert config["enrich"] is True
        assert config["score"] is True

    @patch("kolibri.plugins.ai_assistant.rag_pipeline.OPTIONS", {"Assistant": {}})
    def test_int_overrides(self):
        config = _get_pipeline_config({"hard_min": "2", "ideal_min": "5"})
        assert config["hard_min"] == 2
        assert config["ideal_min"] == 5


class TestSelectResults:

    def test_guaranteed_per_query(self):
        candidates = [
            {"query_index": 0, "content_id": "doc_a", "score": 0.9, "context": ""},
            {"query_index": 0, "content_id": "doc_b", "score": 0.5, "context": ""},
            {"query_index": 1, "content_id": "doc_c", "score": 0.8, "context": ""},
            {"query_index": 1, "content_id": "doc_a", "score": 0.7, "context": ""},
        ]
        available = {"doc_a", "doc_b", "doc_c"}
        selected = _select_results(candidates, available, top_docs=3)
        cids = [r["content_id"] for r in selected]
        assert "doc_a" in cids
        assert "doc_c" in cids
        assert len(selected) == 3

    def test_collision_falls_to_next_best(self):
        candidates = [
            {"query_index": 0, "content_id": "doc_a", "score": 0.95, "context": ""},
            {"query_index": 0, "content_id": "doc_b", "score": 0.4, "context": ""},
            {"query_index": 1, "content_id": "doc_a", "score": 0.90, "context": ""},
            {"query_index": 1, "content_id": "doc_c", "score": 0.85, "context": ""},
        ]
        available = {"doc_a", "doc_b", "doc_c"}
        selected = _select_results(candidates, available, top_docs=3)
        cids = [r["content_id"] for r in selected]
        assert "doc_a" in cids
        assert "doc_c" in cids
        assert len(selected) == 3

    def test_unavailable_docs_skipped(self):
        candidates = [
            {"query_index": 0, "content_id": "doc_a", "score": 0.9, "context": ""},
            {"query_index": 0, "content_id": "doc_b", "score": 0.5, "context": ""},
        ]
        available = {"doc_b"}
        selected = _select_results(candidates, available, top_docs=2)
        cids = [r["content_id"] for r in selected]
        assert "doc_a" not in cids
        assert "doc_b" in cids

    def test_top_docs_less_than_queries(self):
        candidates = [
            {"query_index": 0, "content_id": "doc_a", "score": 0.9, "context": ""},
            {"query_index": 1, "content_id": "doc_b", "score": 0.8, "context": ""},
            {"query_index": 2, "content_id": "doc_c", "score": 0.7, "context": ""},
        ]
        available = {"doc_a", "doc_b", "doc_c"}
        selected = _select_results(candidates, available, top_docs=2)
        cids = [r["content_id"] for r in selected]
        assert len(selected) == 2
        assert "doc_a" in cids
        assert "doc_b" in cids

    def test_best_query_index_tracked(self):
        candidates = [
            {"query_index": 0, "content_id": "doc_a", "score": 0.5, "context": ""},
            {"query_index": 1, "content_id": "doc_a", "score": 0.9, "context": ""},
            {"query_index": 1, "content_id": "doc_b", "score": 0.3, "context": ""},
        ]
        available = {"doc_a", "doc_b"}
        selected = _select_results(candidates, available, top_docs=2)
        doc_a = [r for r in selected if r["content_id"] == "doc_a"][0]
        assert doc_a["best_query_index"] == 1
