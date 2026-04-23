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
        "AI_ASSISTANT_RAG_QUERY_ENRICHMENT": {
            "type": "bool",
            "default": True,
            "description": "Enable LLM-based query enrichment stage in RAG pipeline",
        },
        "AI_ASSISTANT_RAG_LLM_SCORING": {
            "type": "bool",
            "default": True,
            "description": "Enable LLM-based scoring and contextualization of RAG results",
        },
        "AI_ASSISTANT_RAG_SYNTHESIS": {
            "type": "bool",
            "default": True,
            "description": "Enable LLM synthesis of introductory message for RAG results",
        },
        "AI_ASSISTANT_RAG_SCORE_HARD_MIN": {
            "type": "int",
            "default": 3,
            "description": "Minimum LLM relevance score (1-5) to include a result. Results below this are always excluded.",
        },
        "AI_ASSISTANT_RAG_SCORE_IDEAL_MIN": {
            "type": "int",
            "default": 4,
            "description": "Preferred minimum score. Applied per enriched query: if any result for a given query meets this threshold, lower-scoring results from that query are excluded. Across queries, the best result is always kept down to SCORE_HARD_MIN.",
        },
    }
}
