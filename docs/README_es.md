<p align="center">
  <h1 align="center">OpenAgent</h1>
  <p align="center">
    Un agente de programación IA de código abierto que puedes ejecutar localmente, entender completamente y extender a tu gusto.
  </p>
  <p align="center">
    <a href="#inicio-rápido">Inicio rápido</a> &bull;
    <a href="#características">Características</a> &bull;
    <a href="#arquitectura">Arquitectura</a> &bull;
    <a href="#documentación">Documentación</a> &bull;
    <a href="#contribuir">Contribuir</a>
  </p>
  <p align="center">
    <strong>Otros idiomas:</strong>&nbsp;
    <a href="../README.md">English</a> &bull;
    <a href="README_zh.md">中文</a> &bull;
    <a href="README_ja.md">日本語</a> &bull;
    <a href="README_ko.md">한국어</a> &bull;
    <a href="README_fr.md">Français</a>
  </p>
</p>

---

## ¿Qué es esto?

OpenAgent es un agente de programación IA completamente funcional — similar a Claude Code, Cursor o Windsurf — que puedes **ejecutar localmente**, **leer cada línea de código** y **modificar como quieras**.

Escribes un mensaje como *"Crea una API REST con autenticación"*, y el agente:

1. Lee tu código fuente para entender el contexto
2. Planifica un enfoque (opcionalmente en modo plan de solo lectura)
3. Escribe código, ejecuta comandos y crea archivos usando herramientas
4. Verifica su propio trabajo antes de terminar
5. Devuelve los resultados en tiempo real mediante streaming

```
Tú: "Agrega autenticación de usuarios con JWT"

Agente: [pensando] Déjame explorar el código primero...
        [read_file] src/app.py — encontré la app Flask
        [read_file] requirements.txt — no hay librerías de auth
        [bash] pip install PyJWT bcrypt
        [write_file] src/auth.py — generación de tokens JWT
        [edit_file] src/app.py — agregué rutas de login/registro
        [bash] python -m pytest tests/ — los 12 tests pasan

        ¡Listo! He agregado autenticación JWT con endpoints
        de login y registro. Esto es lo que creé: ...
```

## ¿Por qué este proyecto?

La mayoría de los frameworks de agentes IA son demasiado abstractos (LangChain) o demasiado cerrados (Claude Code). OpenAgent es:

- **Legible** — el bucle principal tiene ~30 líneas. Sin frameworks, sin magia.
- **Completo** — Web UI, CLI de terminal, streaming, herramientas, memoria, equipos, modo plan.
- **Educativo** — incluye una [guía para principiantes](../HOW_IT_WORKS.md) y un [plan de curso en video](../course-outline.md).
- **Extensible** — agrega una herramienta nueva en 20 líneas. Cambia el proveedor LLM con un solo adaptador.

## Instalación

```bash
pip install openagent-app
export ANTHROPIC_API_KEY=tu-clave
openagent
```

Paquetes PyPI: [`openagent-core`](https://pypi.org/project/openagent-core/) (librería backend) · [`openagent-app`](https://pypi.org/project/openagent-app/) (CLI)

## Inicio rápido (desarrollo)

### Prerrequisitos

- Python 3.11+ (3.14 recomendado)
- [Clave API de Anthropic](https://console.anthropic.com/)

### Opción 1a: Developer Web UI

```bash
# Clonar el repositorio
git clone https://github.com/anthropics/openagent.git
cd openagent

# Backend
cd agent-api
python -m venv .venv && source .venv/bin/activate
pip install -e .
echo "ANTHROPIC_API_KEY=tu-clave-aquí" > .env
uvicorn agent_service.main:app --reload

# Frontend para desarrolladores (nueva terminal)
cd agent-ui
python3 -m http.server 3500

# Abrir http://localhost:3500
```

### Opción 1b: User Web UI

```bash
# Mismo backend que arriba, luego en una nueva terminal:
cd agent-user-ui
python3 -m http.server 3501

# Abrir http://localhost:3501
```

La User UI es una interfaz más liviana orientada al usuario, con un tema claro Forest Canopy, indicadores de actividad en lugar de bloques de herramientas sin procesar, y diálogos de aprobación simplificados. Ambas UIs se conectan al mismo backend.

### Opción 2: CLI de terminal

```bash
cd agent-cli
python -m venv .venv && source .venv/bin/activate
pip install -e .
openagent
```

### Opción 3: Modo pipe (no interactivo)

```bash
echo "Explica cómo funciona la búsqueda binaria" | openagent --no-approval
```

## Características

### Funcionalidades principales

| Característica | Descripción |
|----------------|-------------|
| **Bucle del agente** | Bucle while que transmite respuestas LLM, ejecuta herramientas y repite hasta terminar |
| **15+ herramientas integradas** | Bash, lectura/escritura/edición de archivos, pensamiento, compactación, habilidades, tareas, comandos en segundo plano |
| **Streaming** | Salida token por token en tiempo real vía WebSocket |
| **Aprobación de herramientas** | Confirmación humana opcional antes de operaciones peligrosas |
| **Modo plan** | Fase de exploración de solo lectura — el agente diseña un plan antes de hacer cambios |
| **Planificación autónoma** | El agente entra en modo plan autónomamente para tareas complejas |
| **Sub-agentes** | Genera agentes hijo enfocados (explorar, codificar, planificar, investigar) para subtareas |
| **Equipos de agentes** | Múltiples agentes nombrados trabajando en paralelo con mensajería asíncrona |

### Inteligencia

| Característica | Descripción |
|----------------|-------------|
| **Compactación de 3 capas** | Micro-compactación, auto-compactación con transcripciones, herramienta de compactación manual |
| **Memoria persistente** | El agente recuerda tus preferencias entre sesiones |
| **Auto-verificación** | Usa la herramienta think para revisar su trabajo antes de terminar |
| **Aviso de cierre** | Indica que debe terminar al acercarse al límite de turnos |
| **Recuperación de truncamiento** | Continúa automáticamente cuando la respuesta alcanza el límite de tokens |

### Experiencia de desarrollo

| Característica | Descripción |
|----------------|-------------|
| **Developer UI** | Interfaz de chat con tema oscuro, markdown, resaltado de sintaxis, explorador de archivos, panel de desarrollo |
| **User UI** | Interfaz orientada al usuario con tema claro (Forest Canopy), indicadores de actividad, diálogos simplificados |
| **CLI de terminal** | REPL enriquecido con historial, autocompletado, modo vi, persistencia de sesión |
| **Panel de desarrollo** | Inspector de frames WebSocket en el navegador |
| **Trazado de LLM** | Visualiza los prompts y respuestas exactos enviados al modelo |
| **Presets** | Personas de system prompt intercambiables (programación, productividad de oficina, etc.) |
| **Habilidades** | Conocimiento experto bajo demanda (diseño de API, Docker, generación de PDF, etc.) |

## Arquitectura

```
┌──────────────┐  ┌──────────────────┐  ┌──────────────┐
│   agent-ui   │  │  agent-user-ui   │  │  agent-cli   │
│  (Developer) │  │     (User)       │  │  (Terminal)  │
│  port 3500   │  │   port 3501      │  │              │
└──────┬───────┘  └────────┬─────────┘  └──────┬───────┘
       │ WebSocket         │ WebSocket         │ Llamada directa
       └──────────┬────────┘                   │
                  └─────────────┬───────────────┘
                                ▼
                  ┌─────────────────┐
                  │    agent-api     │
                  │    (FastAPI)     │
                  ├─────────────────┤
                  │  Bucle agente    │  ◄── while not done: stream → herramientas → repetir
                  ├─────────────────┤
                  │  Registro tools  │  ◄── bash, archivos, think, plan_mode, compact...
                  ├─────────────────┤
                  │  Cliente LLM     │  ◄── agnóstico al proveedor (cambiar con un adaptador)
                  └────────┬────────┘
                           ▼
                    ┌────────────┐
                    │  Claude API │  (o cualquier API compatible con Anthropic)
                    └────────────┘
```

El diagrama completo de arquitectura con todos los subsistemas se encuentra en [HOW_IT_WORKS.md](../HOW_IT_WORKS.md#the-complete-architecture).

## Estructura del proyecto

```
codingagents/
├── agent-api/          # Backend FastAPI + lógica del agente
│   ├── src/agent_service/
│   │   ├── main.py           # Punto de entrada de la app
│   │   ├── agent/loop.py     # Bucle principal del agente (~1200 líneas)
│   │   ├── agent/llm.py      # Abstracción LLM agnóstica al proveedor
│   │   ├── agent/tools/      # Implementaciones de herramientas
│   │   └── api/websocket.py  # Manejador de streaming WebSocket
│   ├── skills/               # Archivos SKILL.md de conocimiento experto
│   ├── prompts/              # Presets de system prompt PROMPT.md
│   └── tests/                # 236 tests
├── agent-cli/          # Interfaz CLI de terminal
│   ├── src/agent_cli/
│   │   ├── app.py            # Orquestador del REPL
│   │   ├── renderer.py       # Salida enriquecida de terminal
│   │   └── commands.py       # Comandos slash (/plan, /model, etc.)
│   └── tests/                # 160 tests
├── agent-ui/           # Frontend web para desarrolladores (sin paso de compilación)
│   ├── index.html
│   ├── css/styles.css
│   └── js/                   # Módulos ES (app, renderer, websocket, etc.)
├── agent-user-ui/      # Frontend web para usuarios (sin paso de compilación)
│   ├── index.html
│   ├── css/styles.css        # Tema claro Forest Canopy
│   └── js/                   # Módulos ES (app, renderer, websocket, etc.)
├── HOW_IT_WORKS.md     # Guía de arquitectura para principiantes
├── course-outline.md   # Plan de curso YouTube (24 videos)
├── CONTRIBUTING.md     # Guía de contribución
├── LICENSE             # Licencia MIT
└── .env.example        # Referencia de variables de entorno
```

## Testing

```bash
# Backend (236 tests, ~2s)
cd agent-api && .venv/bin/python -m pytest tests/ -v

# CLI (160 tests, <1s)
cd agent-cli && .venv/bin/python -m pytest tests/ -v

# Lint + verificación de tipos
cd agent-api && .venv/bin/ruff check src/ tests/
cd agent-cli && .venv/bin/ruff check src/ tests/
```

## Configuración

Las variables de entorno se configuran en `agent-api/.env`:

| Variable | Valor por defecto | Descripción |
|----------|-------------------|-------------|
| `ANTHROPIC_API_KEY` | (requerido) | Tu clave API de Anthropic |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | Endpoint de la API (usar para DeepSeek, proxies, etc.) |
| `MODEL` | `claude-sonnet-4-20250514` | Modelo a utilizar |
| `WORKSPACE_DIR` | `./workspace` | Directorio donde el agente crea archivos |
| `ENABLE_MEMORY` | `true` | Memoria entre sesiones |
| `MAX_TURNS` | `50` | Máximo de iteraciones del bucle del agente |
| `MAX_TOKEN_BUDGET` | `200000` | Límite de gasto de tokens por sesión |
| `OPENAGENT_TIMEOUT` | `1800` | Tiempo límite del bucle del agente en CLI (segundos) |

### Uso de proveedores LLM alternativos

```bash
# DeepSeek (económico, rápido)
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic MODEL=deepseek-chat

# Local con Ollama (gratis)
# Requiere un proxy compatible con Anthropic
```

## Documentación

| Documento | Audiencia | Descripción |
|-----------|-----------|-------------|
| [HOW_IT_WORKS.md](../HOW_IT_WORKS.md) | Principiantes | Guía visual de componentes con diagramas |
| [CLAUDE.md](../agent-api/CLAUDE.md) | Agentes IA / desarrolladores | Referencia técnica completa |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Colaboradores | Convenciones de ramas, formato de commits, checklist de PRs |
| [course-outline.md](../course-outline.md) | Educadores | Plan de curso YouTube de 24 videos |
| [.env.example](../.env.example) | Operadores | Todas las variables de entorno con descripciones |

## Contribuir

¡Las contribuciones son bienvenidas! Consulta [CONTRIBUTING.md](../CONTRIBUTING.md) para ver las directrices completas. Algunos buenos puntos de partida:

- **Agregar una herramienta** — copia `agent-api/src/agent_service/agent/tools/compact_tool.py`, modifica y registra en `loop.py`
- **Agregar una habilidad** — crea `agent-api/skills/tu-habilidad/SKILL.md`
- **Agregar un preset** — crea `agent-api/prompts/tu-preset/PROMPT.md`
- **Agregar un proveedor LLM** — implementa el protocolo `LLMClient` en `agent/llm.py`
- **Mejorar la Developer UI** — edita los archivos en `agent-ui/` directamente (sin paso de compilación)
- **Mejorar la User UI** — edita los archivos en `agent-user-ui/` directamente (sin paso de compilación)

Por favor ejecuta los tests antes de enviar (CI los ejecuta automáticamente en los PRs):

```bash
cd agent-api && .venv/bin/python -m pytest tests/ -v
cd agent-cli && .venv/bin/python -m pytest tests/ -v
```

También puedes ejecutar todas las verificaciones a la vez con pre-commit:

```bash
pre-commit run --all-files
```

## Licencia

MIT

## Agradecimientos

Construido con la [API de Anthropic Claude](https://docs.anthropic.com/). Inspirado en [Claude Code](https://docs.anthropic.com/en/docs/claude-code), los patrones de este proyecto reflejan sistemas de agentes de producción reales.
