<p align="center">
  <h1 align="center">OpenAgent</h1>
  <p align="center">
    Un agente de programación IA source-available, pensado para principiantes, con el que puedes aprender cómo funcionan los agentes ejecutándolo y modificándolo tú mismo.
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

OpenAgent es un proyecto de agente de programación IA pensado para principiantes con curiosidad por entender cómo funcionan los agentes modernos. Puedes **ejecutarlo localmente**, **leer cada línea de código** y **aprender cambiando código real**, no solo mirando diagramas.

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

La mayoría de los proyectos de agentes IA son demasiado abstractos para principiantes o demasiado cerrados para aprender bien de ellos. OpenAgent es:

- **Legible** — el bucle principal tiene ~30 líneas. Sin frameworks, sin magia.
- **Educativo** — diseñado para principiantes que quieren aprender arquitectura de agentes ejecutándola, trazándola y modificándola.
- **Completo** — Web UI, CLI de terminal, streaming, herramientas, memoria, equipos, modo plan.
- **Bien documentado** — incluye guía de contribución, política de seguridad, traducciones y referencias técnicas por componente.
- **Independiente del LLM** — el bucle principal trabaja contra una interfaz `LLMClient` compartida en lugar de depender de un proveedor único.
- **Extensible** — agrega una herramienta nueva en 20 líneas. Cambia o añade adaptadores de proveedor sin reescribir el bucle.

## Instalación

```bash
cd openagent
python -m venv .venv && source .venv/bin/activate
pip install -e agent-api -e agent-cli
openagent
```

## Inicio rápido (desarrollo)

### Prerrequisitos

- Python 3.11+ (3.14 recomendado)
- Credenciales de tu proveedor LLM elegido o de un endpoint compatible

### Paquetes publicados en PyPI

OpenAgent también está publicado en PyPI:

- `openagent-core` — librería backend
- `openagent-app` — CLI de terminal

Si solo quieres usar el CLI empaquetado y no clonar el monorepo:

```bash
pip install openagent-app
openagent
```

### Opción 1a: Developer Web UI

```bash
# Clona tu fork o copia local
git clone <your-fork-or-local-copy>
cd openagent

# Backend
cd agent-api
python -m venv .venv && source .venv/bin/activate
pip install -e .
cat > .env <<'EOF'
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=tu-clave-aquí
EOF
uvicorn agent_service.main:app --reload

# Frontend para desarrolladores (nueva terminal)
cd /path/to/openagent/agent-ui
python3 -m http.server 3500

# Abrir http://localhost:3500
```

### Opción 1b: User Web UI

```bash
# Mismo backend que arriba, luego en una nueva terminal:
cd /path/to/openagent/agent-user-ui
python3 -m http.server 3501

# Abrir http://localhost:3501
```

La User UI es una interfaz más liviana orientada al usuario, con un tema claro Forest Canopy, indicadores de actividad en lugar de bloques de herramientas sin procesar, y diálogos de aprobación simplificados. Ambas UIs se conectan al mismo backend.

### Opción 2: CLI de terminal

```bash
cd openagent
python -m venv .venv && source .venv/bin/activate
pip install -e agent-api -e agent-cli
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
                  │  Cliente LLM     │  ◄── frontera de adaptadores independiente del proveedor
                  └────────┬────────┘
                           ▼
                    ┌────────────┐
                    │ Proveedor LLM │  (cualquier backend soportado o compatible)
                    └────────────┘
```

Más detalles de la arquitectura backend están en [agent-api/README.md](../agent-api/README.md) y [agent-api/CLAUDE.md](../agent-api/CLAUDE.md).

## Estructura del proyecto

```
openagent/
├── agent-api/          # Backend FastAPI + lógica del agente
│   ├── src/agent_service/
│   │   ├── main.py           # Punto de entrada de la app
│   │   ├── agent/loop.py     # Bucle principal del agente (~1200 líneas)
│   │   ├── agent/llm.py      # Abstracción LLM agnóstica al proveedor
│   │   ├── agent/tools/      # Implementaciones de herramientas
│   │   └── api/websocket.py  # Manejador de streaming WebSocket
│   ├── skills/               # Archivos SKILL.md de conocimiento experto
│   ├── prompts/              # Presets de system prompt PROMPT.md
│   └── tests/                # Suite de tests del backend
├── agent-cli/          # Interfaz CLI de terminal
│   ├── src/agent_cli/
│   │   ├── app.py            # Orquestador del REPL
│   │   ├── renderer.py       # Salida enriquecida de terminal
│   │   └── commands.py       # Comandos slash (/plan, /model, etc.)
│   └── tests/                # Suite de tests del CLI
├── agent-ui/           # Frontend web para desarrolladores (sin paso de compilación)
│   ├── index.html
│   ├── css/styles.css
│   └── js/                   # Módulos ES (app, renderer, websocket, etc.)
├── agent-user-ui/      # Frontend web para usuarios (sin paso de compilación)
│   ├── index.html
│   ├── css/styles.css        # Tema claro Forest Canopy
│   └── js/                   # Módulos ES (app, renderer, websocket, etc.)
├── docs/                # Traducciones del README principal
├── .github/             # CI, plantillas de issues y PR
├── HOW_IT_WORKS.md      # Guía de arquitectura del runtime
├── CONTRIBUTING.md      # Guía de contribución
├── CODE_OF_CONDUCT.md   # Expectativas de la comunidad
├── SECURITY.md          # Política de divulgación de vulnerabilidades
├── LICENSE              # Business Source License 1.1
├── .env.example         # Referencia de variables de entorno
└── REMOTE-CONTROL.md    # Notas operativas de control remoto
```

## Testing

```bash
# Backend
cd agent-api && .venv/bin/python -m pytest tests/ -v

# CLI
cd agent-cli && .venv/bin/python -m pytest tests/ -v

# Developer UI
cd agent-ui && npm test

# Lint + verificación de tipos
cd agent-api && .venv/bin/ruff check src/ tests/
cd agent-cli && .venv/bin/ruff check src/ tests/
```

## Configuración

Las variables de entorno se configuran en `agent-api/.env`:

| Variable | Valor por defecto | Descripción |
|----------|-------------------|-------------|
| `LLM_PROVIDER` | `anthropic` | Backend LLM a usar (`anthropic` o `openai`) |
| `ANTHROPIC_API_KEY` | (requerido para Anthropic) | Tu clave API de Anthropic |
| `ANTHROPIC_BASE_URL` | no definido | Override opcional del endpoint API |
| `OPENAI_API_KEY` | (requerido para OpenAI) | Tu clave API de OpenAI |
| `OPENAI_BASE_URL` | no definido | Endpoint opcional compatible con OpenAI |
| `MODEL` | `claude-sonnet-4-5-20250929` | Modelo por defecto |
| `WORKSPACE_DIR` | `workspace` | Directorio donde el agente crea archivos |
| `ENABLE_MEMORY` | `true` | Memoria entre sesiones |
| `MAX_TURNS` | `50` | Máximo de iteraciones del bucle del agente |
| `MAX_TOKEN_BUDGET` | `200000` | Límite de gasto de tokens por sesión |
| `OPENAGENT_TIMEOUT` | `1800` | Tiempo límite del bucle del agente en CLI (segundos) |

### Uso de proveedores LLM alternativos

```bash
# OpenAI
LLM_PROVIDER=openai OPENAI_API_KEY=tu-clave MODEL=gpt-4.1

# Endpoint compatible con Anthropic
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic MODEL=deepseek-chat

# Cualquier otro backend compatible
# Implementa o amplía la capa de adaptadores en agent-api/src/agent_service/agent/llm.py
```

## Documentación

| Documento | Audiencia | Descripción |
|-----------|-----------|-------------|
| [README.md](../README.md) | Todos | Visión general del producto, setup, tests y configuración |
| [HOW_IT_WORKS.md](../HOW_IT_WORKS.md) | Colaboradores | Recorrido de la arquitectura del runtime |
| [REPOSITORY.md](REPOSITORY.md) | Colaboradores | Diseño del monorepo y notas para mantenedores |
| [CLAUDE.md](../agent-api/CLAUDE.md) | Agentes IA / desarrolladores | Referencia técnica completa |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Colaboradores | Convenciones de ramas, formato de commits, checklist de PRs |
| [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) | Comunidad | Comportamiento esperado y proceso de aplicación |
| [SECURITY.md](../SECURITY.md) | Investigadores de seguridad | Guía para reportar vulnerabilidades en privado |
| [REMOTE-CONTROL.md](../REMOTE-CONTROL.md) | Operadores | Configuración y notas operativas de control remoto |
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
cd agent-ui && npm test
```

También puedes ejecutar todas las verificaciones a la vez con pre-commit:

```bash
pre-commit run --all-files
```

## Licencia

Business Source License 1.1 (BSL 1.1)

Consulta [LICENSE](../LICENSE) para el Additional Use Grant, la Change Date y la Change License.

## Agradecimientos

Construido como una implementación de referencia para aprender haciendo, con patrones de agentes cercanos a producción y una capa de adaptadores LLM independiente del proveedor.
