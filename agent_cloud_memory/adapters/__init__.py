"""Framework adapters for agent-cloud-memory.

Each adapter provides framework-specific implementations for:
- Detecting the framework's data directory
- Loading local memories into the universal cloud format
- Exporting cloud data back to the framework's native format
- Framework-specific hooks/events (memory writes, session ends)
"""

from __future__ import annotations

from agent_cloud_memory.adapters.base import (
    FrameworkAdapter,
    FrameworkDetector,
    ADAPTER_REGISTRY,
    get_adapter_for_path,
    get_adapter_by_name,
    list_available_adapters,
)

from agent_cloud_memory.adapters.hermes import HermesAdapter
from agent_cloud_memory.adapters.openclaw import OpenClawAdapter
from agent_cloud_memory.adapters.claude_code import ClaudeCodeAdapter
from agent_cloud_memory.adapters.codex import CodexAdapter

__all__ = [
    "FrameworkAdapter",
    "FrameworkDetector",
    "ADAPTER_REGISTRY",
    "get_adapter_for_path",
    "get_adapter_by_name",
    "list_available_adapters",
    "HermesAdapter",
    "OpenClawAdapter",
    "ClaudeCodeAdapter",
    "CodexAdapter",
]