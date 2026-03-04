"""
Model Router — auto-selects the optimal LLM model based on request complexity.

Routes between fast/cheap and smart/expensive models to optimize cost.
"""


class ModelRouter:
    """Selects the optimal LLM model for a given request."""

    MODELS = {
        "fast": "google/gemini-3-flash-preview",       # $0.50/1M
        "smart": "anthropic/claude-sonnet-4-6",         # $3.00/1M
        "powerful": "anthropic/claude-opus-4-6",        # $15.00/1M
    }

    # Cost per 1M tokens in USD (input, output)
    COSTS = {
        "google/gemini-3-flash-preview": (0.10, 0.40),
        "anthropic/claude-sonnet-4-6": (3.00, 15.00),
        "anthropic/claude-opus-4-6": (15.00, 75.00),
    }

    def route(self, user_request: str, intent_type: str, context_size: int) -> str:
        """
        Select model based on request complexity.

        Args:
            user_request: The user's natural language request.
            intent_type: Classified intent (read/write/view_op/dangerous).
            context_size: Size of context in characters.

        Returns:
            Model string for OpenRouter API.
        """
        # Dangerous operations need precision
        if intent_type == "dangerous":
            return self.MODELS["smart"]

        # Large context needs smarter model
        if context_size > 8000:
            return self.MODELS["smart"]

        # Long/complex requests
        if len(user_request) > 200:
            return self.MODELS["smart"]

        # Analyze intents may need smarter model for grouping/aggregation logic
        if intent_type == "analyze":
            return self.MODELS["smart"]

        # Simple read operations → fast model
        if intent_type == "read":
            return self.MODELS["fast"]

        # Default → fast
        return self.MODELS["fast"]

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """
        Estimate cost in USD for a given model and token counts.

        Args:
            model: Model string.
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.

        Returns:
            Estimated cost in USD.
        """
        costs = self.COSTS.get(model, (0.50, 1.50))  # fallback
        input_cost = (input_tokens / 1_000_000) * costs[0]
        output_cost = (output_tokens / 1_000_000) * costs[1]
        return round(input_cost + output_cost, 6)
