"""Registry of known provider adapters."""

from __future__ import annotations

from typing import Callable

from app.providers.adapters import AnthropicAdapter, ArenaBridgeAdapter, ProviderAdapter
from app.providers.context import ProviderContext
from app.providers.contracts import PROVIDER_IDS


class ProviderRegistry:
    def __init__(self, adapters: list[ProviderAdapter] | None = None) -> None:
        items = adapters if adapters is not None else [ArenaBridgeAdapter(), AnthropicAdapter()]
        self._adapters: dict[str, ProviderAdapter] = {item.provider_id: item for item in items}

    def get(self, provider_id: str) -> ProviderAdapter | None:
        return self._adapters.get(provider_id)

    def list(self) -> list[ProviderAdapter]:
        return [self._adapters[key] for key in PROVIDER_IDS if key in self._adapters]

    def describe_all(self, context_for: Callable[[str], ProviderContext]) -> list[dict[str, object]]:
        return [adapter.descriptor(context_for(adapter.provider_id)) for adapter in self.list()]

    def health_all(self, context_for: Callable[[str], ProviderContext]) -> dict[str, object]:
        return {
            adapter.provider_id: adapter.health(context_for(adapter.provider_id)).as_dict()
            for adapter in self.list()
        }


def default_registry() -> ProviderRegistry:
    return ProviderRegistry()
