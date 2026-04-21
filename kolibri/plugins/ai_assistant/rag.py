"""RAG index for Kolibri AI assistant.

Singleton class that loads precomputed embeddings and provides
fast semantic search + sub-chunk context assembly.

Runtime dependencies: onnxruntime, tokenizers, numpy
(No PyTorch, no sentence-transformers, no FAISS)
"""

import json
import logging
import time
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

_instance = None


class RAGIndex:
    """In-memory RAG index with ONNX embedding model."""

    def __init__(self, data_dir):
        data_dir = Path(data_dir)
        t0 = time.time()
        logger.info("Loading RAG index from %s...", data_dir)

        # Load ONNX model + tokenizer
        self._load_model(data_dir / "model")

        # Load document embeddings (keep as float16 to save memory on
        # shared-memory systems like Jetson where GPU needs the headroom)
        self.doc_embeddings = np.load(
            data_dir / "doc_embeddings.npy"
        ).astype(np.float16)
        self.doc_metadata = json.loads(
            (data_dir / "doc_metadata.json").read_text()
        )

        # Load sub-chunk embeddings
        self.chunk_embeddings = np.load(
            data_dir / "chunk_embeddings.npy"
        ).astype(np.float16)
        self.chunk_index = json.loads(
            (data_dir / "chunk_index.json").read_text()
        )
        self.chunk_texts = json.loads(
            (data_dir / "chunk_texts.json").read_text()
        )

        elapsed = time.time() - t0
        logger.info(
            "RAG index loaded: %d docs, %d chunks in %.1fs (%.0f MB resident)",
            len(self.doc_metadata),
            self.chunk_embeddings.shape[0],
            elapsed,
            (self.doc_embeddings.nbytes + self.chunk_embeddings.nbytes) / 1e6,
        )

    def _load_model(self, model_dir):
        """Load ONNX model and tokenizer."""
        import onnxruntime as ort
        from tokenizers import Tokenizer

        onnx_path = model_dir / "model.onnx"
        self.session = ort.InferenceSession(
            str(onnx_path),
            providers=["CPUExecutionProvider"],
        )
        self.tokenizer = Tokenizer.from_file(
            str(model_dir / "tokenizer.json")
        )
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        self.tokenizer.enable_truncation(max_length=128)

        # Read pooling config
        pooling_path = model_dir / "1_Pooling" / "config.json"
        if pooling_path.exists():
            pooling_cfg = json.loads(pooling_path.read_text())
            self._pooling_mode = (
                "mean"
                if pooling_cfg.get("pooling_mode_mean_tokens")
                else "cls"
            )
        else:
            self._pooling_mode = "mean"

        logger.info("ONNX model loaded (%s pooling)", self._pooling_mode)

    def embed(self, texts):
        """Embed one or more texts using the ONNX model.

        Args:
            texts: list of strings to embed.

        Returns:
            numpy array of shape (len(texts), hidden_dim), L2-normalized.
        """
        encodings = self.tokenizer.encode_batch(texts)

        input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
        attention_mask = np.array(
            [e.attention_mask for e in encodings], dtype=np.int64
        )
        token_type_ids = np.zeros_like(input_ids)

        outputs = self.session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            },
        )
        token_embeddings = outputs[0]  # (batch, seq_len, hidden_dim)

        # Mean pooling
        if self._pooling_mode == "mean":
            mask_expanded = attention_mask[:, :, np.newaxis].astype(
                np.float32
            )
            summed = (token_embeddings * mask_expanded).sum(axis=1)
            counts = mask_expanded.sum(axis=1).clip(min=1e-9)
            pooled = summed / counts
        else:
            pooled = token_embeddings[:, 0, :]  # CLS token

        # L2 normalize
        norms = np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-9)
        return (pooled / norms).astype(np.float16)

    def search(self, query, top_docs=3, sub_chunks=2):
        """Search for relevant content and assemble context.

        Args:
            query: user's question string.
            top_docs: number of top documents to return.
            sub_chunks: number of sub-chunks to select per document.

        Returns:
            list of dicts with content_id, node_id, channel_id, score, context.
        """
        t0 = time.perf_counter()

        # Embed query
        query_vec = self.embed([query])[0]
        t_embed = time.perf_counter()
        logger.info("RAG embed query in %.1fms: %r", (t_embed - t0) * 1000, query[:80])

        # Document-level search (numpy dot product)
        doc_scores = self.doc_embeddings @ query_vec
        if top_docs < len(doc_scores):
            top_indices = np.argpartition(doc_scores, -top_docs)[-top_docs:]
            top_indices = top_indices[
                np.argsort(doc_scores[top_indices])[::-1]
            ]
        else:
            top_indices = np.argsort(doc_scores)[::-1]

        t_docsearch = time.perf_counter()
        logger.info(
            "RAG doc-level search in %.1fms: scored %d docs, top %d scores: %s",
            (t_docsearch - t_embed) * 1000,
            len(doc_scores),
            min(top_docs, len(top_indices)),
            ", ".join("%.4f" % doc_scores[i] for i in top_indices[:top_docs]),
        )

        results = []
        for doc_idx in top_indices:
            meta = self.doc_metadata[doc_idx]
            cid = meta["content_id"]
            score = float(doc_scores[doc_idx])

            # Sub-chunk selection
            context = self._select_sub_chunks(cid, query_vec, sub_chunks)

            results.append(
                {
                    "content_id": cid,
                    "node_id": meta["node_id"],
                    "channel_id": meta["channel_id"],
                    "title": meta.get("title", ""),
                    "description": meta.get("description", ""),
                    "kind": meta.get("kind", ""),
                    "score": round(score, 4),
                    "context": context,
                }
            )

            logger.info(
                "RAG result: content_id=%s, score=%.4f, title=%s, context_len=%d",
                cid[:8], score,
                meta.get("title", "?"),
                len(context),
            )

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "RAG search complete in %.1fms: %d results for %r",
            elapsed_ms,
            len(results),
            query[:80],
        )
        return results

    def _select_sub_chunks(self, content_id, query_vec, n):
        """Select best sub-chunks from a document, formatted with [...] gaps."""
        idx_info = self.chunk_index.get(content_id)
        texts = self.chunk_texts.get(content_id, [])

        if not idx_info or not texts:
            return ""

        offset = idx_info["offset"]
        count = idx_info["count"]

        if count <= n:
            return " ".join(texts)

        # Score sub-chunks against query
        chunk_embs = self.chunk_embeddings[offset : offset + count]
        scores = chunk_embs @ query_vec
        top_k = np.argsort(scores)[-n:]
        top_k = sorted(top_k)  # preserve reading order

        # Join with [...] between non-adjacent chunks
        parts = [texts[top_k[0]]]
        for i in range(1, len(top_k)):
            if top_k[i] > top_k[i - 1] + 1:
                parts.append("[...]")
            parts.append(texts[top_k[i]])

        return " ".join(parts)

    @classmethod
    def get(cls, data_dir):
        """Get or create the singleton RAG index."""
        global _instance
        if _instance is None:
            _instance = cls(data_dir)
        return _instance
