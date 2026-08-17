#!/usr/bin/env python3
"""agent-cloud-memory - Show sync status."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from agent_cloud_memory.adapters import FrameworkDetector, ADAPTER_REGISTRY
from agent_cloud_memory.core import CloudMemoryClient


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
    
    if os.environ.get("ACM_POSTGRES_DSN"):
        config["postgresql"]["dsn"] = os.environ["ACM_POSTGRES_DSN"]
    if os.environ.get("ACM_POSTGRES_SCHEMA"):
        config["postgresql"]["schema"] = os.environ["ACM_POSTGRES_SCHEMA"]
    if os.environ.get("ACM_PROFILE"):
        config["profile"] = os.environ["ACM_PROFILE"]
    
    return config


def main() -> int:
    parser = argparse.ArgumentParser(description="Show sync status")
    parser.add_argument("--framework", choices=list(ADAPTER_REGISTRY.keys()), help="Specific framework")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    config = load_config()
    
    if not config["postgresql"]["dsn"]:
        print("✗ Not configured. Run 'acm-setup' first.")
        return 1
    
    client = CloudMemoryClient()
    try:
        client.initialize(config["postgresql"])
    except Exception as e:
        print(f"✗ Failed to connect: {e}")
        return 1
    
    # Determine frameworks
    if args.framework:
        frameworks = [args.framework]
    else:
        detected = FrameworkDetector.detect_all([Path.home()])
        frameworks = [fw.name for fw in detected]
    
    if not frameworks:
        print("No frameworks detected.")
        return 1
    
    # Cloud stats
    cloud_stats = {}
    try:
        with client.provider._pool.connection() as conn:
            conn.execute(f"SET search_path TO {client.provider._schema}")
            profile = config["profile"]
            
            for table in ["memories", "sessions", "config_snapshots", "skill_snapshots"]:
                cur = conn.execute(f"SELECT count(*) FROM {client.provider._schema}.{table} WHERE profile = %s", (profile,))
                cloud_stats[table] = cur.fetchone()[0]
            
            # Last sync times
            cur = conn.execute(f"SELECT MAX(synced_at) FROM {client.provider._schema}.sessions WHERE profile = %s", (profile,))
            cloud_stats["last_session_sync"] = cur.fetchone()[0]
            
            cur = conn.execute(f"SELECT MAX(synced_at) FROM {client.provider._schema}.skill_snapshots WHERE profile = %s", (profile,))
            cloud_stats["last_skill_sync"] = cur.fetchone()[0]
            
            cur = conn.execute(f"SELECT MAX(snapshot_at) FROM {client.provider._schema}.config_snapshots WHERE profile = %s", (profile,))
            cloud_stats["last_config_sync"] = cur.fetchone()[0]
    except Exception as e:
        cloud_stats["error"] = str(e)
    
    # Local stats per framework
    local_stats = {}
    for fw_name in frameworks:
        adapter_class = ADAPTER_REGISTRY.get(fw_name)
        if not adapter_class:
            continue
        
        detected = FrameworkDetector.detect_primary([Path.home()])
        if detected and detected.name == fw_name:
            adapter = adapter_class(detected.config_dir, detected.data_dir)
        else:
            default_paths = {
                "hermes": Path.home() / ".hermes",
                "openclaw": Path.home() / ".openclaw",
                "claude-code": Path.home() / ".claude",
                "codex": Path.home() / ".codex",
            }
            config_dir = default_paths.get(fw_name, Path.home() / f".{fw_name}")
            adapter = adapter_class(config_dir)
        
        memories = adapter.load_memories()
        sessions = adapter.load_sessions()
        config_snap = adapter.load_config()
        skills = adapter.load_skills()
        
        local_stats[fw_name] = {
            "display_name": adapter.DISPLAY_NAME,
            "config_dir": str(adapter.config_dir),
            "memories": len(memories),
            "sessions": len(sessions),
            "has_config": config_snap is not None,
            "skills": len(skills),
        }
    
    client.close()
    
    result = {
        "profile": config["profile"],
        "schema": config["postgresql"]["schema"],
        "cloud": cloud_stats,
        "local": local_stats,
    }
    
    if args.json:
        # Convert datetime objects to strings
        def serialize(obj):
            if hasattr(obj, 'isoformat'):
                return obj.isoformat()
            if isinstance(obj, dict):
                return {k: serialize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [serialize(v) for v in obj]
            return obj
        
        print(json.dumps(serialize(result), indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"  agent-cloud-memory Status")
        print(f"  Profile: {config['profile']} | Schema: {config['postgresql']['schema']}")
        print(f"{'='*60}")
        
        print(f"\n☁️  Cloud Storage:")
        if "error" in cloud_stats:
            print(f"  ✗ Error: {cloud_stats['error']}")
        else:
            print(f"  Memories:       {cloud_stats.get('memories', 0)}")
            print(f"  Sessions:       {cloud_stats.get('sessions', 0)}")
            print(f"  Config snapshots: {cloud_stats.get('config_snapshots', 0)}")
            print(f"  Skills:         {cloud_stats.get('skill_snapshots', 0)}")
            print(f"  Last session sync: {cloud_stats.get('last_session_sync', 'never')}")
            print(f"  Last skill sync:   {cloud_stats.get('last_skill_sync', 'never')}")
            print(f"  Last config sync:  {cloud_stats.get('last_config_sync', 'never')}")
        
        print(f"\n💻 Local Frameworks:")
        for fw_name, stats in local_stats.items():
            print(f"\n  {stats['display_name']} ({fw_name}):")
            print(f"    Path:          {stats['config_dir']}")
            print(f"    Memories:      {stats['memories']}")
            print(f"    Sessions:      {stats['sessions']}")
            print(f"    Config:        {'yes' if stats['has_config'] else 'no'}")
            print(f"    Skills:        {stats['skills']}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())