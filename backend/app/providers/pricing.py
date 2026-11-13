"""Configurable cost *estimates*.

These rates are local configuration values used for hard budget enforcement.
They are NOT official provider prices and must never be presented as confirmed
billing. Confirmed billing records, if ever imported, are stored separately
with ``billing_status='confirmed'``.
"""

import json
import os
from dataclasses import dataclass

from app.providers.contracts import CostEstimate


@dataclass(frozen=True)
class ModelRate:
    input_per_million_usd: float
    output_per_million_usd: float

    @classmethod
    def parse(cls, value: object) -> "ModelRate":
        if not isinstance(value, dict):
            raise ValueError("Each pricing entry must be an object.")
        input_rate = float(value.get("input_per_million_usd", 0))
        output_rate = float(value.get("output_per_million_usd", 0))
        if input_rate < 0 or output_rate < 0:
            raise ValueError("Pricing rates cannot be negative.")
        return cls(input_rate, output_rate)


# Conservative example defaults for local estimates. Override with AATM_MODEL_PRICING.
DEFAULT_RATES: dict[str, ModelRate] = {
    "default": ModelRate(input_per_million_usd=3.0, output_per_million_usd=15.0),
}


class PricingTable:
    def __init__(self, rates: dict[str, ModelRate] | None = None) -> None:
        self.rates = dict(rates or DEFAULT_RATES)
        self.rates.setdefault("default", DEFAULT_RATES["default"])

    @classmethod
    def from_env(cls) -> "PricingTable":
        raw = os.environ.get("AATM_MODEL_PRICING")
        if not raw:
            return cls()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return cls()
        if not isinstance(parsed, dict):
            return cls()
        rates: dict[str, ModelRate] = {}
        for model, entry in parsed.items():
            if not isinstance(model, str) or not model.strip():
                continue
            try:
                rates[model.strip()] = ModelRate.parse(entry)
            except (TypeError, ValueError):
                continue
        return cls(rates or None)

    def rate_for(self, model: str) -> ModelRate:
        return self.rates.get(model, self.rates["default"])

    def estimate(self, model: str, input_tokens: int, output_tokens: int) -> CostEstimate:
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("Token counts cannot be negative.")
        rate = self.rate_for(model)
        amount = (
            input_tokens * rate.input_per_million_usd
            + output_tokens * rate.output_per_million_usd
        ) / 1_000_000
        return CostEstimate(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=round(amount, 6),
        )

    def describe(self) -> dict[str, object]:
        return {
            "basis": "local estimate (not confirmed provider billing)",
            "override_environment_variable": "AATM_MODEL_PRICING",
            "rates": {
                model: {
                    "input_per_million_usd": rate.input_per_million_usd,
                    "output_per_million_usd": rate.output_per_million_usd,
                }
                for model, rate in self.rates.items()
            },
        }


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> CostEstimate:
    """Convenience wrapper using the environment-configured pricing table."""
    return PricingTable.from_env().estimate(model, input_tokens, output_tokens)
