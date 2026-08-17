"""Hermes Agent adapter."""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_cloud_memory.adapters.base import FrameworkAdapter, register_adapter
from agent_cloud_memory.core import (
    MemoryEntry,
    SessionSnapshot,
    ConfigSnapshot,
    SkillSnapshot,
    CloudMemoryClient,
)


def _get_hostname() -> str:
    """Cross-platform hostname getter."""
    try:
        return socket.gethostname()
    except Exception:
        return "unknown-host"


@register_adapter
class HermesAdapter(FrameworkAdapter):
    """Adapter for Hermes Agent (primary framework)."""
    
    FRAMEWORK_NAME = "hermes"
    DISPLAY_NAME = "Hermes Agent"
    
    MEMORY_FILES = ["MEMORY.md", "USER.md", "SOUL.md"]
    CONFIG_FILES = ["config.yaml", "state.db"]
    SKILL_DIRS = ["skills"]
    
    def __init__(self, config_dir: Path, data_dir: Optional[Path] = None):
        super().__init__(config_dir, data_dir)
        self._state_db = config_dir / "state.db"
        self._memories_dir = config_dir / "memories"
        self._skills_dir = config_dir / "skills"
    
    def load_memories(self) -> List[MemoryEntry]:
        """Load memories from MEMORY.md, USER.md, SOUL.md and state.db."""
        entries = []
        
        # Load from markdown files
        for filename, target in [("MEMORY.md", "memory"), ("USER.md", "user"), ("SOUL.md", "profile")]:
            filepath = self._memories_dir / filename
            if filepath.exists():
                file_entries = self.parse_memory_file(filepath, target)
                entries.extend(file_entries)
        
        # Load from state.db (more recent memories)
        if self._state_db.exists():
            try:
                db_entries = self._load_from_sqlite()
                entries.extend(db_entries)
            except Exception:
                pass  # SQLite might be locked or corrupted
        
        # Deduplicate by content hash
        seen = set()
        unique = []
        for entry in entries:
            content_hash = hash(entry.content[:200])
            if content_hash not in seen:
                seen.add(content_hash)
                unique.append(entry)
        
        return unique
    
    def _load_from_sqlite(self) -> List[MemoryEntry]:
        """Load memories from state.db sessions table."""
        entries = []
        
        with sqlite3.connect(str(self._state_db), timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            
            # Get sessions with messages
            cur = conn.execute(
                "SELECT id, messages_json FROM sessions WHERE messages_json IS NOT NULL AND messages_json != ''"
            )
            
            for row in cur.fetchall():
                session_id = row["id"]
                try:
                    messages = json.loads(row["messages_json"])
                    for msg in messages:
                        role = msg.get("role", "")
                        content = msg.get("content", "")
                        if content and role in ("user", "assistant"):
                            target = "user" if role == "user" else "memory"
                            entry = MemoryEntry(
                                id=uuid.uuid4().hex[:16],
                                target=target,
                                content=content[:2000],  # Limit size
                                profile="default",
                                session_id=session_id,
                                metadata={"source": "sqlite", "role": role},
                            )
                            entries.append(entry)
                except json.JSONDecodeError:
                    continue
        
        return entries
    
    def load_config(self) -> Optional[ConfigSnapshot]:
        """Load config.yaml."""
        config_path = self.config_dir / "config.yaml"
        if not config_path.exists():
            return None
        
        config_text = config_path.read_text(encoding="utf-8")
        
        return ConfigSnapshot(
            profile="default",
            config_yaml=config_text,
            hostname=_get_hostname(),
            device_id=f"hermes-{uuid.uuid4().hex[:8]}",
        )
    
    def load_skills(self) -> List[SkillSnapshot]:
        """Load custom skills from skills/ directory."""
        skills = []
        
        if not self._skills_dir.exists():
            return skills
        
        for skill_md in self._skills_dir.rglob("SKILL.md"):
            rel_path = skill_md.relative_to(self._skills_dir)
            skill_name = skill_md.parent.name
            
            try:
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
    
    def load_sessions(self) -> List[SessionSnapshot]:
        """Load sessions from state.db."""
        sessions = []
        
        if not self._state_db.exists():
            return sessions
        
        try:
            with sqlite3.connect(str(self._state_db), timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                
                cur = conn.execute("""
                    SELECT id, source, title, model, system_prompt, started_at, ended_at,
                           message_count, tool_call_count, input_tokens, output_tokens,
                           cwd, git_branch, git_repo_root, messages_json
                    FROM sessions
                    ORDER BY started_at DESC
                    LIMIT 500
                """)
                
                for row in cur.fetchall():
                    messages = []
                    if row["messages_json"]:
                        try:
                            messages = json.loads(row["messages_json"])
                        except json.JSONDecodeError:
                            pass
                    
                    sessions.append(SessionSnapshot(
                        id=row["id"],
                        source=row["source"] or "cli",
                        profile="default",
                        title=row["title"],
                        model=row["model"],
                        system_prompt=row["system_prompt"],
                        started_at=datetime.fromtimestamp(row["started_at"]) if row["started_at"] else None,
                        ended_at=datetime.fromtimestamp(row["ended_at"]) if row["ended_at"] else None,
                        message_count=row["message_count"] or 0,
                        tool_call_count=row["tool_call_count"] or 0,
                        input_tokens=row["input_tokens"] or 0,
                        output_tokens=row["output_tokens"] or 0,
                        cwd=row["cwd"],
                        git_branch=row["git_branch"],
                        git_repo_root=row["git_repo_root"],
                        messages=messages,
                    ))
        except Exception:
            pass
        
        return sessions
    
    def write_memories(self, entries: List[MemoryEntry]) -> int:
        """Write memories to MEMORY.md and USER.md."""
        memory_entries = [e.content for e in entries if e.target == "memory"]
        user_entries = [e.content for e in entries if e.target == "user"]
        profile_entries = [e.content for e in entries if e.target == "profile"]
        
        count = 0
        
        self._memories_dir.mkdir(parents=True, exist_ok=True)
        
        if memory_entries:
            (self._memories_dir / "MEMORY.md").write_text(
                "\n§\n".join(memory_entries) + "\n§\n",
                encoding="utf-8"
            )
            count += len(memory_entries)
        
        if user_entries:
            (self._memories_dir / "USER.md").write_text(
                "\n§\n".join(user_entries) + "\n§\n",
                encoding="utf-8"
            )
            count += len(user_entries)
        
        if profile_entries:
            (self._memories_dir / "SOUL.md").write_text(
                "\n§\n".join(profile_entries) + "\n§\n",
                encoding="utf-8"
            )
            count += len(profile_entries)
        
        return count
    
    def write_config(self, config: ConfigSnapshot) -> bool:
        """Write config.yaml."""
        try:
            config_path = self.config_dir / "config.yaml"
            config_path.write_text(config.config_yaml, encoding="utf-8")
            return True
        except Exception:
            return False
    
    def write_skills(self, skills: List[SkillSnapshot]) -> int:
        """Write skills to skills/ directory."""
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
        """Get Hermes profile identifier."""
        # Use the profile name from config
        try:
            import yaml
            config_path = self.config_dir / "config.yaml"
            if config_path.exists():
                config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
                return config.get("profile", "default")
        except Exception:
            pass
        return "default"
    
    def full_sync(self, client: CloudMemoryClient) -> "SyncResult":
        """Perform full sync to cloud."""
        from agent_cloud_memory.core import SyncResult
        
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
        
        # Sync sessions
        sessions = self.load_sessions()
        for session in sessions:
            try:
                client.sync_session(session)
                result.sessions_synced += 1
            except Exception as e:
                result.errors.append(f"Session sync error: {e}")
        
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
    
    def full_restore(self, client: CloudMemoryClient) -> "RestoreResult":
        """Perform full restore from cloud."""
        from agent_cloud_memory.core import RestoreResult
        
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