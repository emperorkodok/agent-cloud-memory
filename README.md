# 🧠 agent-cloud-memory

> **Universal cloud memory layer for AI agents** — Sync memories, sessions, config & skills across all your devices and frameworks.

[![PyPI](https://img.shields.io/pypi/v/agent-cloud-memory?style=for-the-badge&logo=pypi)](https://pypi.org/project/agent-cloud-memory/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue?style=for-the-badge&logo=python)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14%2B-blue?style=for-the-badge&logo=postgresql)](https://postgresql.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
[![Tests](https://img.shields.io/github/actions/workflow/status/yourusername/agent-cloud-memory/test.yml?style=for-the-badge)](https://github.com/yourusername/agent-cloud-memory/actions)

---

## ✨ Why This Exists

| Problem | Solution |
|---------|----------|
| 💻 **New device = blank agent** | One command restores **everything** |
| 🔄 **Manual backup/restore** | **Real-time sync** — every memory write, instant |
| 🤖 **Sub-agents lose context** | Sessions synced, delegation preserved |
| 🔀 **Multiple frameworks** | **One cloud** for Hermes, OpenClaw, Claude Code, Codex |
| ☁️ **Vendor lock-in** | Your data, your PostgreSQL, your control |

---

## 🚀 Quick Start

```bash
# 1. Install
pip install agent-cloud-memory

# 2. Run interactive setup (auto-detects frameworks)
acm-setup

# 3. Sync everything to cloud
acm sync --all

# 4. On new device - restore everything
acm restore --what=all
```

**That's it.** Your agent now has universal cloud memory.

---

## 🎯 Supported Frameworks

| Framework | Config Dir | Memory Files | Config | Skills |
|-----------|------------|--------------|--------|--------|
| **Hermes Agent** | `~/.hermes/` | MEMORY.md, USER.md, SOUL.md | config.yaml, state.db | `skills/*/SKILL.md` |
| **OpenClaw** | `~/.openclaw/` | MEMORY.md, USER.md, SOUL.md, AGENTS.md | workspace.json | `skills/*/SKILL.md` |
| **Claude Code** | `~/.claude/` | CLAUDE.md | settings.json, .claude.json | `skills/*/SKILL.md` |
| **Codex** | `~/.codex/` | AGENTS.md, memories/*.md | config.toml | `skills/*/SKILL.md` |

---

## 📦 What Gets Synced

| Data Type | Trigger | Direction |
|-----------|---------|-----------|
| **Memories** | Every write / `acm sync` | Bidirectional ⚡ |
| **Sessions** | End of session / `acm sync` | Local → Cloud |
| **Config** | `acm sync` / setup | Bidirectional |
| **Skills** | `acm sync` | Local → Cloud |

---

## 🛠 CLI Commands

```bash
# Setup & Configuration
acm setup              # Interactive setup wizard
acm detect             # Detect installed frameworks

# Sync Operations
acm sync --all         # Sync all detected frameworks
acm sync --framework hermes --memories --skills
acm sync --dry-run     # Preview without writing

# Auto-Sync (Real-time)
acm watch              # Watch for changes and auto-sync (primary framework)
acm watch --all        # Watch all detected frameworks
acm watch --framework hermes --verbose  # Watch Hermes with verbose output

# Restore Operations
acm restore --what=all # Restore everything
acm restore --what=memories --framework hermes
acm restore --dry-run  # Preview restore

# Status & Maintenance
acm status             # Show cloud/local stats
acm cleanup --days=30  # Archive old sessions
acm cleanup --vacuum   # Reclaim space
```

---

## 💻 Programmatic Usage

```python
from agent_cloud_memory import CloudMemoryClient

# Initialize (reads ~/.config/agent-cloud-memory/config.yaml)
client = CloudMemoryClient()
client.initialize()

# Remember things
client.remember("User prefers dark mode", target="user")
client.remember("Project uses FastAPI + PostgreSQL", target="memory", session_id="proj-123")

# Search memories
results = client.search("dark mode", top_k=5)
for entry in results:
    print(f"[{entry.target}] {entry.content}")

# Get user profile
profile = client.profile()
for entry in profile:
    print(f"User: {entry.content}")

# Full sync/restore (via adapters)
from agent_cloud_memory.adapters import HermesAdapter, get_adapter_for_path
adapter = HermesAdapter(Path.home() / ".hermes")
adapter.set_client(client)
result = adapter.full_sync(client)
print(f"Synced: {result.memories_synced} memories, {result.sessions_synced} sessions")

# Restore to new device
result = adapter.full_restore(client)
print(f"Restored: {result.memories_restored} memories")
```

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      agent-cloud-memory                             │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────┐ ┌──────────┐ ┌────────────┐ ┌────────┐ ┌───────────┐  │
│  │ Hermes  │ │ OpenClaw │ │Claude Code │ │ Codex  │ │ Custom    │  │
│  │ Adapter │ │ Adapter  │ │ Adapter    │ │ Adapter│ │ Adapter   │  │
│  └────┬────┘ └────┬────┘ └─────┬──────┘ └────┬───┘ └─────┬─────┘  │
│       └───────────┴───────────┴──────────────┴─────────┴────────┘  │
│                           │                                        │
│                  ┌────────▼──────────┐                              │
│                  │  CloudMemoryClient │                              │
│                  │  (High-level API)  │                              │
│                  └────────┬──────────┘                              │
│                           │                                        │
│                  ┌────────▼──────────┐                              │
│                  │  MemoryProvider    │                              │
│                  │  (ABC Interface)   │                              │
│                  └────────┬──────────┘                              │
│                           │                                        │
│                  ┌────────▼──────────┐                              │
│                  │ PostgreSQLBackend  │                              │
│                  │  • Connection Pool │                              │
│                  │  • FTS5 Search     │                              │
│                  │  • Auto-schema     │                              │
│                  │  • Retry/Timeout   │                              │
│                  └────────┬──────────┘                              │
│                           │                                        │
│                  ┌────────▼──────────┐                              │
│                  │  PostgreSQL Cloud  │                              │
│                  │  Schema: acm       │                              │
│                  │  Tables:           │                              │
│                  │   • memories       │                              │
│                  │   • sessions       │                              │
│                  │   • config_snapshots│                             │
│                  │   • skill_snapshots│                             │
│                  └───────────────────┘                              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## ☁️ Supported Cloud Providers

| Provider | Free Tier | Referral | Best For |
|----------|-----------|----------|----------|
| **Neon** | 512 MB | $50 each | Serverless, branching, auto-scale |
| **Supabase** | 500 MB | $10 each | Full BaaS (auth, storage, realtime) |
| **Timescale** | 500 MB | $50 each | Time-series, analytics |
| **Railway** | 1 GB (trial) | $5 each | Simple deploys |
| **Render** | 90 days free | $25 each | Native PG, good DX |
| **Self-hosted** | Unlimited | N/A | Full control, 24/7 heavy usage |

**DSN Format**: `postgresql://user:pass@host:5432/db?sslmode=require`

---

## 💾 Storage Estimates

| Usage | Monthly | Yearly | Recommended |
|-------|---------|--------|-------------|
| Light (daily chat) | ~50 MB | ~600 MB | Free tier OK |
| Normal (coding daily) | ~500 MB | ~6 GB | Neon Pro / Supabase |
| **Heavy (24/7 + sub-agents)** | **3-8 GB** | **36-96 GB** | **Self-hosted VPS** |

---

## 🔧 Configuration

**Config file**: `~/.config/agent-cloud-memory/config.yaml`
```yaml
postgresql:
  dsn: "postgresql://user:pass@host:5432/db?sslmode=require"
  schema: "agent_cloud_memory"
profile: "default"
auto_detect: true
```

**Secrets**: `~/.config/agent-cloud-memory/.env` (chmod 600)
```bash
ACM_POSTGRES_DSN=postgresql://user:pass@host:5432/db?sslmode=require
ACM_POSTGRES_SCHEMA=agent_cloud_memory
ACM_PROFILE=default
```

**Environment variables override config file**:
- `ACM_POSTGRES_DSN`
- `ACM_POSTGRES_SCHEMA`
- `ACM_PROFILE`

---

## 🧪 Development

```bash
# Clone and install in dev mode
git clone https://github.com/yourusername/agent-cloud-memory.git
cd agent-cloud-memory
pip install -e ".[dev]"

# Run tests (requires TEST_POSTGRES_DSN)
export TEST_POSTGRES_DSN="postgresql://user:pass@localhost:5432/test"
pytest tests/ -v

# Lint
ruff check .
mypy agent_cloud_memory/

# Build package
pip build
twine upload dist/*
```

---

## 📚 Examples

See [`examples/`](examples/) for:
- Basic usage
- Custom adapter creation
- Integration with agent frameworks
- Migration scripts

---

## 🤝 Contributing

1. Fork the repo
2. Create feature branch: `git checkout -b feature/amazing-thing`
3. Add tests for new functionality
4. Ensure linting passes: `ruff check . && mypy agent_cloud_memory/`
5. Commit: `git commit -m 'Add amazing thing'`
6. Push: `git push origin feature/amazing-thing`
7. Open PR

---

## 📄 License

MIT — Use freely, modify, distribute. See [LICENSE](LICENSE).

---

## 🙏 Credits

- **Hermes Agent** by [Nous Research](https://github.com/NousResearch/hermes-agent)
- **OpenClaw** — Migration inspiration
- **Claude Code** / **Codex** — Framework references
- **PostgreSQL** — The world's most advanced open source database
- **psycopg3** — Modern PostgreSQL adapter for Python

---

## 🌟 Star This Repo If It Saved Your Setup Time!

**[Report Issues](https://github.com/yourusername/agent-cloud-memory/issues) • [Request Features](https://github.com/yourusername/agent-cloud-memory/issues/new) • [Discussions](https://github.com/yourusername/agent-cloud-memory/discussions)**# CI trigger




