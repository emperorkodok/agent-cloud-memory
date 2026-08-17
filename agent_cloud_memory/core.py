"""Core abstractions for agent-cloud-memory."""

from __future__ import annotations

import json
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from contextlib import contextmanager

from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential


def _json_default(obj):
    """JSON serializer for objects not serializable by default json code."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


# ─── Data Models ──────────────────────────────────────────────────────────

class MemoryEntry(BaseModel):
    """A single memory entry."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    target: str = "memory"  # "memory" | "user" | "profile"
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    profile: str = "default"
    session_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "target": self.target,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "profile": self.profile,
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        data = data.copy()
        for field_name in ("created_at", "updated_at"):
            if field_name in data and isinstance(data[field_name], str):
                data[field_name] = datetime.fromisoformat(data[field_name])
        return cls(**data)


class SessionSnapshot(BaseModel):
    """Full session snapshot for persistence."""
    id: str
    source: str = "cli"
    profile: str = "default"
    title: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    message_count: int = 0
    tool_call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cwd: Optional[str] = None
    git_branch: Optional[str] = None
    git_repo_root: Optional[str] = None
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    synced_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConfigSnapshot(BaseModel):
    """Configuration snapshot."""
    profile: str = "default"
    config_yaml: str
    snapshot_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    hostname: Optional[str] = None
    device_id: Optional[str] = None


class SkillSnapshot(BaseModel):
    """Skill file snapshot."""
    profile: str = "default"
    skill_path: str
    skill_name: str
    content: str
    file_type: str = "SKILL.md"
    synced_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SyncResult(BaseModel):
    """Result of a sync operation."""
    memories_synced: int = 0
    sessions_synced: int = 0
    config_synced: bool = False
    skills_synced: int = 0
    errors: List[str] = Field(default_factory=list)


class RestoreResult(BaseModel):
    """Result of a restore operation."""
    memories_restored: int = 0
    sessions_restored: int = 0
    config_restored: bool = False
    skills_restored: int = 0
    errors: List[str] = Field(default_factory=list)


# ─── Core Abstract Interface ──────────────────────────────────────────────

class MemoryProvider(ABC):
    """Abstract base class for memory backends."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier."""
        pass
    
    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> None:
        """Initialize the provider with configuration."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is configured and ready."""
        pass
    
    @abstractmethod
    def remember(self, entry: MemoryEntry) -> str:
        """Store a memory entry. Returns entry ID."""
        pass
    
    @abstractmethod
    def search(self, query: str, top_k: int = 10, profile: Optional[str] = None) -> List[MemoryEntry]:
        """Search memories by semantic query."""
        pass
    
    @abstractmethod
    def forget(self, memory_id: str, profile: Optional[str] = None) -> bool:
        """Delete a memory by ID."""
        pass
    
    @abstractmethod
    def list_memories(self, profile: Optional[str] = None, target: Optional[str] = None, limit: int = 100) -> List[MemoryEntry]:
        """List memories with optional filters."""
        pass
    
    @abstractmethod
    def get_profile(self, profile: Optional[str] = None) -> List[MemoryEntry]:
        """Get user profile memories."""
        pass
    
    @abstractmethod
    def sync_session(self, session: SessionSnapshot) -> bool:
        """Sync a session snapshot."""
        pass
    
    @abstractmethod
    def sync_config(self, config: ConfigSnapshot) -> bool:
        """Sync configuration snapshot."""
        pass
    
    @abstractmethod
    def sync_skill(self, skill: SkillSnapshot) -> bool:
        """Sync skill snapshot."""
        pass
    
    @abstractmethod
    def sync_turn(self, user_content: str, assistant_content: str, session_id: str, profile: str) -> None:
        """Sync a conversation turn (real-time)."""
        pass
    
    @abstractmethod
    def restore_memories(self, profile: Optional[str] = None) -> List[MemoryEntry]:
        """Restore all memories from cloud."""
        pass
    
    @abstractmethod
    def restore_config(self, profile: Optional[str] = None) -> Optional[ConfigSnapshot]:
        """Restore latest config."""
        pass
    
    @abstractmethod
    def restore_skills(self, profile: Optional[str] = None) -> List[SkillSnapshot]:
        """Restore all skills."""
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Close connections and cleanup."""
        pass


# ─── PostgreSQL Backend ───────────────────────────────────────────────────

SCHEMA_SQL = [
    # Memories table
    """
    CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY,
        target TEXT NOT NULL DEFAULT 'memory',
        content TEXT NOT NULL,
        metadata JSONB DEFAULT '{}',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        profile TEXT NOT NULL DEFAULT 'default',
        session_id TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_memories_target ON memories(target)",
    "CREATE INDEX IF NOT EXISTS idx_memories_profile ON memories(profile)",
    "CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_memories_content_gin ON memories USING gin(to_tsvector('english', content))",
    
    # Sessions table
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        source TEXT NOT NULL DEFAULT 'cli',
        profile TEXT NOT NULL DEFAULT 'default',
        title TEXT,
        model TEXT,
        system_prompt TEXT,
        started_at TIMESTAMPTZ,
        ended_at TIMESTAMPTZ,
        message_count INTEGER DEFAULT 0,
        tool_call_count INTEGER DEFAULT 0,
        input_tokens INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0,
        cwd TEXT,
        git_branch TEXT,
        git_repo_root TEXT,
        messages_json TEXT,
        synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_sessions_profile ON sessions(profile)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at DESC)",
    
    # Config snapshots
    """
    CREATE TABLE IF NOT EXISTS config_snapshots (
        id SERIAL PRIMARY KEY,
        profile TEXT NOT NULL DEFAULT 'default',
        config_yaml TEXT NOT NULL,
        snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        hostname TEXT,
        device_id TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_config_profile ON config_snapshots(profile)",
    "CREATE INDEX IF NOT EXISTS idx_config_time ON config_snapshots(snapshot_at DESC)",
    
    # Skill snapshots
    """
    CREATE TABLE IF NOT EXISTS skill_snapshots (
        id SERIAL PRIMARY KEY,
        profile TEXT NOT NULL DEFAULT 'default',
        skill_path TEXT NOT NULL,
        skill_name TEXT NOT NULL,
        content TEXT NOT NULL,
        file_type TEXT NOT NULL DEFAULT 'SKILL.md',
        synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (profile, skill_path)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_skills_profile ON skill_snapshots(profile)",
]


def _parse_metadata(value):
    """Parse metadata from PostgreSQL JSONB - handles both dict and string."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    return json.loads(value)


class PostgreSQLBackend(MemoryProvider):
    """PostgreSQL cloud memory backend."""
    
    def __init__(self):
        self._dsn: Optional[str] = None
        self._schema: str = "agent_cloud_memory"
        self._pool = None
        self._profile: str = "default"
        self._initialized: bool = False
    
    @property
    def name(self) -> str:
        return "postgresql"
    
    def initialize(self, config: Dict[str, Any]) -> None:
        self._dsn = config.get("dsn") or os.environ.get("ACM_POSTGRES_DSN") or os.environ.get("POSTGRES_DSN")
        self._schema = config.get("schema", "agent_cloud_memory")
        self._profile = config.get("profile", "default")
        
        if not self._dsn:
            raise ValueError("PostgreSQL DSN required. Set ACM_POSTGRES_DSN or pass in config.")
        
        self._init_pool()
        self._ensure_schema()
        self._initialized = True
    
    def _init_pool(self):
        import psycopg
        from psycopg_pool import ConnectionPool
        
        self._pool = ConnectionPool(
            conninfo=self._dsn,
            min_size=1,
            max_size=5,
            timeout=30,
        )
    
    def _ensure_schema(self):
        with self._pool.connection() as conn:
            conn.execute(f"CREATE SCHEMA IF NOT EXISTS {self._schema}")
            conn.execute(f"SET search_path TO {self._schema}")
            for stmt in SCHEMA_SQL:
                conn.execute(stmt)
            conn.commit()
    
    def is_available(self) -> bool:
        if not self._dsn:
            return False
        if not self._initialized:
            try:
                self.initialize({})
            except Exception:
                return False
        return True
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    def remember(self, entry: MemoryEntry) -> str:
        if not self._initialized:
            self.initialize({})
        
        with self._pool.connection() as conn:
            conn.execute(f"SET search_path TO {self._schema}")
            conn.execute(
                """
                INSERT INTO memories (id, target, content, metadata, created_at, updated_at, profile, session_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    content = EXCLUDED.content,
                    metadata = EXCLUDED.metadata,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    entry.id,
                    entry.target,
                    entry.content,
                    json.dumps(entry.metadata),
                    entry.created_at,
                    entry.updated_at,
                    entry.profile,
                    entry.session_id,
                ),
            )
            conn.commit()
        return entry.id
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    def search(self, query: str, top_k: int = 10, profile: Optional[str] = None) -> List[MemoryEntry]:
        if not self._initialized:
            self.initialize({})
        
        profile = profile or self._profile
        
        with self._pool.connection() as conn:
            conn.execute(f"SET search_path TO {self._schema}")
            cur = conn.execute(
                """
                SELECT id, target, content, metadata, created_at, updated_at, profile, session_id,
                       ts_rank(to_tsvector('english', content), plainto_tsquery('english', %s)) AS rank
                FROM memories
                WHERE profile = %s
                AND to_tsvector('english', content) @@ plainto_tsquery('english', %s)
                ORDER BY rank DESC
                LIMIT %s
                """,
                (query, profile, query, top_k),
            )
            rows = cur.fetchall()
        
        return [
            MemoryEntry(
                id=row[0],
                target=row[1],
                content=row[2],
                metadata=_parse_metadata(row[3]),
                created_at=row[4],
                updated_at=row[5],
                profile=row[6],
                session_id=row[7],
            )
            for row in rows
        ]
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    def forget(self, memory_id: str, profile: Optional[str] = None) -> bool:
        if not self._initialized:
            self.initialize({})
        
        profile = profile or self._profile
        
        with self._pool.connection() as conn:
            conn.execute(f"SET search_path TO {self._schema}")
            cur = conn.execute(
                "DELETE FROM memories WHERE id = %s AND profile = %s",
                (memory_id, profile),
            )
            conn.commit()
            return cur.rowcount > 0
    
    def list_memories(self, profile: Optional[str] = None, target: Optional[str] = None, limit: int = 100) -> List[MemoryEntry]:
        if not self._initialized:
            self.initialize({})
        
        profile = profile or self._profile
        
        with self._pool.connection() as conn:
            conn.execute(f"SET search_path TO {self._schema}")
            if target:
                cur = conn.execute(
                    "SELECT id, target, content, metadata, created_at, updated_at, profile, session_id FROM memories WHERE profile = %s AND target = %s ORDER BY updated_at DESC LIMIT %s",
                    (profile, target, limit),
                )
            else:
                cur = conn.execute(
                    "SELECT id, target, content, metadata, created_at, updated_at, profile, session_id FROM memories WHERE profile = %s ORDER BY updated_at DESC LIMIT %s",
                    (profile, limit),
                )
            rows = cur.fetchall()
        
        return [
            MemoryEntry(
                id=row[0],
                target=row[1],
                content=row[2],
                metadata=_parse_metadata(row[3]),
                created_at=row[4],
                updated_at=row[5],
                profile=row[6],
                session_id=row[7],
            )
            for row in rows
        ]
    
    def get_profile(self, profile: Optional[str] = None) -> List[MemoryEntry]:
        return self.list_memories(profile=profile or self._profile, target="user", limit=50)
    
    def sync_session(self, session: SessionSnapshot) -> bool:
        if not self._initialized:
            self.initialize({})
        
        import json
        with self._pool.connection() as conn:
            conn.execute(f"SET search_path TO {self._schema}")
            conn.execute(
                """
                INSERT INTO sessions (
                    id, source, profile, title, model, system_prompt,
                    started_at, ended_at, message_count, tool_call_count,
                    input_tokens, output_tokens, cwd, git_branch,
                    git_repo_root, messages_json, synced_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, NOW()
                )
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    ended_at = EXCLUDED.ended_at,
                    message_count = EXCLUDED.message_count,
                    messages_json = EXCLUDED.messages_json,
                    synced_at = NOW()
                """,
                (
                    session.id,
                    session.source,
                    session.profile,
                    session.title,
                    session.model,
                    session.system_prompt,
                    session.started_at,
                    session.ended_at,
                    session.message_count,
                    session.tool_call_count,
                    session.input_tokens,
                    session.output_tokens,
                    session.cwd,
                    session.git_branch,
                    session.git_repo_root,
                    json.dumps(session.messages, default=_json_default),
                ),
            )
            conn.commit()
        return True
    
    def sync_config(self, config: ConfigSnapshot) -> bool:
        if not self._initialized:
            self.initialize({})
        
        with self._pool.connection() as conn:
            conn.execute(f"SET search_path TO {self._schema}")
            conn.execute(
                """
                INSERT INTO config_snapshots (profile, config_yaml, snapshot_at, hostname, device_id)
                VALUES (%s, %s, NOW(), %s, %s)
                """,
                (config.profile, config.config_yaml, config.hostname, config.device_id),
            )
            conn.commit()
        return True
    
    def sync_skill(self, skill: SkillSnapshot) -> bool:
        if not self._initialized:
            self.initialize({})
        
        with self._pool.connection() as conn:
            conn.execute(f"SET search_path TO {self._schema}")
            conn.execute(
                """
                INSERT INTO skill_snapshots (profile, skill_path, skill_name, content, file_type, synced_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (profile, skill_path) DO UPDATE SET
                    content = EXCLUDED.content,
                    file_type = EXCLUDED.file_type,
                    synced_at = NOW()
                """,
                (skill.profile, skill.skill_path, skill.skill_name, skill.content, skill.file_type),
            )
            conn.commit()
        return True
    
    def sync_turn(self, user_content: str, assistant_content: str, session_id: str, profile: str) -> None:
        """Real-time turn sync - store as memories."""
        if not user_content:
            return
        
        # Store user message as memory
        self.remember(MemoryEntry(
            target="memory",
            content=f"[User] {user_content}",
            profile=profile,
            session_id=session_id,
        ))
        
        if assistant_content:
            self.remember(MemoryEntry(
                target="memory",
                content=f"[Assistant] {assistant_content}",
                profile=profile,
                session_id=session_id,
            ))
    
    def restore_memories(self, profile: Optional[str] = None) -> List[MemoryEntry]:
        return self.list_memories(profile=profile or self._profile, limit=10000)
    
    def restore_config(self, profile: Optional[str] = None) -> Optional[ConfigSnapshot]:
        if not self._initialized:
            self.initialize({})
        
        profile = profile or self._profile
        
        with self._pool.connection() as conn:
            conn.execute(f"SET search_path TO {self._schema}")
            cur = conn.execute(
                "SELECT config_yaml, snapshot_at, hostname, device_id FROM config_snapshots WHERE profile = %s ORDER BY snapshot_at DESC LIMIT 1",
                (profile,),
            )
            row = cur.fetchone()
        
        if not row:
            return None
        
        return ConfigSnapshot(
            profile=profile,
            config_yaml=row[0],
            snapshot_at=row[1],
            hostname=row[2],
            device_id=row[3],
        )
    
    def restore_skills(self, profile: Optional[str] = None) -> List[SkillSnapshot]:
        if not self._initialized:
            self.initialize({})
        
        profile = profile or self._profile
        
        with self._pool.connection() as conn:
            conn.execute(f"SET search_path TO {self._schema}")
            cur = conn.execute(
                "SELECT skill_path, skill_name, content, file_type, synced_at FROM skill_snapshots WHERE profile = %s",
                (profile,),
            )
            rows = cur.fetchall()
        
        return [
            SkillSnapshot(
                profile=profile,
                skill_path=row[0],
                skill_name=row[1],
                content=row[2],
                file_type=row[3],
                synced_at=row[4],
            )
            for row in rows
        ]
    
    def close(self) -> None:
        if self._pool:
            self._pool.close()
            self._pool = None
        self._initialized = False


# ─── Cloud Memory Client (High-level API) ─────────────────────────────────

class CloudMemoryClient:
    """High-level client for cloud memory operations."""
    
    def __init__(self, provider: Optional[MemoryProvider] = None, config: Optional[Dict[str, Any]] = None):
        self._provider = provider or PostgreSQLBackend()
        self._config = config or {}
        self._initialized = False
    
    def initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
        if config:
            self._config.update(config)
        self._provider.initialize(self._config)
        self._initialized = True
    
    @property
    def provider(self) -> MemoryProvider:
        return self._provider
    
    def remember(self, content: str, target: str = "memory", profile: Optional[str] = None, session_id: Optional[str] = None, metadata: Optional[Dict] = None) -> str:
        """Store a memory entry."""
        if not self._initialized:
            self.initialize()
        
        entry = MemoryEntry(
            target=target,
            content=content,
            profile=profile or self._config.get("profile", "default"),
            session_id=session_id,
            metadata=metadata or {},
        )
        return self._provider.remember(entry)
    
    def search(self, query: str, top_k: int = 10, profile: Optional[str] = None) -> List[MemoryEntry]:
        """Search memories."""
        if not self._initialized:
            self.initialize()
        return self._provider.search(query, top_k, profile)
    
    def forget(self, memory_id: str, profile: Optional[str] = None) -> bool:
        """Delete a memory."""
        if not self._initialized:
            self.initialize()
        return self._provider.forget(memory_id, profile)
    
    def list(self, profile: Optional[str] = None, target: Optional[str] = None, limit: int = 100) -> List[MemoryEntry]:
        """List memories."""
        if not self._initialized:
            self.initialize()
        return self._provider.list_memories(profile, target, limit)
    
    def profile(self, profile: Optional[str] = None) -> List[MemoryEntry]:
        """Get user profile."""
        if not self._initialized:
            self.initialize()
        return self._provider.get_profile(profile)
    
    def sync_session(self, session: SessionSnapshot) -> bool:
        if not self._initialized:
            self.initialize()
        return self._provider.sync_session(session)
    
    def sync_config(self, config: ConfigSnapshot) -> bool:
        if not self._initialized:
            self.initialize()
        return self._provider.sync_config(config)
    
    def sync_skill(self, skill: SkillSnapshot) -> bool:
        if not self._initialized:
            self.initialize()
        return self._provider.sync_skill(skill)
    
    def sync_turn(self, user_content: str, assistant_content: str, session_id: str, profile: str) -> None:
        if not self._initialized:
            self.initialize()
        self._provider.sync_turn(user_content, assistant_content, session_id, profile)
    
    def restore_memories(self, profile: Optional[str] = None) -> List[MemoryEntry]:
        if not self._initialized:
            self.initialize()
        return self._provider.restore_memories(profile)
    
    def restore_config(self, profile: Optional[str] = None) -> Optional[ConfigSnapshot]:
        if not self._initialized:
            self.initialize()
        return self._provider.restore_config(profile)
    
    def restore_skills(self, profile: Optional[str] = None) -> List[SkillSnapshot]:
        if not self._initialized:
            self.initialize()
        return self._provider.restore_skills(profile)
    
    def full_sync(self, profile: Optional[str] = None) -> SyncResult:
        """Perform a full sync of all local state to cloud."""
        # This would be implemented by adapters
        raise NotImplementedError("Full sync requires framework-specific adapter")
    
    def full_restore(self, profile: Optional[str] = None) -> RestoreResult:
        """Perform a full restore from cloud to local."""
        # This would be implemented by adapters
        raise NotImplementedError("Full restore requires framework-specific adapter")
    
    def close(self) -> None:
        self._provider.close()
        self._initialized = False
    
    def __enter__(self) -> "CloudMemoryClient":
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()