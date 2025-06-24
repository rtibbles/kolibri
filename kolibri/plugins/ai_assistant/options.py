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
            "description": "Model identifier for the AI assistant (e.g., openai/gpt-4o-mini, anthropic/claude-2)",
        },
    }
}
