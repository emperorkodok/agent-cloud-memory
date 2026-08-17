#!/usr/bin/env python3
"""agent-cloud-memory - Restore from cloud to local frameworks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_cloud_memory.adapters import ADAPTER_REGISTRY, FrameworkDetector
from agent_cloud_memory.core import CloudMemoryClient, RestoreResult


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

    import os
    if os.environ.get("ACM_POSTGRES_DSN"):
        config["postgresql"]["dsn"] = os.environ["ACM_POSTGRES_DSN"]
    if os.environ.get("ACM_POSTGRES_SCHEMA"):
        config["postgresql"]["schema"] = os.environ["ACM_POSTGRES_SCHEMA"]
    if os.environ.get("ACM_PROFILE"):
        config["profile"] = os.environ["ACM_PROFILE"]

    return config


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore from cloud to local frameworks")
    parser.add_argument("--framework", choices=list(ADAPTER_REGISTRY.keys()), help="Specific framework to restore")
    parser.add_argument("--what", choices=["memories", "config", "skills", "all"], default="all", help="What to restore")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be restored without writing")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files without backup")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
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
        detected = FrameworkDetector.detect_primary([Path.home()])
        if not detected:
            print("No framework detected. Use --framework.")
            return 1
        frameworks = [detected.name]

    total_result = RestoreResult()

    for fw_name in frameworks:
        adapter_class = ADAPTER_REGISTRY.get(fw_name)
        if not adapter_class:
            print(f"⚠ Unknown framework: {fw_name}")
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

        print(f"\n🔄 Restoring to {fw_name}...")

        if args.dry_run:
            print("  DRY RUN - would restore:")
            if args.what in ("memories", "all"):
                memories = client.restore_memories()
                print(f"  • Memories: {len(memories)} entries")
            if args.what in ("config", "all"):
                cfg = client.restore_config()
                print(f"  • Config: {'yes' if cfg else 'no'}")
            if args.what in ("skills", "all"):
                skills = client.restore_skills()
                print(f"  • Skills: {len(skills)} files")
            continue

        if args.what in ("memories", "all"):
            memories = client.restore_memories()
            written = adapter.write_memories(memories)
            total_result.memories_restored += written
            print(f"  ✓ Memories: {written} entries")

        if args.what in ("config", "all"):
            cfg = client.restore_config()
            if cfg:
                try:
                    if not args.force and (detected.config_dir / "config.yaml").exists():
                        backup = detected.config_dir / f"config.yaml.backup-{int(cfg.snapshot_at.timestamp())}"
                        (detected.config_dir / "config.yaml").rename(backup)
                        print(f"    Backed up existing config to {backup.name}")
                    adapter.write_config(cfg)
                    total_result.config_restored = True
                    print(f"  ✓ Config restored from {cfg.snapshot_at}")
                except Exception as e:
                    total_result.errors.append(f"Config restore error: {e}")
            else:
                print("  ⚠ No config snapshot found")

        if args.what in ("skills", "all"):
            skills = client.restore_skills()
            written = adapter.write_skills(skills)
            total_result.skills_restored += written
            print(f"  ✓ Skills: {written} files")

        if total_result.errors:
            for err in total_result.errors:
                print(f"  ⚠ {err}")

    client.close()

    if args.json:
        print(json.dumps({
            "memories_restored": total_result.memories_restored,
            "config_restored": total_result.config_restored,
            "skills_restored": total_result.skills_restored,
            "errors": total_result.errors,
        }, indent=2))
    else:
        print(f"\n📊 Total: {total_result.memories_restored} memories, config: {total_result.config_restored}, {total_result.skills_restored} skills")

    return 0


if __name__ == "__main__":
    sys.exit(main())
