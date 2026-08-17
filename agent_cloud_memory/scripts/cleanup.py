#!/usr/bin/env python3
"""agent-cloud-memory - Cleanup old data to save space."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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
    
    import os
    if os.environ.get("ACM_POSTGRES_DSN"):
        config["postgresql"]["dsn"] = os.environ["ACM_POSTGRES_DSN"]
    if os.environ.get("ACM_POSTGRES_SCHEMA"):
        config["postgresql"]["schema"] = os.environ["ACM_POSTGRES_SCHEMA"]
    if os.environ.get("ACM_PROFILE"):
        config["profile"] = os.environ["ACM_PROFILE"]
    
    return config


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup old sessions and data")
    parser.add_argument("--days", type=int, default=30, help="Delete sessions older than N days (default: 30)")
    parser.add_argument("--keep", type=int, default=1000, help="Keep at least N most recent sessions (default: 1000)")
    parser.add_argument("--vacuum", action="store_true", help="Run VACUUM ANALYZE after cleanup")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")
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
    
    provider = client.provider
    profile = config["profile"]
    schema = provider._schema
    
    try:
        with provider._pool.connection() as conn:
            conn.execute(f"SET search_path TO {schema}")
            
            # Count total sessions
            cur = conn.execute(
                f"SELECT count(*) FROM {schema}.sessions WHERE profile = %s",
                (profile,)
            )
            total = cur.fetchone()[0]
            print(f"Total sessions: {total}")
            
            if total <= args.keep:
                print(f"  ≤ {args.keep} sessions, nothing to clean up")
                return 0
            
            # Find sessions to delete
            cur = conn.execute(
                f"""
                SELECT id, started_at, ended_at, message_count
                FROM {schema}.sessions
                WHERE profile = %s
                AND id NOT IN (
                    SELECT id FROM {schema}.sessions
                    WHERE profile = %s
                    ORDER BY started_at DESC LIMIT %s
                )
                AND (ended_at IS NOT NULL AND ended_at < NOW() - INTERVAL '%s days')
                ORDER BY started_at
                """,
                (profile, profile, args.keep, args.days)
            )
            to_delete = cur.fetchall()
            
            if not to_delete:
                print("  No sessions match cleanup criteria")
                return 0
            
            print(f"\nSessions to delete: {len(to_delete)}")
            for sid, started, ended, msg_count in to_delete[:10]:
                print(f"  {sid} | {started} | msgs: {msg_count}")
            if len(to_delete) > 10:
                print(f"  ... and {len(to_delete) - 10} more")
            
            if args.dry_run:
                print("\n  DRY RUN - no changes made")
                return 0
            
            # Delete
            ids = [row[0] for row in to_delete]
            placeholders = ",".join(["%s"] * len(ids))
            
            conn.execute(
                f"DELETE FROM {schema}.sessions WHERE id IN ({placeholders})",
                tuple(ids)
            )
            conn.commit()
            print(f"\n  ✓ Deleted {len(to_delete)} sessions")
            
            if args.vacuum:
                print("  Running VACUUM ANALYZE...")
                conn.execute("VACUUM ANALYZE")
                print("  ✓ Vacuum complete")
            
    except Exception as exc:
        print(f"✗ Error: {exc}")
        return 1
    finally:
        client.close()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())