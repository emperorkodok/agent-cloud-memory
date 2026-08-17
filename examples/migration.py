#!/usr/bin/env python3
"""Example: Migration between frameworks."""

from __future__ import annotations

from pathlib import Path
from agent_cloud_memory import CloudMemoryClient
from agent_cloud_memory.adapters import (
    HermesAdapter, OpenClawAdapter, 
    ClaudeCodeAdapter, CodexAdapter,
    FrameworkDetector
)

def main():
    print("🔄 agent-cloud-memory - Framework Migration Example")
    print("=" * 55)
    
    # Initialize client
    client = CloudMemoryClient()
    client.initialize()
    
    # Detect all frameworks
    print("\n1. Detecting frameworks...")
    detected = FrameworkDetector.detect_all([Path.home()])
    
    if not detected:
        print("   No frameworks found")
        return
    
    for fw in detected:
        print(f"   • {fw.display_name} ({fw.confidence:.0%}) at {fw.config_dir}")
    
    # Migrate: OpenClaw → Hermes
    print("\n2. Migration: OpenClaw → Hermes")
    
    openclaw_adapter = OpenClawAdapter(Path.home() / ".openclaw")
    openclaw_adapter.set_client(client)
    
    hermes_adapter = HermesAdapter(Path.home() / ".hermes")
    hermes_adapter.set_client(client)
    
    # Step 1: Sync OpenClaw to cloud
    print("   Syncing OpenClaw to cloud...")
    result = openclaw_adapter.full_sync(client)
    print(f"   ✓ Cloud now has: {result.memories_synced} memories, {result.skills_synced} skills")
    
    # Step 2: Restore to Hermes
    print("   Restoring to Hermes...")
    result = hermes_adapter.full_restore(client)
    print(f"   ✓ Hermes now has: {result.memories_restored} memories, {result.skills_restored} skills")
    
    # Migrate: Claude Code → Codex
    print("\n3. Migration: Claude Code → Codex")
    
    claude_adapter = ClaudeCodeAdapter(Path.home() / ".claude")
    claude_adapter.set_client(client)
    
    codex_adapter = CodexAdapter(Path.home() / ".codex")
    codex_adapter.set_client(client)
    
    print("   Syncing Claude Code to cloud...")
    result = claude_adapter.full_sync(client)
    print(f"   ✓ Cloud updated: {result.memories_synced} memories")
    
    print("   Restoring to Codex...")
    result = codex_adapter.full_restore(client)
    print(f"   ✓ Codex now has: {result.memories_restored} memories")
    
    # Cross-framework memory sharing
    print("\n4. Cross-framework memory sharing")
    print("   All frameworks now share the same cloud memory!")
    print("   A memory added in Hermes is instantly available in Codex.")
    
    # Verify
    results = client.search("project", top_k=10)
    print(f"\n   Cloud contains {len(results)} memories about 'project'")
    
    client.close()
    print("\n✅ Migration complete!")


if __name__ == "__main__":
    main()