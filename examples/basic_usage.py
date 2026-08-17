#!/usr/bin/env python3
"""Example: Basic usage of agent-cloud-memory."""

from __future__ import annotations

from pathlib import Path
from agent_cloud_memory import CloudMemoryClient
from agent_cloud_memory.adapters import HermesAdapter, get_adapter_for_path

def main():
    # Initialize client (reads config from ~/.config/agent-cloud-memory/)
    client = CloudMemoryClient()
    client.initialize()
    
    print("🧠 agent-cloud-memory - Basic Usage Example")
    print("=" * 50)
    
    # 1. Remember things
    print("\n1. Storing memories...")
    client.remember(
        "User prefers dark mode and tabs over spaces",
        target="user"
    )
    client.remember(
        "Project uses FastAPI + PostgreSQL + Redis",
        target="memory",
        session_id="proj-123",
        metadata={"project": "web-api"}
    )
    client.remember(
        "API keys are stored in ~/.config/app/secrets.yaml",
        target="memory",
        metadata={"sensitive": True}
    )
    print("   ✓ Stored 3 memories")
    
    # 2. Search memories
    print("\n2. Searching memories...")
    results = client.search("dark mode", top_k=5)
    for entry in results:
        print(f"   [{entry.target}] {entry.content[:60]}...")
    
    # 3. Get user profile
    print("\n3. User profile:")
    profile = client.profile()
    for entry in profile:
        print(f"   • {entry.content}")
    
    # 4. List all memories
    print("\n4. All memories:")
    all_memories = client.list(limit=20)
    for entry in all_memories:
        print(f"   [{entry.target}] {entry.content[:50]}...")
    
    # 5. Framework adapter usage (auto-detect)
    print("\n5. Framework adapter (auto-detect)...")
    adapter = get_adapter_for_path(Path.home())
    if adapter:
        print(f"   Detected: {adapter.DISPLAY_NAME}")
        adapter.set_client(client)
        
        # Full sync to cloud
        result = adapter.full_sync(client)
        print(f"   Synced: {result.memories_synced} memories, {result.sessions_synced} sessions, {result.skills_synced} skills")
    else:
        print("   No framework detected")
    
    client.close()
    print("\n✅ Done!")


if __name__ == "__main__":
    main()