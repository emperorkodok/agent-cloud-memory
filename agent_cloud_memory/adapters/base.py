"""Base adapter classes and registry."""

from __future__ import annotations

import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_cloud_memory.core import (
    CloudMemoryClient,
    ConfigSnapshot,
    MemoryEntry,
    SessionSnapshot,
    SkillSnapshot,
)


@dataclass
class FrameworkInfo:
    """Information about a detected framework."""
    name: str
    display_name: str
    config_dir: Path
    data_dir: Path | None = None
    version: str | None = None
    confidence: float = 1.0  # 0.0 - 1.0
    extra: dict[str, Any] = field(default_factory=dict)


class FrameworkDetector:
    """Detects AI agent frameworks by scanning common locations."""

    # Framework detection patterns
    DETECTION_PATTERNS = {
        "hermes": {
            "dirs": [".hermes"],
            "files": ["config.yaml", "state.db", "MEMORY.md", "USER.md", "SOUL.md"],
            "subdirs": ["skills", "sessions", "memories"],
            "confidence": 0.95,
        },
        "openclaw": {
            "dirs": [".openclaw", ".clawdbot", ".moltbot"],
            "files": ["MEMORY.md", "USER.md", "SOUL.md", "AGENTS.md", "workspace.json"],
            "subdirs": ["skills", "memories", "workspace"],
            "confidence": 0.9,
        },
        "claude-code": {
            "dirs": [".claude"],
            "files": ["CLAUDE.md", "settings.json", ".claude.json"],
            "subdirs": ["skills", "scripts"],
            "confidence": 0.9,
        },
        "codex": {
            "dirs": [".codex"],
            "files": ["AGENTS.md", "config.toml", "memories"],
            "subdirs": ["skills", "memories"],
            "confidence": 0.9,
        },
    }

    @classmethod
    def detect_all(cls, search_paths: list[Path] | None = None) -> list[FrameworkInfo]:
        """Detect all frameworks in the given paths."""
        if search_paths is None:
            search_paths = [Path.home()]

        detected = []

        for base_path in search_paths:
            if not base_path.exists():
                continue

            for framework, patterns in cls.DETECTION_PATTERNS.items():
                for dir_name in patterns["dirs"]:
                    config_dir = base_path / dir_name
                    if config_dir.exists() and config_dir.is_dir():
                        # Check for marker files
                        confidence = patterns["confidence"]
                        matched_files = 0

                        for marker_file in patterns["files"]:
                            if (config_dir / marker_file).exists():
                                matched_files += 1

                        if matched_files > 0 or patterns.get("subdirs"):
                            data_dir = None
                            # Try to find data directory
                            for subdir in patterns.get("subdirs", []):
                                if (config_dir / subdir).exists():
                                    data_dir = config_dir / subdir
                                    break

                            detected.append(FrameworkInfo(
                                name=framework,
                                display_name=framework.replace("-", " ").title(),
                                config_dir=config_dir,
                                data_dir=data_dir,
                                confidence=confidence * (matched_files / max(len(patterns["files"]), 1) * 0.5 + 0.5),
                            ))

        # Sort by confidence descending
        detected.sort(key=lambda f: f.confidence, reverse=True)
        return detected

    @classmethod
    def detect_primary(cls, search_paths: list[Path] | None = None) -> FrameworkInfo | None:
        """Get the most confident detection."""
        all_detected = cls.detect_all(search_paths)
        return all_detected[0] if all_detected else None

    @classmethod
    def is_framework_present(cls, framework: str, path: Path) -> bool:
        """Check if a specific framework is present at path."""
        patterns = cls.DETECTION_PATTERNS.get(framework, {})
        return any((path / dir_name).exists() for dir_name in patterns.get("dirs", []))


class FrameworkAdapter(ABC):
    """Abstract base class for framework-specific adapters."""

    # Framework identifier
    FRAMEWORK_NAME: str = ""
    DISPLAY_NAME: str = ""

    # File patterns this adapter understands
    MEMORY_FILES: list[str] = []
    CONFIG_FILES: list[str] = []
    SKILL_DIRS: list[str] = []

    def __init__(self, config_dir: Path, data_dir: Path | None = None):
        self.config_dir = config_dir
        self.data_dir = data_dir or config_dir
        self._client: CloudMemoryClient | None = None

    @abstractmethod
    def load_memories(self) -> list[MemoryEntry]:
        """Load all memories from local framework format."""
        pass

    @abstractmethod
    def load_config(self) -> ConfigSnapshot | None:
        """Load configuration from local format."""
        pass

    @abstractmethod
    def load_skills(self) -> list[SkillSnapshot]:
        """Load all skills from local format."""
        pass

    @abstractmethod
    def load_sessions(self) -> list[SessionSnapshot]:
        """Load session history if available."""
        pass

    @abstractmethod
    def write_memories(self, entries: list[MemoryEntry]) -> int:
        """Write memories back to local format. Returns count written."""
        pass

    @abstractmethod
    def write_config(self, config: ConfigSnapshot) -> bool:
        """Write configuration back to local format."""
        pass

    @abstractmethod
    def write_skills(self, skills: list[SkillSnapshot]) -> int:
        """Write skills back to local format. Returns count written."""
        pass

    @abstractmethod
    def get_profile_identifier(self) -> str:
        """Get unique identifier for this agent instance/profile."""
        pass

    def set_client(self, client: CloudMemoryClient) -> None:
        """Set the cloud memory client for real-time sync."""
        self._client = client

    def on_memory_write(self, entry: MemoryEntry) -> None:
        """Hook called when a memory is written (for real-time sync)."""
        if self._client:
            self._client.remember(
                content=entry.content,
                target=entry.target,
                profile=entry.profile,
                session_id=entry.session_id,
                metadata=entry.metadata,
            )

    def on_session_end(self, session: SessionSnapshot) -> None:
        """Hook called when a session ends."""
        if self._client:
            self._client.sync_session(session)

    def on_config_change(self, config: ConfigSnapshot) -> None:
        """Hook called when config changes."""
        if self._client:
            self._client.sync_config(config)

    def on_skill_change(self, skill: SkillSnapshot) -> None:
        """Hook called when a skill is added/updated."""
        if self._client:
            self._client.sync_skill(skill)

    # ─── Utility methods for parsing common formats ─────────────────────

    @staticmethod
    def parse_markdown_entries(text: str, entry_delimiter: str = "\n§\n") -> list[str]:
        """Parse markdown entries separated by delimiter."""
        if not text:
            return []

        # Split by delimiter
        parts = text.split(entry_delimiter)
        entries = []

        for part in parts:
            part = part.strip()
            if not part:
                continue
            # Skip markdown headings that are just file markers
            if re.match(r'^#+\s*(MEMORY|USER|SOUL|AGENTS)\.md', part, re.I):
                continue
            entries.append(part)

        return entries

    @staticmethod
    def parse_memory_file(filepath: Path, target: str = "memory") -> list[MemoryEntry]:
        """Parse a memory file (MEMORY.md, USER.md, etc.) into entries."""
        if not filepath.exists():
            return []

        text = filepath.read_text(encoding="utf-8", errors="replace")
        entries_text = FrameworkAdapter.parse_markdown_entries(text)

        entries = []
        for i, entry_text in enumerate(entries_text):
            if not entry_text.strip():
                continue
            entry_id = uuid.uuid4().hex[:16]
            entries.append(MemoryEntry(
                id=entry_id,
                target=target,
                content=entry_text,
                profile="default",
                metadata={"source_file": filepath.name, "entry_index": i},
            ))

        return entries


# ─── Adapter Registry ──────────────────────────────────────────────────

# Registry of all available adapters
ADAPTER_REGISTRY: dict[str, type[FrameworkAdapter]] = {}


def register_adapter(adapter_class: type[FrameworkAdapter]) -> type[FrameworkAdapter]:
    """Decorator to register an adapter."""
    if not adapter_class.FRAMEWORK_NAME:
        raise ValueError(f"Adapter {adapter_class.__name__} missing FRAMEWORK_NAME")
    ADAPTER_REGISTRY[adapter_class.FRAMEWORK_NAME] = adapter_class
    return adapter_class


def get_adapter_by_name(name: str) -> type[FrameworkAdapter] | None:
    """Get adapter class by framework name."""
    return ADAPTER_REGISTRY.get(name)


def get_adapter_for_path(path: Path) -> FrameworkAdapter | None:
    """Auto-detect and create adapter for a path."""
    info = FrameworkDetector.detect_primary([path])
    if not info:
        return None

    adapter_class = get_adapter_by_name(info.name)
    if not adapter_class:
        return None

    return adapter_class(info.config_dir, info.data_dir)


def list_available_adapters() -> list[str]:
    """List all registered adapter names."""
    return sorted(ADAPTER_REGISTRY.keys())
