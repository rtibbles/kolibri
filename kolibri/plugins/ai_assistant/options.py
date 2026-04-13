option_spec = {
    "Assistant": {
        "AI_ASSISTANT_API_KEY": {
            "type": "string",
            "default": "",
            "description": "API key for the AI assistant service (e.g., OpenAI, Anthropic)",
        },
        "AI_ASSISTANT_MODEL": {
            "type": "string",
            "default": "openai/gpt-4.1-nano",
            "description": "Model identifier for the AI assistant (e.g., openai/gpt-4o-mini, anthropic/claude-2, litert/gemma-4-E2B-it)",
        },
        "AI_ASSISTANT_MODEL_PATH": {
            "type": "string",
            "default": "",
            "description": "Path to local model file for litert provider (e.g., /home/user/models/gemma-4-E2B-it.litertlm)",
        },
        "AI_ASSISTANT_RAG_DATA_PATH": {
            "type": "string",
            "default": "",
            "description": "Path to precomputed RAG index directory (containing doc_embeddings.npy, model/, etc.)",
        },
    }
}
