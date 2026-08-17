"""Claude Code adapter."""

from __future__ import annotations

import json
import socket
import uuid
from pathlib import Path

from agent_cloud_memory.adapters.base import FrameworkAdapter, register_adapter
from agent_cloud_memory.core import (
    CloudMemoryClient,
    ConfigSnapshot,
    MemoryEntry,
    RestoreResult,
    SessionSnapshot,
    SkillSnapshot,
    SyncResult,
)


def _get_hostname() -> str:
    """Cross-platform hostname getter."""
    try:
        return socket.gethostname()
    except Exception:
        return "unknown-host"


@register_adapter
class ClaudeCodeAdapter(FrameworkAdapter):
    """Adapter for Claude Code (Anthropic)."""

    FRAMEWORK_NAME = "claude-code"
    DISPLAY_NAME = "Claude Code"

    MEMORY_FILES = ["CLAUDE.md"]
    CONFIG_FILES = ["settings.json", ".claude.json"]
    SKILL_DIRS = ["skills"]

    def __init__(self, config_dir: Path, data_dir: Path | None = None):
        super().__init__(config_dir, data_dir)
        self._skills_dir = config_dir / "skills"
        self._settings_json = config_dir / "settings.json"
        self._claude_json = Path.home() / ".claude.json"

    def load_memories(self) -> list[MemoryEntry]:
        """Load memories from CLAUDE.md."""
        entries = []

        # Load CLAUDE.md
        claude_md = self.config_dir / "CLAUDE.md"
        if claude_md.exists():
            file_entries = self.parse_memory_file(claude_md, "memory")
            for entry in file_entries:
                entry.metadata["source"] = "CLAUDE.md"
            entries.extend(file_entries)

        # Load from skills if they have markdown docs
        if self._skills_dir.exists():
            for skill_md in self._skills_dir.rglob("*.md"):
                if skill_md.name == "SKILL.md":
                    continue
                try:
                    text = skill_md.read_text(encoding="utf-8", errors="replace")
                    if text.strip():
                        entries.append(MemoryEntry(
                            id=uuid.uuid4().hex[:16],
                            target="memory",
                            content=f"[Skill: {skill_md.parent.name}]\n{text}",
                            profile="default",
                            metadata={"source": f"skill:{skill_md.parent.name}"},
                        ))
                except Exception:
                    continue

        return entries

    def load_config(self) -> ConfigSnapshot | None:
        """Load settings.json and .claude.json."""
        configs = []

        # settings.json
        if self._settings_json.exists():
            try:
                text = self._settings_json.read_text(encoding="utf-8")
                data = json.loads(text)
                # Convert to YAML-like format for storage
                import yaml
                configs.append(yaml.dump(data, sort_keys=False))
            except Exception:
                pass

        # .claude.json (global config)
        if self._claude_json.exists():
            try:
                text = self._claude_json.read_text(encoding="utf-8")
                data = json.loads(text)
                import yaml
                configs.append(yaml.dump(data, sort_keys=False))
            except Exception:
                pass

        if not configs:
            return None

        return ConfigSnapshot(
            profile="default",
            config_yaml="\n---\n".join(configs),
            hostname=_get_hostname(),
            device_id=f"claude-code-{uuid.uuid4().hex[:8]}",
        )

    def load_skills(self) -> list[SkillSnapshot]:
        """Load skills from .claude/skills/."""
        skills = []

        if not self._skills_dir.exists():
            return skills

        for skill_md in self._skills_dir.rglob("SKILL.md"):
            try:
                rel_path = skill_md.relative_to(self._skills_dir)
                skill_name = skill_md.parent.name
                content = skill_md.read_text(encoding="utf-8")

                skills.append(SkillSnapshot(
                    profile="default",
                    skill_path=rel_path.as_posix(),  # Cross-platform path
                    skill_name=skill_name,
                    content=content,
                    file_type="SKILL.md",
                ))
            except Exception:
                continue

        return skills

    def load_sessions(self) -> list[SessionSnapshot]:
        """Claude Code doesn't have session persistence."""
        return []

    def write_memories(self, entries: list[MemoryEntry]) -> int:
        """Write memories to CLAUDE.md."""
        memory_entries = [e.content for e in entries if e.target == "memory"]

        if not memory_entries:
            return 0

        claude_md = self.config_dir / "CLAUDE.md"
        # Append to existing or create new
        existing = ""
        if claude_md.exists():
            existing = claude_md.read_text(encoding="utf-8")

        # Combine
        all_content = existing + ("\n\n" if existing else "") + "\n§\n".join(memory_entries) + "\n§\n"
        claude_md.write_text(all_content, encoding="utf-8")

        return len(memory_entries)

    def write_config(self, config: ConfigSnapshot) -> bool:
        """Write config back to settings.json."""
        try:
            import yaml
            data = yaml.safe_load(config.config_yaml)
            if isinstance(data, dict):
                self._settings_json.write_text(
                    json.dumps(data, indent=2),
                    encoding="utf-8"
                )
                return True
        except Exception:
            pass
        return False

    def write_skills(self, skills: list[SkillSnapshot]) -> int:
        """Write skills to .claude/skills/."""
        count = 0

        for skill in skills:
            try:
                # Convert forward slashes to platform-specific paths
                skill_path = self._skills_dir / Path(skill.skill_path)
                skill_path.parent.mkdir(parents=True, exist_ok=True)
                skill_path.write_text(skill.content, encoding="utf-8")
                count += 1
            except Exception:
                continue

        return count

    def get_profile_identifier(self) -> str:
        return "default"

    def full_sync(self, client: CloudMemoryClient) -> SyncResult:
        result = SyncResult()

        # Sync memories
        memories = self.load_memories()
        for entry in memories:
            try:
                client.remember(
                    content=entry.content,
                    target=entry.target,
                    profile=entry.profile,
                    session_id=entry.session_id,
                    metadata=entry.metadata,
                )
                result.memories_synced += 1
            except Exception as e:
                result.errors.append(f"Memory sync error: {e}")

        # Sync config
        config = self.load_config()
        if config:
            try:
                client.sync_config(config)
                result.config_synced = True
            except Exception as e:
                result.errors.append(f"Config sync error: {e}")

        # Sync skills
        skills = self.load_skills()
        for skill in skills:
            try:
                client.sync_skill(skill)
                result.skills_synced += 1
            except Exception as e:
                result.errors.append(f"Skill sync error: {e}")

        return result

    def full_restore(self, client: CloudMemoryClient) -> RestoreResult:
        result = RestoreResult()

        # Restore memories
        memories = client.restore_memories()
        self.write_memories(memories)
        result.memories_restored = len(memories)

        # Restore config
        config = client.restore_config()
        if config:
            try:
                self.write_config(config)
                result.config_restored = True
            except Exception as e:
                result.errors.append(f"Config restore error: {e}")

        # Restore skills
        skills = client.restore_skills()
        self.write_skills(skills)
        result.skills_restored = len(skills)

        return result
