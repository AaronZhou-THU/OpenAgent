<p align="center">
  <h1 align="center">OpenAgent</h1>
  <p align="center">
    Un agent de programmation IA open source que vous pouvez exécuter localement, comprendre entièrement et étendre librement.
  </p>
  <p align="center">
    <a href="#démarrage-rapide">Démarrage rapide</a> &bull;
    <a href="#fonctionnalités">Fonctionnalités</a> &bull;
    <a href="#architecture">Architecture</a> &bull;
    <a href="#documentation">Documentation</a> &bull;
    <a href="#contribuer">Contribuer</a>
  </p>
  <p align="center">
    <strong>Autres langues :</strong>&nbsp;
    <a href="../README.md">English</a> &bull;
    <a href="README_zh.md">中文</a> &bull;
    <a href="README_ja.md">日本語</a> &bull;
    <a href="README_ko.md">한국어</a> &bull;
    <a href="README_es.md">Español</a>
  </p>
</p>

---

## Qu'est-ce que c'est ?

OpenAgent est un agent de programmation IA complet — similaire à Claude Code, Cursor ou Windsurf — que vous pouvez **exécuter localement**, **lire ligne par ligne** et **modifier à votre guise**.

Vous tapez un message comme *« Crée une API REST avec authentification »*, et l'agent :

1. Lit votre code source pour comprendre le contexte
2. Planifie une approche (optionnellement en mode plan lecture seule)
3. Écrit du code, exécute des commandes et crée des fichiers avec ses outils
4. Vérifie son propre travail avant de terminer
5. Renvoie les résultats en temps réel via streaming

```
Vous : "Ajoute l'authentification utilisateur avec JWT"

Agent : [réflexion] Laissez-moi d'abord explorer le code...
        [read_file] src/app.py — trouvé l'app Flask
        [read_file] requirements.txt — pas de lib d'auth
        [bash] pip install PyJWT bcrypt
        [write_file] src/auth.py — génération de tokens JWT
        [edit_file] src/app.py — ajouté les routes login/inscription
        [bash] python -m pytest tests/ — les 12 tests passent

        Terminé ! J'ai ajouté l'authentification JWT avec des
        endpoints de connexion et d'inscription. Voici ce que
        j'ai créé : ...
```

## Pourquoi ce projet ?

La plupart des frameworks d'agents IA sont soit trop abstraits (LangChain), soit trop fermés (Claude Code). OpenAgent est :

- **Lisible** — la boucle principale fait ~30 lignes. Pas de framework, pas de magie.
- **Complet** — Web UI, CLI terminal, streaming, outils, mémoire, équipes, mode plan.
- **Éducatif** — inclut un [guide pour débutants](../HOW_IT_WORKS.md) et un [plan de cours vidéo](../course-outline.md).
- **Extensible** — ajoutez un outil en 20 lignes. Changez de fournisseur LLM en modifiant un seul adaptateur.

## Installation

```bash
pip install openagent-app
export ANTHROPIC_API_KEY=votre-clé
openagent
```

Paquets PyPI : [`openagent-core`](https://pypi.org/project/openagent-core/) (bibliothèque backend) · [`openagent-app`](https://pypi.org/project/openagent-app/) (CLI)

## Démarrage rapide (développement)

### Prérequis

- Python 3.11+ (3.14 recommandé)
- [Clé API Anthropic](https://console.anthropic.com/)

### Option 1a : Web UI développeur

```bash
# Cloner le dépôt
git clone https://github.com/anthropics/openagent.git
cd openagent

# Backend
cd agent-api
python -m venv .venv && source .venv/bin/activate
pip install -e .
echo "ANTHROPIC_API_KEY=votre-clé-ici" > .env
uvicorn agent_service.main:app --reload

# Frontend développeur (nouveau terminal)
cd agent-ui
python3 -m http.server 3500

# Ouvrir http://localhost:3500
```

### Option 1b : Web UI utilisateur

```bash
# Même backend que ci-dessus, puis dans un nouveau terminal :
cd agent-user-ui
python3 -m http.server 3501

# Ouvrir http://localhost:3501
```

L'UI utilisateur est une interface plus légère orientée utilisateur, avec un thème clair Forest Canopy, des indicateurs d'activité au lieu de blocs d'outils bruts, et des dialogues d'approbation simplifiés. Les deux UI se connectent au même backend.

### Option 2 : CLI terminal

```bash
cd agent-cli
python -m venv .venv && source .venv/bin/activate
pip install -e .
openagent
```

### Option 3 : Mode pipe (non interactif)

```bash
echo "Explique comment fonctionne la recherche binaire" | openagent --no-approval
```

## Fonctionnalités

### Fonctionnalités principales

| Fonctionnalité | Description |
|----------------|-------------|
| **Boucle agent** | Boucle while qui diffuse les réponses LLM, exécute les outils et répète jusqu'à la fin |
| **15+ outils intégrés** | Bash, lecture/écriture/édition de fichiers, réflexion, compaction, compétences, tâches, commandes en arrière-plan |
| **Streaming** | Sortie en temps réel token par token via WebSocket |
| **Approbation des outils** | Confirmation humaine optionnelle avant les opérations dangereuses |
| **Mode plan** | Phase d'exploration en lecture seule — l'agent conçoit un plan avant de modifier le code |
| **Planification autonome** | L'agent entre en mode plan de manière autonome pour les tâches complexes |
| **Sous-agents** | Crée des agents enfants spécialisés (exploration, code, plan, recherche) pour les sous-tâches |
| **Équipes d'agents** | Plusieurs agents nommés travaillant en parallèle avec messagerie asynchrone |

### Intelligence

| Fonctionnalité | Description |
|----------------|-------------|
| **Compaction 3 couches** | Micro-compaction, auto-compaction avec transcriptions, outil de compaction manuelle |
| **Mémoire persistante** | L'agent mémorise vos préférences entre les sessions |
| **Auto-vérification** | Utilise l'outil think pour vérifier son travail avant de terminer |
| **Rappel de conclusion** | Signale qu'il faut terminer à l'approche de la limite de tours |
| **Récupération de troncature** | Continue automatiquement quand la réponse atteint la limite de tokens |

### Expérience développeur

| Fonctionnalité | Description |
|----------------|-------------|
| **UI développeur** | Interface chat avec thème sombre, markdown, coloration syntaxique, navigateur de fichiers, panneau dev |
| **UI utilisateur** | Interface orientée utilisateur avec thème clair (Forest Canopy), indicateurs d'activité, dialogues simplifiés |
| **CLI terminal** | REPL riche avec historique, autocomplétion, mode vi, persistance de session |
| **Panneau dev** | Inspecteur de trames WebSocket brutes dans le navigateur |
| **Traçage LLM** | Voir les prompts et réponses exacts envoyés au modèle |
| **Presets** | Personas de prompts système interchangeables (programmation, productivité bureautique, etc.) |
| **Compétences** | Connaissances expertes à la demande (conception d'API, Docker, génération PDF, etc.) |

## Architecture

```
┌──────────────┐  ┌──────────────────┐  ┌──────────────┐
│   agent-ui   │  │  agent-user-ui   │  │  agent-cli   │
│ (Développeur)│  │  (Utilisateur)   │  │  (Terminal)  │
│  port 3500   │  │   port 3501      │  │              │
└──────┬───────┘  └────────┬─────────┘  └──────┬───────┘
       │ WebSocket         │ WebSocket         │ Appel direct
       └──────────┬────────┘                   │
                  └─────────────┬───────────────┘
                                ▼
                  ┌─────────────────┐
                  │    agent-api     │
                  │    (FastAPI)     │
                  ├─────────────────┤
                  │  Boucle agent    │  ◄── while not done: stream → outils → répéter
                  ├─────────────────┤
                  │  Registre outils │  ◄── bash, fichiers, think, plan_mode, compact...
                  ├─────────────────┤
                  │  Client LLM      │  ◄── agnostique (changer avec un adaptateur)
                  └────────┬────────┘
                           ▼
                    ┌────────────┐
                    │  Claude API │  (ou toute API compatible Anthropic)
                    └────────────┘
```

Le diagramme complet de l'architecture avec tous les sous-systèmes se trouve dans [HOW_IT_WORKS.md](../HOW_IT_WORKS.md#the-complete-architecture).

## Structure du projet

```
codingagents/
├── agent-api/          # Backend FastAPI + logique agent
│   ├── src/agent_service/
│   │   ├── main.py           # Point d'entrée de l'app
│   │   ├── agent/loop.py     # Boucle agentique principale (~1200 lignes)
│   │   ├── agent/llm.py      # Abstraction LLM agnostique
│   │   ├── agent/tools/      # Toutes les implémentations d'outils
│   │   └── api/websocket.py  # Gestionnaire de streaming WebSocket
│   ├── skills/               # Fichiers SKILL.md de connaissances expertes
│   ├── prompts/              # Presets de prompts système PROMPT.md
│   └── tests/                # 236 tests
├── agent-cli/          # Interface CLI terminal
│   ├── src/agent_cli/
│   │   ├── app.py            # Orchestrateur REPL
│   │   ├── renderer.py       # Rendu terminal Rich
│   │   └── commands.py       # Commandes slash (/plan, /model, etc.)
│   └── tests/                # 160 tests
├── agent-ui/           # Frontend web développeur (pas de compilation)
│   ├── index.html
│   ├── css/styles.css
│   └── js/                   # Modules ES (app, renderer, websocket, etc.)
├── agent-user-ui/      # Frontend web utilisateur (pas de compilation)
│   ├── index.html
│   ├── css/styles.css        # Thème clair Forest Canopy
│   └── js/                   # Modules ES (app, renderer, websocket, etc.)
├── HOW_IT_WORKS.md     # Guide d'architecture pour débutants
├── course-outline.md   # Plan de cours YouTube (24 vidéos)
├── CONTRIBUTING.md     # Guide de contribution
├── LICENSE             # Licence MIT
└── .env.example        # Référence des variables d'environnement
```

## Tests

```bash
# Backend (236 tests, ~2s)
cd agent-api && .venv/bin/python -m pytest tests/ -v

# CLI (160 tests, <1s)
cd agent-cli && .venv/bin/python -m pytest tests/ -v

# Lint + vérification de types
cd agent-api && .venv/bin/ruff check src/ tests/
cd agent-cli && .venv/bin/ruff check src/ tests/
```

## Configuration

Variables d'environnement à définir dans `agent-api/.env` :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `ANTHROPIC_API_KEY` | (requis) | Votre clé API Anthropic |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | Endpoint API (pour DeepSeek, proxies, etc.) |
| `MODEL` | `claude-sonnet-4-20250514` | Modèle à utiliser |
| `WORKSPACE_DIR` | `./workspace` | Répertoire de création des fichiers de l'agent |
| `ENABLE_MEMORY` | `true` | Mémoire inter-sessions |
| `MAX_TURNS` | `50` | Nombre max d'itérations de la boucle agent |
| `MAX_TOKEN_BUDGET` | `200000` | Limite de tokens par session |
| `OPENAGENT_TIMEOUT` | `1800` | Timeout dur de la boucle agent CLI (secondes) |

### Utiliser d'autres fournisseurs LLM

```bash
# DeepSeek (économique, rapide)
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic MODEL=deepseek-chat

# En local avec Ollama (gratuit)
# Nécessite un proxy compatible Anthropic
```

## Documentation

| Document | Public | Description |
|----------|--------|-------------|
| [HOW_IT_WORKS.md](../HOW_IT_WORKS.md) | Débutants | Guide visuel des composants avec diagrammes |
| [CLAUDE.md](../agent-api/CLAUDE.md) | Agents IA / développeurs | Référence technique complète |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Contributeurs | Nommage des branches, format des commits, checklist PR |
| [course-outline.md](../course-outline.md) | Éducateurs | Plan de cours YouTube de 24 vidéos |
| [.env.example](../.env.example) | Opérateurs | Toutes les variables d'environnement avec descriptions |

## Contribuer

Les contributions sont les bienvenues ! Consultez le [CONTRIBUTING.md](../CONTRIBUTING.md) pour les directives complètes. Quelques bons points de départ :

- **Ajouter un outil** — copiez `agent-api/src/agent_service/agent/tools/compact_tool.py`, modifiez et enregistrez dans `loop.py`
- **Ajouter une compétence** — créez `agent-api/skills/votre-competence/SKILL.md`
- **Ajouter un preset** — créez `agent-api/prompts/votre-preset/PROMPT.md`
- **Ajouter un fournisseur LLM** — implémentez le protocole `LLMClient` dans `agent/llm.py`
- **Améliorer l'UI développeur** — éditez les fichiers dans `agent-ui/` directement (pas de compilation)
- **Améliorer l'UI utilisateur** — éditez les fichiers dans `agent-user-ui/` directement (pas de compilation)

Veuillez exécuter les suites de tests avant de soumettre (la CI les exécute automatiquement sur les PR) :

```bash
cd agent-api && .venv/bin/python -m pytest tests/ -v
cd agent-cli && .venv/bin/python -m pytest tests/ -v
```

Vous pouvez également exécuter toutes les vérifications d'un coup avec pre-commit :

```bash
pre-commit run --all-files
```

## Licence

MIT

## Remerciements

Construit avec l'[API Anthropic Claude](https://docs.anthropic.com/). Inspiré par [Claude Code](https://docs.anthropic.com/en/docs/claude-code), les patterns de ce projet reflètent des systèmes d'agents en production réels.
