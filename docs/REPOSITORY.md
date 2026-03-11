# Repository Layout

This monorepo contains the OpenAgent runtime stack and the files needed to maintain it
as a public repository.

## Runtime Components

The main OpenAgent product is formed by these directories:

| Path | Role |
|------|------|
| `agent-api/` | FastAPI backend, agent loop, built-in tools, WebSocket API |
| `agent-cli/` | Terminal client for local interactive use |
| `agent-ui/` | Developer-facing browser UI |
| `agent-user-ui/` | Simpler user-facing browser UI |

Most issues, pull requests, and release work should target one or more of these four directories.

## Repository Files

The rest of the monorepo root contains project-level files:

| Path | Purpose |
|------|---------|
| `.github/` | CI workflow, issue templates, and PR template |
| `docs/README_*.md` | Translations of the root README |
| `README.md` | Main project overview and setup |
| `CONTRIBUTING.md` | Contribution process |
| `CODE_OF_CONDUCT.md` | Community expectations |
| `SECURITY.md` | Private vulnerability reporting guidance |
| `.env.example` | Runtime configuration reference |

## Where To Contribute

- Backend behavior, tools, prompts, skills, or APIs: start in `agent-api/`
- Terminal UX, slash commands, or session handling: start in `agent-cli/`
- Browser developer experience: start in `agent-ui/`
- Simplified browser UX: start in `agent-user-ui/`
- Onboarding, setup, and project positioning: start in the root `README.md`, `CONTRIBUTING.md`, and `.github/`

## Maintainer Note

The embedded Git repositories have been removed from the runtime component directories,
so `openagent/` now behaves as a normal single-repository monorepo.

To preserve the original standalone histories before flattening, Git bundle archives were
exported to the sibling directory `../openagent-history-bundles/`.
