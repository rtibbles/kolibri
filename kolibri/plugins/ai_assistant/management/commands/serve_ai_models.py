# flake8: noqa: E501
"""
Django management command that starts a lightweight HTTP server for AI model
inference and RAG search.  Designed to run as a separate process so the
models stay loaded across Kolibri restarts, GPU memory is isolated, and
concurrent-access issues disappear.

Usage:
    kolibri manage serve_ai_models [--port PORT] [--host HOST]

The server exposes:
    POST /v1/chat/completions   OpenAI-compatible chat endpoint (LiteRT-LM)
    POST /v1/rag/search         Semantic search over the precomputed RAG index
    GET  /v1/health             Readiness / health check
"""
import atexit
import json
import logging
import os
import signal
import sys
import time
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer

from django.core.management.base import BaseCommand

from kolibri.utils.conf import KOLIBRI_HOME
from kolibri.utils.conf import OPTIONS

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8765
PID_FILENAME = "ai_server.json"


def _pid_file_path():
    return os.path.join(KOLIBRI_HOME, PID_FILENAME)


def _write_pid_file(host, port):
    data = {
        "pid": os.getpid(),
        "port": port,
        "url": "http://{}:{}".format(host, port),
    }
    path = _pid_file_path()
    with open(path, "w") as f:
        json.dump(data, f)
    logger.info("PID file written: %s", path)


def _remove_pid_file():
    path = _pid_file_path()
    try:
        os.remove(path)
        logger.info("PID file removed: %s", path)
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------
# Model loading helpers
# ---------------------------------------------------------------------------

def _load_litert_engine():
    """Load the LiteRT-LM engine with GPU backend."""
    assistant_settings = OPTIONS.get("Assistant", {})
    model_path = assistant_settings.get("AI_ASSISTANT_MODEL_PATH", "")
    if not model_path:
        logger.warning("AI_ASSISTANT_MODEL_PATH not set; LLM endpoint will be unavailable")
        return None

    import litert_lm

    litert_lm.set_min_log_severity(litert_lm.LogSeverity.ERROR)
    engine = litert_lm.Engine(
        model_path,
        backend=litert_lm.Backend.GPU,
        cache_dir="/tmp/litert-lm-cache",
    )
    logger.info("LiteRT-LM engine loaded (GPU): %s", model_path)
    return engine


def _load_rag_index():
    """Load the RAG index (ONNX embeddings + metadata)."""
    assistant_settings = OPTIONS.get("Assistant", {})
    data_path = assistant_settings.get("AI_ASSISTANT_RAG_DATA_PATH", "")
    if not data_path:
        logger.warning("AI_ASSISTANT_RAG_DATA_PATH not set; RAG endpoint will be unavailable")
        return None

    from kolibri.plugins.ai_assistant.rag import RAGIndex

    return RAGIndex.get(data_path)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

def _read_json_body(handler):
    """Read and parse a JSON request body."""
    length = int(handler.headers.get("Content-Length", 0))
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length))


def _send_json(handler, data, status=200):
    body = json.dumps(data).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def make_handler(engine, rag_index, model_name):
    """Create a request handler class bound to the loaded models."""

    class AIModelHandler(BaseHTTPRequestHandler):

        # Suppress per-request log lines from BaseHTTPRequestHandler;
        # we do our own logging.
        def log_message(self, format, *args):
            logger.debug(format, *args)

        # -- routing ---------------------------------------------------

        def do_GET(self):
            if self.path == "/v1/health":
                return self._handle_health()
            _send_json(self, {"error": "not found"}, 404)

        def do_POST(self):
            if self.path == "/v1/chat/completions":
                return self._handle_chat()
            if self.path == "/v1/rag/search":
                return self._handle_rag_search()
            _send_json(self, {"error": "not found"}, 404)

        # -- endpoints -------------------------------------------------

        def _handle_health(self):
            _send_json(self, {
                "status": "ok",
                "models": {
                    "llm": {
                        "loaded": engine is not None,
                        "model": model_name if engine else None,
                        "backend": "GPU" if engine else None,
                    },
                    "rag": {
                        "loaded": rag_index is not None,
                    },
                },
            })

        def _handle_chat(self):
            if engine is None:
                _send_json(self, {"error": "LLM not loaded"}, 503)
                return

            try:
                body = _read_json_body(self)
            except Exception:
                _send_json(self, {"error": "invalid JSON body"}, 400)
                return

            messages = body.get("messages", [])

            # Separate system messages from conversation messages for
            # litert_lm's create_conversation API.
            system_parts = []
            user_prompt = ""
            for msg in messages:
                if msg.get("role") == "system":
                    system_parts.append(msg.get("content", ""))
                elif msg.get("role") == "user":
                    user_prompt = msg.get("content", "")

            litert_messages = []
            if system_parts:
                litert_messages.append({
                    "role": "system",
                    "content": [{"type": "text", "text": "\n\n".join(system_parts)}],
                })

            logger.info("LLM prompt:\n--- SYSTEM ---\n%s\n--- USER ---\n%s\n--- END PROMPT ---",
                        "\n\n".join(system_parts) if system_parts else "(none)",
                        user_prompt)

            try:
                t0 = time.perf_counter()
                with engine.create_conversation(messages=litert_messages) as conversation:
                    response = conversation.send_message(user_prompt)
                elapsed = time.perf_counter() - t0
                text = response["content"][0]["text"]
                logger.info("LLM response (%.1fs, %d chars):\n--- RESPONSE ---\n%s\n--- END RESPONSE ---",
                            elapsed, len(text), text)
            except Exception:
                logger.exception("LLM inference failed")
                _send_json(self, {"error": "LLM inference failed"}, 500)
                return

            # OpenAI-compatible response envelope
            _send_json(self, {
                "id": "chatcmpl-local",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model_name or "litert",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            })

        def _handle_rag_search(self):
            if rag_index is None:
                _send_json(self, {"error": "RAG index not loaded"}, 503)
                return

            try:
                body = _read_json_body(self)
            except Exception:
                _send_json(self, {"error": "invalid JSON body"}, 400)
                return

            queries = body.get("queries", [])
            if not queries or not isinstance(queries, list):
                _send_json(self, {"error": "missing or invalid 'queries' (expected list of strings)"}, 400)
                return

            top_docs = body.get("top_docs", 6)
            sub_chunks = body.get("sub_chunks", 2)

            try:
                results = rag_index.search_batch(queries, top_docs=top_docs, sub_chunks=sub_chunks)
            except Exception:
                logger.exception("RAG batch search failed")
                _send_json(self, {"error": "RAG search failed"}, 500)
                return

            _send_json(self, {"results": results})

    return AIModelHandler


class Command(BaseCommand):
    help = "Start the AI model inference server (LiteRT-LM + RAG)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--port",
            type=int,
            default=DEFAULT_PORT,
            help="Preferred port (falls back to OS-assigned if unavailable). Default: {}".format(DEFAULT_PORT),
        )
        parser.add_argument(
            "--host",
            default="127.0.0.1",
            help="Bind address. Default: 127.0.0.1",
        )

    def handle(self, *args, **options):
        host = options["host"]
        port = options["port"]

        # -- load models -----------------------------------------------
        self.stdout.write("Loading models...")

        engine = _load_litert_engine()
        rag_index = _load_rag_index()

        if engine is None and rag_index is None:
            self.stderr.write(
                self.style.ERROR(
                    "Neither LLM nor RAG is configured. Set AI_ASSISTANT_MODEL_PATH "
                    "and/or AI_ASSISTANT_RAG_DATA_PATH in options.ini [Assistant]."
                )
            )
            sys.exit(1)

        # Derive model name for the OpenAI-compatible response envelope
        assistant_settings = OPTIONS.get("Assistant", {})
        model_str = assistant_settings.get("AI_ASSISTANT_MODEL", "")
        model_name = model_str.split("/", 1)[-1] if "/" in model_str else model_str

        handler_class = make_handler(engine, rag_index, model_name)

        # -- bind to port (preferred, then fallback) --------------------
        try:
            server = HTTPServer((host, port), handler_class)
        except OSError:
            self.stdout.write(
                self.style.WARNING(
                    "Port {} unavailable, using OS-assigned port".format(port)
                )
            )
            server = HTTPServer((host, 0), handler_class)

        actual_port = server.server_address[1]

        # -- PID / port file -------------------------------------------
        _write_pid_file(host, actual_port)
        atexit.register(_remove_pid_file)

        def _shutdown(signum, frame):
            self.stdout.write("\nShutting down...")
            _remove_pid_file()
            # Don't call server.shutdown() from the signal handler -- it
            # deadlocks because shutdown() waits for serve_forever() which
            # is blocked in the same thread.  Raising SystemExit unwinds
            # serve_forever() and falls through to the finally block.
            raise SystemExit(0)

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)

        status_parts = []
        if engine is not None:
            status_parts.append("LLM ({})".format(model_name))
        if rag_index is not None:
            status_parts.append("RAG")
        self.stdout.write(
            self.style.SUCCESS(
                "AI model server running on {}:{} [{}]".format(
                    host, actual_port, " + ".join(status_parts)
                )
            )
        )

        try:
            server.serve_forever()
        finally:
            _remove_pid_file()
            if engine is not None:
                self.stdout.write("Releasing LiteRT engine...")
                del engine
