# OpenAgent CLI

Terminal interface for OpenAgent.

Provider thinking can be enabled per run:

```bash
openagent --thinking --thinking-effort max
```

Or in `~/.openagent/config.toml`:

```toml
thinking_enabled = true
thinking_effort = "max"
```

When enabled, the CLI prints provider thinking before the assistant reply and keeps normal reply streaming behavior intact.

For the full project overview, setup guide, and architecture notes, see the repository
root [README](../README.md).
