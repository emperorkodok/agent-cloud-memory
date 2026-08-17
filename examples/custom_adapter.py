#!/usr/bin/env python3
"""Example: Creating a custom adapter for a new framework."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_cloud_memory.adapters.base import FrameworkAdapter, register_adapter
from agent_cloud_memory.core import (
    MemoryEntry,
    SessionSnapshot,
    ConfigSnapshot,
    SkillSnapshot,
    CloudMemoryClient,
    SyncResult,
    RestoreResult,
)


@register_adapter
class MyCustomAgentAdapter(FrameworkAdapter):
    """Adapter for MyCustomAgent framework."""
    
    FRAMEWORK_NAME = "my-custom-agent"
    DISPLAY_NAME = "My Custom Agent"
    
    # File patterns this adapter handles
    MEMORY_FILES = ["memory.json", "user_prefs.json"]
    CONFIG_FILES = ["config.json"]
    SKILL_DIRS = ["plugins"]
    
    def __init__(self, config_dir: Path, data_dir: Optional[Path] = None):
        super().__init__(config_dir, data_dir)
        self._memory_file = config_dir / "memory.json"
        self._user_prefs_file = config_dir / "user_prefs.json"
        self._config_file = config_dir / "config.json"
        self._plugins_dir = config_dir / "plugins"
    
    def load_memories(self) -> List[MemoryEntry]:
        """Load memories from custom JSON format."""
        entries = []
        
        # Load memory.json
        if self._memory_file.exists():
            try:
                data = json.loads(self._memory_file.read_text())
                for item in data.get("entries", []):
                    entries.append(MemoryEntry(
                        id=uuid.uuid4().hex[:16],
                        target="memory",
                        content=item.get("content", ""),
                        profile="default",
                        metadata={"source": "memory.json", "tags": item.get("tags", [])},
                    ))
            except Exception:
                pass
        
        # Load user_prefs.json
        if self._user_prefs_file.exists():
            try:
                data = json.loads(self._user_prefs_file.read_text())
                for key, value in data.items():
                    entries.append(MemoryEntry(
                        id=uuid.uuid4().hex[:16],
                        target="user",
                        content=f"{key}: {value}",
                        profile="default",
                        metadata={"source": "user_prefs.json", "key": key},
                    ))
            except Exception:
                pass
        
        return entries
    
    def load_config(self) -> Optional[ConfigSnapshot]:
        """Load config from config.json."""
        if not self._config_file.exists():
            return None
        
        try:
            text = self._config_file.read_text()
            import yaml
            # Convert JSON to YAML for storage
            data = json.loads(text)
            return ConfigSnapshot(
                profile="default",
                config_yaml=yaml.dump(data, sort_keys=False),
            )
        except Exception:
            pass
        
        return None
    
    def load_skills(self) -> List[SkillSnapshot]:
        """Load plugins as skills."""
        skills = []
        
        if not self._plugins_dir.exists():
            return skills
        
        for plugin_dir in self._plugins_dir.iterdir():
            if not plugin_dir.is_dir():
                continue
            
            # Look for plugin manifest
            manifest = plugin_dir / "manifest.json"
            if manifest.exists():
                try:
                    data = json.loads(manifest.read_text())
                    skills.append(SkillSnapshot(
                        profile="default",
                        skill_path=f"plugins/{plugin_dir.name}/manifest.json",
                        skill_name=data.get("name", plugin_dir.name),
                        content=manifest.read_text(),
                        file_type="manifest.json",
                    ))
                except Exception:
                    continue
        
        return skills
    
    def load_sessions(self) -> List[SessionSnapshot]:
        """No session support in this example."""
        return []
    
    def write_memories(self, entries: List[MemoryEntry]) -> int:
        """Write memories back to JSON files."""
        memory_entries = []
        user_prefs = {}
        
        for entry in entries:
            if entry.target == "memory":
                memory_entries.append({
                    "content": entry.content,
                    "tags": entry.metadata.get("tags", []),
                })
            elif entry.target == "user":
                key = entry.metadata.get("key", entry.content.split(":")[0])
                user_prefs[key] = entry.content.split(":", 1)[-1].strip()
        
        count = 0
        
        if memory_entries:
            self._memory_file.write_text(
                json.dumps({"entries": memory_entries}, indent=2)
            )
            count += len(memory_entries)
        
        if user_prefs:
            self._user_prefs_file.write_text(
                json.dumps(user_prefs, indent=2)
            )
            count += len(user_prefs)
        
        return count
    
    def write_config(self, config: ConfigSnapshot) -> bool:
        """Write config back to config.json."""
        try:
            import yaml
            data = yaml.safe_load(config.config_yaml)
            if isinstance(data, dict):
                self._config_file.write_text(
                    json.dumps(data, indent=2)
                )
                return True
        except Exception:
            pass
        return False
    
    def write_skills(self, skills: List[SkillSnapshot]) -> int:
        """Write plugins from skills."""
        count = 0
        
        for skill in skills:
            try:
                plugin_path = self._plugins_dir / skill.skill_path.replace("manifest.json", "")
                plugin_path.mkdir(parents=True, exist_ok=True)
                (plugin_path / "manifest.json").write_text(skill.content)
                count += 1
            except Exception:
                continue
        
        return count
    
    def get_profile_identifier(self) -> str:
        return "default"


def main():
    """Demo the custom adapter."""
    print("🔧 Custom Adapter Example")
    print("=" * 40)
    
    # The adapter is auto-registered via @register_adapter
    # Now you can use it like any other adapter:
    
    from agent_cloud_memory.adapters import get_adapter_by_name
    
    adapter_class = get_adapter_by_name("my-custom-agent")
    if adapter_class:
        print(f"✓ Custom adapter registered: {adapter_class.DISPLAY_NAME}")
        
        # Usage:
        # adapter = adapter_class(Path.home() / ".my-custom-agent")
        # adapter.set_client(client)
        # result = adapter.full_sync(client)
    else:
        print("✗ Adapter not found")
    
    # List all available adapters
    from agent_cloud_memory.adapters import list_available_adapters
    print("\nAvailable adapters:")
    for name in list_available_adapters():
        print(f"  • {name}")


if __name__ == "__main__":
    main()