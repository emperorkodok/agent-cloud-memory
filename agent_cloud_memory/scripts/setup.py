#!/usr/bin/env python3
"""agent-cloud-memory - Setup wizard."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

from agent_cloud_memory.core import CloudMemoryClient


def prompt(prompt_text: str, default: str = "", secret: bool = False) -> str:
    """Prompt user for input."""
    suffix = f" [{default}]" if default else ""
    if secret:
        value = getpass.getpass(f"  {prompt_text}{suffix}: ")
    else:
        value = input(f"  {prompt_text}{suffix}: ").strip()
    return value or default


def test_connection(dsn: str) -> bool:
    """Test PostgreSQL connection."""
    try:
        import psycopg
        conn = psycopg.connect(dsn, connect_timeout=10)
        conn.execute("SELECT 1")
        conn.close()
        return True
    except Exception as e:
        print(f"  ✗ Connection failed: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="agent-cloud-memory setup wizard")
    parser.add_argument("--non-interactive", action="store_true", help="Skip prompts, use env vars")
    args = parser.parse_args()

    print("""
╔══════════════════════════════════════════════════════════════╗
║         agent-cloud-memory - Setup Wizard                    ║
║     Universal cloud memory for AI agents                     ║
╚══════════════════════════════════════════════════════════════╝
""")

    # Get configuration
    if args.non_interactive:
        dsn = os.environ.get("ACM_POSTGRES_DSN") or os.environ.get("POSTGRES_DSN")
        schema = os.environ.get("ACM_POSTGRES_SCHEMA", "agent_cloud_memory")
        profile = os.environ.get("ACM_PROFILE", "default")
        auto_detect = os.environ.get("ACM_AUTO_DETECT", "true").lower() == "true"
    else:
        print("\n📋 Step 1: PostgreSQL Connection")
        print("   Enter your PostgreSQL DSN (connection string):")
        print("   Examples:")
        print("     Neon:      postgresql://user:***@ep-xxx.region.aws.neon.tech/db?sslmode=require")
        print("     Supabase:  postgresql://postgres:***@db.xxx.supabase.co:5432/postgres?sslmode=require")
        print("     Railway:   postgresql://postgres:***@containers-xxx.railway.app:5432/railway?sslmode=require")
        print("     Local:     postgresql://user:***@localhost:5432/agent_memory?sslmode=require")
        print()

        dsn = prompt("PostgreSQL DSN", secret=True)
        if not dsn:
            print("  ✗ DSN is required")
            return 1

        schema = prompt("Database schema", default="agent_cloud_memory")
        profile = prompt("Profile name", default="default")

        print("\n📋 Step 2: Framework Detection")
        auto_detect = prompt("Auto-detect frameworks (Hermes, OpenClaw, Claude Code, Codex)?", default="Y").lower() in ("y", "yes", "")

    # Test connection
    print("\n🔌 Testing connection...")
    if not test_connection(dsn):
        if not args.non_interactive:
            retry = prompt("Continue anyway?", default="N").lower()
            if retry != "y":
                return 1
        print("  ⚠ Continuing without verified connection...")
    else:
        print("  ✓ Connection successful!")

    # Initialize client and create schema
    print("\n📦 Initializing database schema...")
    try:
        client = CloudMemoryClient()
        client.initialize({
            "dsn": dsn,
            "schema": schema,
            "profile": profile,
        })
        print("  ✓ Schema created/verified")
    except Exception as e:
        print(f"  ✗ Failed to initialize: {e}")
        return 1

    # Save configuration
    print("\n💾 Saving configuration...")
    config_dir = Path.home() / ".config" / "agent-cloud-memory"
    config_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "postgresql": {
            "dsn": dsn,
            "schema": schema,
        },
        "profile": profile,
        "auto_detect": auto_detect,
    }

    config_file = config_dir / "config.yaml"
    if yaml:
        config_file.write_text(yaml.dump(config, sort_keys=False), encoding="utf-8")
    else:
        # Fallback: write simple YAML
        lines = []
        for key, value in config.items():
            if isinstance(value, dict):
                lines.append(f"{key}:")
                for k, v in value.items():
                    lines.append(f"  {k}: {v}")
            else:
                lines.append(f"{key}: {value}")
        config_file.write_text("\n".join(lines), encoding="utf-8")

    # Save DSN to environment file (secure)
    env_file = config_dir / ".env"
    env_content = f"ACM_POSTGRES_DSN={dsn}\nACM_POSTGRES_SCHEMA={schema}\nACM_PROFILE={profile}\n"
    env_file.write_text(env_content, encoding="utf-8")
    env_file.chmod(0o600)

    print(f"  ✓ Config saved to {config_file}")
    print(f"  ✓ Secrets saved to {env_file} (chmod 600)")

    # Auto-detect frameworks
    if auto_detect:
        print("\n🔍 Detecting frameworks...")
        from agent_cloud_memory.adapters import FrameworkDetector

        detected = FrameworkDetector.detect_all([Path.home()])
        if detected:
            print("  Found frameworks:")
            for fw in detected:
                print(f"    • {fw.display_name} ({fw.confidence:.0%}) at {fw.config_dir}")

            if not args.non_interactive:
                print("\n  Run 'acm sync' to sync all detected frameworks to cloud.")
        else:
            print("  No frameworks detected. You can still use the library programmatically.")

    print("""
╔══════════════════════════════════════════════════════════════╗
║                    Setup Complete! 🎉                         ║
╚══════════════════════════════════════════════════════════════╝

Next steps:
  acm sync          # Sync all detected frameworks to cloud
  acm status        # Show sync status
  acm restore       # Restore from cloud to new device

Programmatic usage:
  from agent_cloud_memory import CloudMemoryClient
  client = CloudMemoryClient()
  client.initialize()
  client.remember("User prefers dark mode")
  results = client.search("dark mode")

Configuration: ~/.config/agent-cloud-memory/config.yaml
Secrets:       ~/.config/agent-cloud-memory/.env
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
