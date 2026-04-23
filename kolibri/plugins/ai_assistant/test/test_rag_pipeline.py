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
