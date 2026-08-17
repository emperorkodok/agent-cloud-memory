#!/usr/bin/env python3
"""agent-cloud-memory - File watcher for real-time auto-sync."""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
from pathlib import Path

from agent_cloud_memory.adapters import ADAPTER_REGISTRY, FrameworkDetector
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


def get_watch_dirs(frameworks: list[str]) -> list[Path]:
    """Get directories to watch for each framework."""
    watch_dirs = []
    default_paths = {
        "hermes": Path.home() / ".hermes",
        "openclaw": Path.home() / ".openclaw",
        "claude-code": Path.home() / ".claude",
        "codex": Path.home() / ".codex",
    }

    for fw_name in frameworks:
        # Try to detect exact path
        detected = FrameworkDetector.detect_primary([Path.home()])
        if detected and detected.name == fw_name:
            watch_dirs.append(detected.config_dir)
            if detected.data_dir:
                watch_dirs.append(detected.data_dir)
        elif fw_name in default_paths:
            watch_dirs.append(default_paths[fw_name])

    return [d for d in watch_dirs if d.exists()]


async def sync_once(client: CloudMemoryClient, frameworks: list[str], sync_types: list[str], verbose: bool = False) -> SyncResult:
    """Perform a single sync cycle."""
    total_result = SyncResult()

    for fw_name in frameworks:
        adapter_class = ADAPTER_REGISTRY.get(fw_name)
        if not adapter_class:
            if verbose:
                print(f"⚠ Unknown framework: {fw_name}")
            continue

        # Get config dir for this framework
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

        adapter.set_client(client)

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

        total_result.memories_synced += result.memories_synced
        total_result.sessions_synced += result.sessions_synced
        total_result.config_synced = total_result.config_synced or result.config_synced
        total_result.skills_synced += result.skills_synced
        total_result.errors.extend(result.errors)

        if verbose:
            print(f"  ✓ {fw_name}: {result.memories_synced} mem, {result.sessions_synced} sess, {result.skills_synced} skills")

    return total_result


class AutoSyncWatcher:
    """File watcher that triggers sync on changes."""

    def __init__(
        self,
        client: CloudMemoryClient,
        frameworks: list[str],
        sync_types: list[str],
        debounce_seconds: float = 2.0,
        verbose: bool = False,
    ):
        self.client = client
        self.frameworks = frameworks
        self.sync_types = sync_types
        self.debounce_seconds = debounce_seconds
        self.verbose = verbose
        self._pending_sync = False
        self._debounce_task = None
        self._shutdown = False

    def on_change(self, changes: set[tuple[str, Path]]) -> None:
        """Called when files change."""
        if self.verbose:
            for change_type, path in changes:
                print(f"📝 Change detected: {change_type} {path}")

        # Debounce: cancel any pending debounce and start a new one
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()

        self._debounce_task = asyncio.create_task(self._debounced_sync())

    async def _debounced_sync(self) -> None:
        """Wait for debounce period then sync."""
        try:
            await asyncio.sleep(self.debounce_seconds)
        except asyncio.CancelledError:
            return  # New change came in, will reschedule

        if self._shutdown:
            return

        await self._perform_sync()

    async def _perform_sync(self) -> None:
        """Actually perform the sync."""
        if self._pending_sync:
            return  # Already syncing

        self._pending_sync = True
        if self.verbose:
            print("\n🔄 Auto-sync triggered...")

        try:
            result = await sync_once(self.client, self.frameworks, self.sync_types, self.verbose)
            if self.verbose:
                print(
                    f"✅ Auto-sync complete: {result.memories_synced} mem, "
                    f"{result.sessions_synced} sess, {result.skills_synced} skills"
                )
            if result.errors and self.verbose:
                for err in result.errors:
                    print(f"  ⚠ {err}")
        except Exception as e:
            if self.verbose:
                print(f"❌ Auto-sync error: {e}")
        finally:
            self._pending_sync = False


async def watch_main(
    frameworks: list[str],
    sync_types: list[str],
    debounce: float,
    verbose: bool,
    config: dict,
) -> int:
    """Main watch loop."""
    # Initialize client
    client = CloudMemoryClient()
    try:
        client.initialize(config["postgresql"])
    except Exception as e:
        print(f"✗ Failed to connect: {e}")
        return 1

    # Get watch directories
    watch_dirs = get_watch_dirs(frameworks)
    if not watch_dirs:
        print("✗ No framework directories found to watch")
        return 1

    if verbose:
        print("👀 Watching directories:")
        for d in watch_dirs:
            print(f"   {d}")
        print(f"⏱  Debounce: {debounce}s")
        print(f"🔧 Sync types: {', '.join(sync_types)}")
        print(f"📦 Frameworks: {', '.join(frameworks)}")
        print("\nPress Ctrl+C to stop\n")

    # Create watcher
    watcher = AutoSyncWatcher(client, frameworks, sync_types, debounce, verbose)

    # Set up signal handling
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: setattr(watcher, "_shutdown", True))

    # Initial sync
    if verbose:
        print("🔄 Initial sync...")
    await sync_once(client, frameworks, sync_types, verbose)

    # Watch for changes
    try:
        from watchfiles import awatch

        async for changes in awatch(*watch_dirs):
            if watcher._shutdown:
                break
            watcher.on_change(changes)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"❌ Watch error: {e}")
        return 1
    finally:
        client.close()
        if verbose:
            print("\n👋 Watcher stopped")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch for changes and auto-sync to cloud")
    parser.add_argument("--framework", choices=list(ADAPTER_REGISTRY.keys()), help="Specific framework to watch")
    parser.add_argument("--all", action="store_true", help="Watch all detected frameworks")
    parser.add_argument("--memories", action="store_true", help="Sync only memories")
    parser.add_argument("--sessions", action="store_true", help="Sync only sessions")
    parser.add_argument("--config", action="store_true", help="Sync only config")
    parser.add_argument("--skills", action="store_true", help="Sync only skills")
    parser.add_argument("--debounce", type=float, default=2.0, help="Debounce seconds (default: 2.0)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    # Load config
    config = load_config()

    if not config["postgresql"]["dsn"]:
        print("✗ Not configured. Run 'acm-setup' first.")
        return 1

    # Determine frameworks to watch
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
    if args.memories:
        sync_types.append("memories")
    if args.sessions:
        sync_types.append("sessions")
    if args.config:
        sync_types.append("config")
    if args.skills:
        sync_types.append("skills")
    if not sync_types:
        sync_types = ["memories", "sessions", "config", "skills"]

    return asyncio.run(watch_main(frameworks, sync_types, args.debounce, args.verbose, config))


if __name__ == "__main__":
    sys.exit(main())
