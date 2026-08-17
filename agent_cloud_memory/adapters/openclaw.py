"""OpenClaw adapter."""

from __future__ import annotations

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
class OpenClawAdapter(FrameworkAdapter):
    """Adapter for OpenClaw / ClawBot."""

    FRAMEWORK_NAME = "openclaw"
    DISPLAY_NAME = "OpenClaw"

    MEMORY_FILES = ["MEMORY.md", "USER.md", "SOUL.md", "AGENTS.md"]
    CONFIG_FILES = ["workspace.json", "config.yaml", "config.yml"]
    SKILL_DIRS = ["skills", "workspace/skills"]

    def __init__(self, config_dir: Path, data_dir: Path | None = None):
        super().__init__(config_dir, data_dir)
        self._workspace_dir = config_dir / "workspace"
        self._skills_dirs = [
            config_dir / "skills",
            config_dir / "workspace" / "skills",
        ]
        self._memories_dir = config_dir / "memories"

    def load_memories(self) -> list[MemoryEntry]:
        """Load memories from OpenClaw format."""
        entries = []

        # Load from memory files in root
        for filename, target in [("MEMORY.md", "memory"), ("USER.md", "user"), ("SOUL.md", "profile")]:
            filepath = self.config_dir / filename
            if filepath.exists():
                file_entries = self.parse_memory_file(filepath, target)
                entries.extend(file_entries)

        # Load from memories/ subdirectory (daily memories)
        if self._memories_dir.exists():
            for md_file in sorted(self._memories_dir.glob("*.md")):
                if md_file.name in ("MEMORY.md", "USER.md"):
                    continue
                file_entries = self.parse_memory_file(md_file, "memory")
                # Add date metadata from filename
                for entry in file_entries:
                    entry.metadata["openclaw_date_file"] = md_file.stem
                entries.extend(file_entries)

        # Load AGENTS.md as workspace instructions
        agents_file = self.config_dir / "AGENTS.md"
        if agents_file.exists():
            text = agents_file.read_text(encoding="utf-8", errors="replace")
            if text.strip():
                entries.append(MemoryEntry(
                    id=uuid.uuid4().hex[:16],
                    target="profile",
                    content=f"[Workspace Instructions]\n{text}",
                    profile="default",
                    metadata={"source": "AGENTS.md", "type": "workspace_instructions"},
                ))

        # Deduplicate
        seen = set()
        unique = []
        for entry in entries:
            content_hash = hash(entry.content[:200])
            if content_hash not in seen:
                seen.add(content_hash)
                unique.append(entry)

        return unique

    def load_config(self) -> ConfigSnapshot | None:
        """Load OpenClaw configuration."""
        # Try workspace.json first
        workspace_json = self.config_dir / "workspace.json"
        if workspace_json.exists():
            try:
                text = workspace_json.read_text(encoding="utf-8")
                return ConfigSnapshot(
                    profile="default",
                    config_yaml=text,
                    hostname=_get_hostname(),
                    device_id=f"openclaw-{uuid.uuid4().hex[:8]}",
                )
            except Exception:
                pass

        # Try config.yaml
        for name in ["config.yaml", "config.yml"]:
            config_path = self.config_dir / name
            if config_path.exists():
                try:
                    text = config_path.read_text(encoding="utf-8")
                    return ConfigSnapshot(
                        profile="default",
                        config_yaml=text,
                        hostname=_get_hostname(),
                        device_id=f"openclaw-{uuid.uuid4().hex[:8]}",
                    )
                except Exception:
                    pass

        return None

    def load_skills(self) -> list[SkillSnapshot]:
        """Load skills from OpenClaw skills directories."""
        skills = []

        for skills_dir in self._skills_dirs:
            if not skills_dir.exists():
                continue

            for skill_md in skills_dir.rglob("SKILL.md"):
                try:
                    rel_path = skill_md.relative_to(skills_dir)
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
        """OpenClaw doesn't have a session store like Hermes."""
        return []

    def write_memories(self, entries: list[MemoryEntry]) -> int:
        """Write memories to OpenClaw format."""
        memory_entries = [e.content for e in entries if e.target == "memory"]
        user_entries = [e.content for e in entries if e.target == "user"]
        profile_entries = [e.content for e in entries if e.target == "profile"]

        count = 0

        if memory_entries:
            (self.config_dir / "MEMORY.md").write_text(
                "\n§\n".join(memory_entries) + "\n§\n",
                encoding="utf-8"
            )
            count += len(memory_entries)

        if user_entries:
            (self.config_dir / "USER.md").write_text(
                "\n§\n".join(user_entries) + "\n§\n",
                encoding="utf-8"
            )
            count += len(user_entries)

        if profile_entries:
            (self.config_dir / "SOUL.md").write_text(
                "\n§\n".join(profile_entries) + "\n§\n",
                encoding="utf-8"
            )
            count += len(profile_entries)

        return count

    def write_config(self, config: ConfigSnapshot) -> bool:
        """Write config as workspace.json."""
        try:
            (self.config_dir / "workspace.json").write_text(config.config_yaml, encoding="utf-8")
            return True
        except Exception:
            return False

    def write_skills(self, skills: list[SkillSnapshot]) -> int:
        """Write skills to primary skills directory."""
        count = 0
        primary_skills_dir = self._skills_dirs[0]  # config_dir/skills

        for skill in skills:
            try:
                # Convert forward slashes to platform-specific paths
                skill_path = primary_skills_dir / Path(skill.skill_path)
                skill_path.parent.mkdir(parents=True, exist_ok=True)
                skill_path.write_text(skill.content, encoding="utf-8")
                count += 1
            except Exception:
                continue

        return count

    def get_profile_identifier(self) -> str:
        """Get OpenClaw identifier."""
        return "default"

    def full_sync(self, client: CloudMemoryClient) -> SyncResult:
        """Perform full sync to cloud."""
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
        """Perform full restore from cloud."""
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
