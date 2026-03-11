"""Tests for agent_cli.cost — pricing and CostTracker."""

from __future__ import annotations

import pytest

from agent_cli.cost import PRICING, CostTracker


class TestCostTrackerInit:
    """Verify initial state."""

    def test_initial_totals_zero(self):
        ct = CostTracker("claude-sonnet-4-5-20250929")
        assert ct.total_input == 0
        assert ct.total_output == 0

    def test_initial_cost_zero(self):
        ct = CostTracker("claude-sonnet-4-5-20250929")
        assert ct.total_cost == 0.0


class TestCostTrackerAdd:
    """Test token accumulation."""

    def test_add_accumulates(self):
        ct = CostTracker("claude-sonnet-4-5-20250929")
        ct.add(1000, 500)
        assert ct.total_input == 1000
        assert ct.total_output == 500
        ct.add(2000, 300)
        assert ct.total_input == 3000
        assert ct.total_output == 800


class TestCostTrackerCost:
    """Test cost computation."""

    def test_known_model_cost(self):
        ct = CostTracker("claude-sonnet-4-5-20250929")
        ct.add(1_000_000, 1_000_000)
        # sonnet: $3/M input, $15/M output
        assert ct.total_cost == pytest.approx(3.0 + 15.0)

    def test_unknown_model_uses_default(self):
        ct = CostTracker("unknown-model")
        ct.add(1_000_000, 1_000_000)
        # default: $3/M input, $15/M output
        assert ct.total_cost == pytest.approx(3.0 + 15.0)

    def test_opus_cost(self):
        ct = CostTracker("claude-opus-4-6")
        ct.add(1_000_000, 1_000_000)
        # opus: $15/M input, $75/M output
        assert ct.total_cost == pytest.approx(15.0 + 75.0)

    def test_haiku_cost(self):
        ct = CostTracker("claude-haiku-4-5-20251001")
        ct.add(1_000_000, 1_000_000)
        # haiku: $0.80/M input, $4/M output
        assert ct.total_cost == pytest.approx(0.80 + 4.0)


class TestCostTrackerCostFor:
    """Test per-turn cost calculation."""

    def test_cost_for_does_not_accumulate(self):
        ct = CostTracker("claude-sonnet-4-5-20250929")
        cost = ct.cost_for(1_000_000, 0)
        assert cost == pytest.approx(3.0)
        assert ct.total_input == 0  # not accumulated


class TestFormatUsageLine:
    """Test the formatted usage string."""

    def test_basic_format(self):
        ct = CostTracker("claude-sonnet-4-5-20250929")
        ct.add(12340, 2100)
        line = ct.format_usage_line(12340, 2100)
        assert "12,340 in" in line
        assert "2,100 out" in line
        assert "$" in line

    def test_with_context_percentage(self):
        ct = CostTracker("claude-sonnet-4-5-20250929")
        ct.add(10000, 2000)
        line = ct.format_usage_line(10000, 2000, last_input_tokens=28000)
        assert "% ctx" in line

    def test_without_context_percentage(self):
        ct = CostTracker("claude-sonnet-4-5-20250929")
        ct.add(10000, 2000)
        line = ct.format_usage_line(10000, 2000)
        assert "ctx" not in line


class TestPricingTable:
    """Verify pricing table has expected models."""

    def test_has_opus(self):
        assert "claude-opus-4-6" in PRICING

    def test_has_sonnet(self):
        assert "claude-sonnet-4-5-20250929" in PRICING

    def test_has_haiku(self):
        assert "claude-haiku-4-5-20251001" in PRICING

    def test_pricing_tuples_are_pairs(self):
        for model, (inp, out) in PRICING.items():
            assert isinstance(inp, float)
            assert isinstance(out, float)
