"""Token cost tracking — pricing table and per-session accumulator."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# (input_per_million, output_per_million) in USD
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-6": (15.0, 75.0),
    "claude-opus-4-5-20250414": (15.0, 75.0),
    "claude-sonnet-4-5-20250929": (3.0, 15.0),
    "claude-sonnet-4-5-20250514": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
}

# Default context window sizes
CONTEXT_WINDOWS: dict[str, int] = {
    "claude-opus-4-6": 200_000,
    "claude-opus-4-5-20250414": 200_000,
    "claude-sonnet-4-5-20250929": 200_000,
    "claude-sonnet-4-5-20250514": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
}

DEFAULT_CONTEXT_WINDOW = 200_000


class CostTracker:
    """Tracks cumulative token usage and cost for a session."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.total_input: int = 0
        self.total_output: int = 0

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.total_input += input_tokens
        self.total_output += output_tokens

    @property
    def total_cost(self) -> float:
        if self.model not in PRICING:
            logger.warning(
                "Model '%s' not in PRICING table — using Sonnet defaults ($3/$15 per M)",
                self.model,
            )
        in_price, out_price = PRICING.get(self.model, (3.0, 15.0))
        return (
            self.total_input * in_price / 1_000_000
            + self.total_output * out_price / 1_000_000
        )

    def cost_for(self, input_tokens: int, output_tokens: int) -> float:
        if self.model not in PRICING:
            logger.warning(
                "Model '%s' not in PRICING table — using Sonnet defaults ($3/$15 per M)",
                self.model,
            )
        in_price, out_price = PRICING.get(self.model, (3.0, 15.0))
        return (
            input_tokens * in_price / 1_000_000
            + output_tokens * out_price / 1_000_000
        )

    def format_usage_line(
        self,
        input_tokens: int,
        output_tokens: int,
        last_input_tokens: int | None = None,
    ) -> str:
        """Format a usage line like: 12,340 in · 2,100 out · $0.23 · 14% ctx"""
        parts = [
            f"{input_tokens:,} in",
            f"{output_tokens:,} out",
            f"${self.total_cost:.2f}",
        ]

        if last_input_tokens is not None:
            ctx_window = CONTEXT_WINDOWS.get(self.model, DEFAULT_CONTEXT_WINDOW)
            pct = last_input_tokens / ctx_window * 100
            parts.append(f"{pct:.0f}% ctx")

        return " \u00b7 ".join(parts)
