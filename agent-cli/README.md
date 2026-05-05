# OpenAgent CLI

Terminal interface for OpenAgent.

Install from PyPI:

```bash
pip install openagent-app
openagent --version
```

Current published release: **0.1.1**.

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

During an interactive session, use slash commands to change it without restarting:

```text
/thinking
/thinking on
/thinking off
/thinking high
/thinking max
```

For the full project overview, setup guide, and architecture notes, see the repository
root [README](../README.md).
