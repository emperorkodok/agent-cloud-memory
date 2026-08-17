#!/usr/bin/env python3
"""agent-cloud-memory - Sync local frameworks to cloud."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from agent_cloud_memory.adapters import FrameworkDetector, get_adapter_for_path, ADAPTER_REGISTRY
from agent_cloud_memory.core import CloudMemoryClient, SyncResult


def load_config() -> dict:
    """Load configuration from ~/.config/agent-cloud-memory/config.yaml and .env."""
    import yaml
    
    config_dir = Path.home() / ".config" / "agent-cloud-memory"
    config = {
        "postgresql": {"dsn": "", "schema": "agent_cloud_memory"},
        "profile": "default",
    }
    
    config_file = config_dir / "config.yaml"
    if config_file.exists():
        with open(config_file, encoding="utf-8") as f:
            config.update(yaml.safe_load(f) or {})
    
    env_file = config_dir / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                if key == "ACM_POSTGRES_DSN":
                    config["postgresql"]["dsn"] = value
                elif key == "ACM_POSTGRES_SCHEMA":
                    config["postgresql"]["schema"] = value
                elif key == "ACM_PROFILE":
                    config["profile"] = value
    
    # Also check environment variables
    if os.environ.get("ACM_POSTGRES_DSN"):
        config["postgresql"]["dsn"] = os.environ["ACM_POSTGRES_DSN"]
    if os.environ.get("ACM_POSTGRES_SCHEMA"):
        config["postgresql"]["schema"] = os.environ["ACM_POSTGRES_SCHEMA"]
    if os.environ.get("ACM_PROFILE"):
        config["profile"] = os.environ["ACM_PROFILE"]
    
    return config


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync local frameworks to cloud")
    parser.add_argument("--framework", choices=list(ADAPTER_REGISTRY.keys()), help="Specific framework to sync")
    parser.add_argument("--all", action="store_true", help="Sync all detected frameworks")
    parser.add_argument("--memories", action="store_true", help="Sync only memories")
    parser.add_argument("--sessions", action="store_true", help="Sync only sessions")
    parser.add_argument("--config", action="store_true", help="Sync only config")
    parser.add_argument("--skills", action="store_true", help="Sync only skills")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be synced without writing")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()
    
    # Load config
    config = load_config()
    
    if not config["postgresql"]["dsn"]:
        print("✗ Not configured. Run 'acm-setup' first.")
        return 1
    
    # Initialize client
    client = CloudMemoryClient()
    try:
        client.initialize(config["postgresql"])
    except Exception as e:
        print(f"✗ Failed to connect: {e}")
        return 1
    
    # Determine frameworks to sync
    if args.framework:
        frameworks = [args.framework]
    elif args.all:
        detected = FrameworkDetector.detect_all([Path.home()])
        frameworks = [fw.name for fw in detected]
        if not frameworks:
            print("No frameworks detected.")
            return 1
    else:
        # Default: detect primary
        primary = FrameworkDetector.detect_primary([Path.home()])
        if not primary:
            print("No framework detected. Use --framework or --all.")
            return 1
        frameworks = [primary.name]
    
    # Determine what to sync
    sync_types = []
    if args.memories: sync_types.append("memories")
    if args.sessions: sync_types.append("sessions")
    if args.config: sync_types.append("config")
    if args.skills: sync_types.append("skills")
    if not sync_types:
        sync_types = ["memories", "sessions", "config", "skills"]
    
    # Sync each framework
    total_result = SyncResult()
    
    for fw_name in frameworks:
        adapter_class = ADAPTER_REGISTRY.get(fw_name)
        if not adapter_class:
            print(f"⚠ Unknown framework: {fw_name}")
            continue
        
        # Get config dir for this framework
        detected = FrameworkDetector.detect_primary([Path.home()])
        if detected and detected.name == fw_name:
            adapter = adapter_class(detected.config_dir, detected.data_dir)
        else:
            # Fallback to default locations
            default_paths = {
                "hermes": Path.home() / ".hermes",
                "openclaw": Path.home() / ".openclaw",
                "claude-code": Path.home() / ".claude",
                "codex": Path.home() / ".codex",
            }
            config_dir = default_paths.get(fw_name, Path.home() / f".{fw_name}")
            adapter = adapter_class(config_dir)
        
        adapter.set_client(client)
        
        if args.dry_run:
            print(f"\n📋 Dry run for {fw_name}:")
            memories = adapter.load_memories()
            print(f"  Would sync {len(memories)} memories")
            
            if "sessions" in sync_types:
                sessions = adapter.load_sessions()
                print(f"  Would sync {len(sessions)} sessions")
            
            if "config" in sync_types:
                cfg = adapter.load_config()
                print(f"  Would sync config: {'yes' if cfg else 'no'}")
            
            if "skills" in sync_types:
                skills = adapter.load_skills()
                print(f"  Would sync {len(skills)} skills")
            continue
        
        print(f"\n🔄 Syncing {fw_name}...")
        
        # Use full_sync if syncing everything, otherwise manual
        if set(sync_types) == {"memories", "sessions", "config", "skills"}:
            result = adapter.full_sync(client)
        else:
            result = SyncResult()
            
            if "memories" in sync_types:
                memories = adapter.load_memories()
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
            
            if "sessions" in sync_types:
                sessions = adapter.load_sessions()
                for session in sessions:
                    try:
                        client.sync_session(session)
                        result.sessions_synced += 1
                    except Exception as e:
                        result.errors.append(f"Session sync error: {e}")
            
            if "config" in sync_types:
                cfg = adapter.load_config()
                if cfg:
                    try:
                        client.sync_config(cfg)
                        result.config_synced = True
                    except Exception as e:
                        result.errors.append(f"Config sync error: {e}")
            
            if "skills" in sync_types:
                skills = adapter.load_skills()
                for skill in skills:
                    try:
                        client.sync_skill(skill)
                        result.skills_synced += 1
                    except Exception as e:
                        result.errors.append(f"Skill sync error: {e}")
        
        # Aggregate
        total_result.memories_synced += result.memories_synced
        total_result.sessions_synced += result.sessions_synced
        total_result.config_synced = total_result.config_synced or result.config_synced
        total_result.skills_synced += result.skills_synced
        total_result.errors.extend(result.errors)
        
        print(f"  ✓ Memories: {result.memories_synced}")
        print(f"  ✓ Sessions: {result.sessions_synced}")
        print(f"  ✓ Config: {'yes' if result.config_synced else 'no'}")
        print(f"  ✓ Skills: {result.skills_synced}")
        
        if result.errors:
            for err in result.errors:
                print(f"  ⚠ {err}")
    
    client.close()
    
    if args.json:
        print(json.dumps({
            "memories_synced": total_result.memories_synced,
            "sessions_synced": total_result.sessions_synced,
            "config_synced": total_result.config_synced,
            "skills_synced": total_result.skills_synced,
            "errors": total_result.errors,
        }, indent=2))
    else:
        print(f"\n📊 Total: {total_result.memories_synced} memories, {total_result.sessions_synced} sessions, config: {total_result.config_synced}, {total_result.skills_synced} skills")
        if total_result.errors:
            print(f"⚠ {len(total_result.errors)} errors occurred")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())