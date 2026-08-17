"""Tests for agent-cloud-memory core module."""

from __future__ import annotations

import pytest
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

from agent_cloud_memory.core import (
    MemoryEntry,
    SessionSnapshot,
    ConfigSnapshot,
    SkillSnapshot,
    SyncResult,
    RestoreResult,
    PostgreSQLBackend,
)


class TestDataModels:
    """Test Pydantic data models."""
    
    def test_memory_entry_creation(self):
        entry = MemoryEntry(
            target="memory",
            content="Test memory content",
            profile="test",
            session_id="session-123",
        )
        assert entry.target == "memory"
        assert entry.content == "Test memory content"
        assert entry.profile == "test"
        assert entry.session_id == "session-123"
        assert entry.id  # Auto-generated
    
    def test_memory_entry_serialization(self):
        entry = MemoryEntry(
            target="user",
            content="User preference",
            metadata={"source": "test"},
        )
        data = entry.to_dict()
        
        assert data["target"] == "user"
        assert data["content"] == "User preference"
        assert data["metadata"]["source"] == "test"
        assert "created_at" in data
        assert "updated_at" in data
    
    def test_memory_entry_deserialization(self):
        original = MemoryEntry(
            target="memory",
            content="Test",
            profile="default",
        )
        data = original.to_dict()
        restored = MemoryEntry.from_dict(data)
        
        assert restored.id == original.id
        assert restored.target == original.target
        assert restored.content == original.content
        assert restored.profile == original.profile
    
    def test_session_snapshot(self):
        session = SessionSnapshot(
            id="test-session",
            source="cli",
            title="Test Session",
            message_count=10,
        )
        assert session.id == "test-session"
        assert session.message_count == 10
    
    def test_config_snapshot(self):
        config = ConfigSnapshot(
            profile="test",
            config_yaml="model: test\nprovider: test",
        )
        assert config.profile == "test"
        assert "model: test" in config.config_yaml
    
    def test_skill_snapshot(self):
        skill = SkillSnapshot(
            profile="test",
            skill_path="skills/test/SKILL.md",
            skill_name="test",
            content="# Test Skill",
        )
        assert skill.skill_name == "test"
        assert skill.skill_path == "skills/test/SKILL.md"


class TestSyncRestoreResults:
    """Test result aggregation."""
    
    def test_sync_result_aggregation(self):
        r1 = SyncResult(memories_synced=5, sessions_synced=2, config_synced=True)
        r2 = SyncResult(memories_synced=3, sessions_synced=1, skills_synced=2)
        
        # Manual aggregation (what the sync script does)
        total = SyncResult()
        total.memories_synced = r1.memories_synced + r2.memories_synced
        total.sessions_synced = r1.sessions_synced + r2.sessions_synced
        total.config_synced = r1.config_synced or r2.config_synced
        total.skills_synced = r1.skills_synced + r2.skills_synced
        
        assert total.memories_synced == 8
        assert total.sessions_synced == 3
        assert total.config_synced is True
        assert total.skills_synced == 2
    
    def test_restore_result_aggregation(self):
        r1 = RestoreResult(memories_restored=10, config_restored=True)
        r2 = RestoreResult(memories_restored=5, skills_restored=3)
        
        total = RestoreResult()
        total.memories_restored = r1.memories_restored + r2.memories_restored
        total.config_restored = r1.config_restored or r2.config_restored
        total.skills_restored = r1.skills_restored + r2.skills_restored
        
        assert total.memories_restored == 15
        assert total.config_restored is True
        assert total.skills_restored == 3


class TestPostgreSQLBackend:
    """Test PostgreSQL backend (requires running PostgreSQL)."""
    
    @pytest.fixture
    def db_config(self):
        """PostgreSQL test configuration - uses environment variables."""
        import os
        dsn = os.environ.get("TEST_POSTGRES_DSN")
        if not dsn:
            pytest.skip("TEST_POSTGRES_DSN not set")
        return {"dsn": dsn, "schema": "test_agent_cloud_memory", "profile": "test"}
    
    def test_backend_initialization(self, db_config):
        backend = PostgreSQLBackend()
        backend.initialize(db_config)
        assert backend.is_available()
        backend.close()
    
    def test_remember_and_search(self, db_config):
        backend = PostgreSQLBackend()
        backend.initialize(db_config)
        
        try:
            # Store a memory
            entry = MemoryEntry(
                target="memory",
                content="Test memory for search",
                profile="test",
                metadata={"test": True},
            )
            entry_id = backend.remember(entry)
            assert entry_id == entry.id
            
            # Search for it
            results = backend.search("test memory", top_k=5, profile="test")
            assert len(results) >= 1
            assert "Test memory" in results[0].content
            
            # List memories
            listed = backend.list_memories(profile="test", limit=10)
            assert len(listed) >= 1
            
            # Delete it
            deleted = backend.forget(entry_id, profile="test")
            assert deleted is True
            
            # Verify deleted
            results = backend.search("test memory", top_k=5, profile="test")
            assert all(r.id != entry_id for r in results)
        finally:
            backend.close()
    
    def test_session_sync(self, db_config):
        backend = PostgreSQLBackend()
        backend.initialize(db_config)
        
        try:
            session = SessionSnapshot(
                id="test-session-123",
                source="test",
                title="Test Session",
                message_count=5,
                messages=[{"role": "user", "content": "Hello"}],
            )
            result = backend.sync_session(session)
            assert result is True
        finally:
            backend.close()
    
    def test_config_skill_sync(self, db_config):
        backend = PostgreSQLBackend()
        backend.initialize(db_config)
        
        try:
            # Config
            config = ConfigSnapshot(
                profile="test",
                config_yaml="test: config",
            )
            result = backend.sync_config(config)
            assert result is True
            
            # Restore config
            restored = backend.restore_config(profile="test")
            assert restored is not None
            assert restored.config_yaml == "test: config"
            
            # Skill
            skill = SkillSnapshot(
                profile="test",
                skill_path="skills/test/SKILL.md",
                skill_name="test",
                content="# Test Skill",
            )
            result = backend.sync_skill(skill)
            assert result is True
            
            # Restore skills
            skills = backend.restore_skills(profile="test")
            assert len(skills) >= 1
            assert skills[0].skill_name == "test"
        finally:
            backend.close()


class TestCloudMemoryClient:
    """Test high-level CloudMemoryClient."""
    
    @pytest.fixture
    def client(self):
        import os
        dsn = os.environ.get("TEST_POSTGRES_DSN")
        if not dsn:
            pytest.skip("TEST_POSTGRES_DSN not set")
        
        from agent_cloud_memory.core import CloudMemoryClient
        
        client = CloudMemoryClient()
        client.initialize({
            "dsn": dsn,
            "schema": "test_agent_cloud_memory",
            "profile": "test_client",
        })
        yield client
        client.close()
    
    def test_remember_search_forget(self, client):
        # Remember
        entry_id = client.remember(
            content="Client test memory",
            target="memory",
            profile="test_client",
            metadata={"via": "client"},
        )
        assert entry_id
        
        # Search
        results = client.search("Client test", top_k=5, profile="test_client")
        assert len(results) >= 1
        assert results[0].content == "Client test memory"
        
        # Profile (user memories)
        client.remember("User preference", target="user", profile="test_client")
        profile = client.profile(profile="test_client")
        assert len(profile) >= 1
        
        # List
        listed = client.list(profile="test_client", limit=10)
        assert len(listed) >= 1
        
        # Forget
        deleted = client.forget(entry_id, profile="test_client")
        assert deleted is True
    
    def test_context_manager(self):
        import os
        dsn = os.environ.get("TEST_POSTGRES_DSN")
        if not dsn:
            pytest.skip("TEST_POSTGRES_DSN not set")
        
        from agent_cloud_memory.core import CloudMemoryClient
        
        with CloudMemoryClient() as client:
            client.initialize({
                "dsn": dsn,
                "schema": "test_agent_cloud_memory",
                "profile": "test_cm",
            })
            entry_id = client.remember("Context manager test", profile="test_cm")
            assert entry_id
        
        # Client should be closed after context


class TestAdapters:
    """Test framework adapters (without cloud)."""
    
    def test_hermes_adapter_loads(self, tmp_path):
        from agent_cloud_memory.adapters import HermesAdapter
        
        # Create fake Hermes structure
        hermes_dir = tmp_path / ".hermes"
        hermes_dir.mkdir()
        (hermes_dir / "memories").mkdir()
        (hermes_dir / "skills").mkdir()
        
        (hermes_dir / "memories" / "MEMORY.md").write_text("Test memory\n§\nAnother\n§\n")
        (hermes_dir / "memories" / "USER.md").write_text("User pref\n§\n")
        
        skill_dir = hermes_dir / "skills" / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Test Skill\n\nContent")
        
        adapter = HermesAdapter(hermes_dir)
        
        memories = adapter.load_memories()
        assert len(memories) >= 3  # 2 from MEMORY.md + 1 from USER.md
        
        skills = adapter.load_skills()
        assert len(skills) == 1
        assert skills[0].skill_name == "test-skill"
        
        config = adapter.load_config()
        # No config.yaml created, so None
    
    def test_openclaw_adapter_loads(self, tmp_path):
        from agent_cloud_memory.adapters import OpenClawAdapter
        
        openclaw_dir = tmp_path / ".openclaw"
        openclaw_dir.mkdir()
        (openclaw_dir / "MEMORY.md").write_text("OpenClaw memory\n§\n")
        (openclaw_dir / "USER.md").write_text("User pref\n§\n")
        
        skills_dir = openclaw_dir / "skills"
        skills_dir.mkdir()
        (skills_dir / "test").mkdir()
        (skills_dir / "test" / "SKILL.md").write_text("# Test")
        
        adapter = OpenClawAdapter(openclaw_dir)
        
        memories = adapter.load_memories()
        assert len(memories) >= 2
        
        skills = adapter.load_skills()
        assert len(skills) == 1
    
    def test_claude_code_adapter_loads(self, tmp_path):
        from agent_cloud_memory.adapters import ClaudeCodeAdapter
        
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "CLAUDE.md").write_text("Claude memory\n§\n")
        
        skills_dir = claude_dir / "skills"
        skills_dir.mkdir()
        (skills_dir / "test").mkdir()
        (skills_dir / "test" / "SKILL.md").write_text("# Test")
        
        adapter = ClaudeCodeAdapter(claude_dir)
        
        memories = adapter.load_memories()
        assert len(memories) >= 1
        
        skills = adapter.load_skills()
        assert len(skills) == 1
    
    def test_codex_adapter_loads(self, tmp_path):
        from agent_cloud_memory.adapters import CodexAdapter
        
        codex_dir = tmp_path / ".codex"
        codex_dir.mkdir()
        (codex_dir / "AGENTS.md").write_text("Codex memory\n§\n")
        
        skills_dir = codex_dir / "skills"
        skills_dir.mkdir()
        (skills_dir / "test").mkdir()
        (skills_dir / "test" / "SKILL.md").write_text("# Test")
        
        adapter = CodexAdapter(codex_dir)
        
        memories = adapter.load_memories()
        assert len(memories) >= 1
        
        skills = adapter.load_skills()
        assert len(skills) == 1
    
    def test_adapter_registry(self):
        from agent_cloud_memory.adapters import ADAPTER_REGISTRY, get_adapter_by_name
        
        assert "hermes" in ADAPTER_REGISTRY
        assert "openclaw" in ADAPTER_REGISTRY
        assert "claude-code" in ADAPTER_REGISTRY
        assert "codex" in ADAPTER_REGISTRY
        
        assert get_adapter_by_name("hermes") is not None
        assert get_adapter_by_name("unknown") is None
    
    def test_framework_detector(self, tmp_path):
        from agent_cloud_memory.adapters import FrameworkDetector
        
        # Create fake frameworks
        (tmp_path / ".hermes").mkdir()
        (tmp_path / ".openclaw").mkdir()
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".codex").mkdir()
        
        detected = FrameworkDetector.detect_all([tmp_path])
        
        names = [fw.name for fw in detected]
        assert "hermes" in names
        assert "openclaw" in names
        assert "claude-code" in names
        assert "codex" in names
        
        primary = FrameworkDetector.detect_primary([tmp_path])
        assert primary is not None
        assert primary.name in names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])