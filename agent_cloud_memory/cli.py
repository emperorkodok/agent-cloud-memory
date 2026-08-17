#!/usr/bin/env python3
"""agent-cloud-memory - Main CLI entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        prog="acm",
        description="agent-cloud-memory - Universal cloud memory for AI agents",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # setup
    setup_parser = subparsers.add_parser("setup", help="Interactive setup wizard")
    setup_parser.add_argument("--non-interactive", action="store_true", help="Use env vars only")

    # sync
    sync_parser = subparsers.add_parser("sync", help="Sync local frameworks to cloud")
    framework_choices = ["hermes", "openclaw", "claude-code", "codex"]
    sync_parser.add_argument(
        "--framework", choices=framework_choices, help="Specific framework"
    )
    sync_parser.add_argument("--all", action="store_true", help="Sync all detected frameworks")
    sync_parser.add_argument("--memories", action="store_true", help="Sync only memories")
    sync_parser.add_argument("--sessions", action="store_true", help="Sync only sessions")
    sync_parser.add_argument("--config", action="store_true", help="Sync only config")
    sync_parser.add_argument("--skills", action="store_true", help="Sync only skills")
    sync_parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    sync_parser.add_argument("--json", action="store_true", help="Output JSON")

    # watch
    watch_parser = subparsers.add_parser("watch", help="Watch for changes and auto-sync")
    watch_parser.add_argument(
        "--framework", choices=framework_choices, help="Specific framework"
    )
    watch_parser.add_argument("--all", action="store_true", help="Watch all detected frameworks")
    watch_parser.add_argument("--memories", action="store_true", help="Sync only memories")
    watch_parser.add_argument("--sessions", action="store_true", help="Sync only sessions")
    watch_parser.add_argument("--config", action="store_true", help="Sync only config")
    watch_parser.add_argument("--skills", action="store_true", help="Sync only skills")
    watch_parser.add_argument("--debounce", type=float, default=2.0, help="Debounce seconds (default: 2.0)")
    watch_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    # restore
    restore_parser = subparsers.add_parser("restore", help="Restore from cloud to local")
    restore_parser.add_argument(
        "--framework", choices=framework_choices, help="Specific framework"
    )
    restore_parser.add_argument(
        "--what",
        choices=["memories", "config", "skills", "all"],
        default="all",
        help="What to restore",
    )
    restore_parser.add_argument(
        "--dry-run", action="store_true", help="Preview without writing"
    )
    restore_parser.add_argument(
        "--force", action="store_true", help="Overwrite without backup"
    )
    restore_parser.add_argument("--json", action="store_true", help="Output JSON")

    # status
    status_parser = subparsers.add_parser("status", help="Show sync status")
    status_parser.add_argument(
        "--framework", choices=framework_choices, help="Specific framework"
    )
    status_parser.add_argument("--json", action="store_true", help="Output JSON")

    # cleanup
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up old sessions")
    cleanup_parser.add_argument("--days", type=int, default=30, help="Delete sessions older than N days")
    cleanup_parser.add_argument("--keep", type=int, default=1000, help="Keep at least N sessions")
    cleanup_parser.add_argument("--vacuum", action="store_true", help="Run VACUUM ANALYZE")
    cleanup_parser.add_argument("--dry-run", action="store_true", help="Preview without deleting")
    cleanup_parser.add_argument("--json", action="store_true", help="Output JSON")

    # detect
    detect_parser = subparsers.add_parser("detect", help="Detect installed frameworks")
    detect_parser.add_argument("--json", action="store_true", help="Output JSON")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # Dispatch to subcommand modules
    if args.command == "setup":
        from agent_cloud_memory.scripts.setup import main as setup_main
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        return setup_main()
    elif args.command == "sync":
        from agent_cloud_memory.scripts.sync import main as sync_main
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        return sync_main()
    elif args.command == "watch":
        from agent_cloud_memory.scripts.watch import main as watch_main
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        return watch_main()
    elif args.command == "restore":
        from agent_cloud_memory.scripts.restore import main as restore_main
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        return restore_main()
    elif args.command == "status":
        from agent_cloud_memory.scripts.status import main as status_main
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        return status_main()
    elif args.command == "cleanup":
        from agent_cloud_memory.scripts.cleanup import main as cleanup_main
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        return cleanup_main()
    elif args.command == "detect":
        from agent_cloud_memory.adapters import FrameworkDetector
        detected = FrameworkDetector.detect_all([Path.home()])
        if args.json:
            import json
            print(json.dumps([
                {
                    "name": fw.name,
                    "display_name": fw.display_name,
                    "config_dir": str(fw.config_dir),
                    "data_dir": str(fw.data_dir) if fw.data_dir else None,
                    "confidence": fw.confidence,
                }
                for fw in detected
            ], indent=2))
        else:
            if not detected:
                print("No frameworks detected.")
            else:
                print("Detected frameworks:")
                for fw in detected:
                    print(f"  • {fw.display_name} ({fw.name}) - {fw.confidence:.0%} at {fw.config_dir}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
