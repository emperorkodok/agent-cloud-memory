"""agent-cloud-memory - Universal cloud memory for AI agents."""

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "Hermes Community"

from agent_cloud_memory.core import (
    MemoryProvider,
    PostgreSQLBackend,
    CloudMemoryClient,
)

from agent_cloud_memory.adapters import (
    HermesAdapter,
    OpenClawAdapter,
    ClaudeCodeAdapter,
    CodexAdapter,
)

__all__ = [
    "MemoryProvider",
    "PostgreSQLBackend",
    "CloudMemoryClient",
    "HermesAdapter",
    "OpenClawAdapter",
    "ClaudeCodeAdapter",
    "CodexAdapter",
]