<p align="center">
  <h1 align="center">OpenAgent</h1>
  <p align="center">
    一个面向初学者、源码可见的 AI 编程代理项目，让你通过亲手运行和修改代码来学习 Agent 的工作方式。
  </p>
  <p align="center">
    <a href="#快速开始">快速开始</a> &bull;
    <a href="#功能特性">功能特性</a> &bull;
    <a href="#架构">架构</a> &bull;
    <a href="#文档">文档</a> &bull;
    <a href="#参与贡献">参与贡献</a>
  </p>
  <p align="center">
    <strong>其他语言：</strong>&nbsp;
    <a href="../README.md">English</a> &bull;
    <a href="README_ja.md">日本語</a> &bull;
    <a href="README_ko.md">한국어</a> &bull;
    <a href="README_es.md">Español</a> &bull;
    <a href="README_fr.md">Français</a>
  </p>
</p>

---

## 这是什么？

OpenAgent 是一个面向初学者的 AI 编程代理项目，适合那些对现代 Agent 如何工作感到好奇的人。你可以**在本地运行它**、**阅读每一行代码**，并且**通过修改真实代码来学习**，而不是只看抽象图示。

你输入一条消息，比如*"创建一个带认证功能的 REST API"*，代理会：

1. 阅读你的代码库以理解上下文
2. 制定计划（可选择在只读计划模式下进行）
3. 使用工具编写代码、运行命令、创建文件
4. 在完成前自行验证工作成果
5. 实时流式返回结果

```
你: "添加 JWT 用户认证"

代理: [思考] 让我先浏览一下代码库...
      [read_file] src/app.py — 找到了 Flask 应用
      [read_file] requirements.txt — 还没有认证库
      [bash] pip install PyJWT bcrypt
      [write_file] src/auth.py — JWT 令牌生成
      [edit_file] src/app.py — 添加了登录/注册路由
      [bash] python -m pytest tests/ — 全部 12 个测试通过

      完成！我已经添加了包含登录和注册端点的 JWT 认证。
      以下是我创建的内容：...
```

## 为什么选择这个项目？

大多数 AI 代理项目对初学者来说要么过于抽象，要么过于封闭。OpenAgent 的特点：

- **可读性强** — 核心循环只有约 30 行。没有框架，没有黑魔法。
- **教育友好** — 专为想通过动手实践理解 Agent 架构的初学者设计。
- **功能完整** — Web UI、终端 CLI、流式输出、工具、记忆、团队、计划模式。
- **文档完善** — 包含贡献指南、安全策略、翻译文档，以及面向组件的技术参考资料。
- **模型无关** — 核心循环面向统一的 `LLMClient` 接口，而不是绑定某一家模型厂商。
- **易于扩展** — 20 行代码添加新工具；新增或替换提供商适配器时无需重写核心循环。

## 安装

```bash
cd openagent
python -m venv .venv && source .venv/bin/activate
pip install -e agent-api -e agent-cli
openagent
```

## 快速开始（开发）

### 前置条件

- Python 3.11+（推荐 3.14）
- 你所选择的 LLM 提供商或兼容端点的凭据

### 已发布的 PyPI 包

OpenAgent 也已经发布到 PyPI：

- [`openagent-core`](https://pypi.org/project/openagent-core/) — 后端库
- [`openagent-app`](https://pypi.org/project/openagent-app/) — 终端 CLI

当前发布版本：**0.1.1**。

如果你只想直接安装打包好的 CLI，而不是克隆整个 monorepo：

```bash
pip install openagent-app
openagent
```

### 方式1a：开发者 Web UI

```bash
# 克隆你的 fork 或本地副本
git clone <your-fork-or-local-copy>
cd openagent

# 后端
cd agent-api
python -m venv .venv && source .venv/bin/activate
pip install -e .
cat > .env <<'EOF'
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=你的密钥
EOF
uvicorn agent_service.main:app --reload

# 开发者前端（新终端）
cd /path/to/openagent/agent-ui
python3 -m http.server 3500

# 打开 http://localhost:3500
```

### 方式1b：用户 Web UI

```bash
# 后端启动方式同上，然后在新终端中：
cd /path/to/openagent/agent-user-ui
python3 -m http.server 3501

# 打开 http://localhost:3501
```

用户 UI 是一个更轻量的面向用户的界面，采用 Forest Canopy 浅色主题，使用活动指示器代替原始工具块，并提供简化的审批对话框。两个 UI 连接到同一个后端。

### 方式二：终端 CLI

```bash
cd openagent
python -m venv .venv && source .venv/bin/activate
pip install -e agent-api -e agent-cli
openagent
```

### 方式三：管道模式（非交互式）

```bash
echo "解释二分查找的原理" | openagent --no-approval
```

## 功能特性

### 核心功能

| 功能 | 描述 |
|------|------|
| **代理循环** | While 循环：流式 LLM 响应、执行工具、重复直到完成 |
| **15+ 内置工具** | Bash、文件读写编辑、思考、压缩、技能、任务、后台命令 |
| **流式输出** | 通过 WebSocket 实时逐 token 输出 |
| **工具审批** | 可选的人工确认，在危险操作前暂停 |
| **计划模式** | 只读探索阶段——代理先设计计划再修改代码 |
| **代理自主规划** | 代理面对复杂任务时自主进入计划模式 |
| **子代理** | 为子任务生成专注的子代理（探索、编码、规划、研究） |
| **代理团队** | 多个命名代理并行工作，通过异步消息传递协作 |

### 智能特性

| 功能 | 描述 |
|------|------|
| **三层压缩** | 微压缩、带记录的自动压缩、手动压缩工具 |
| **持久记忆** | 代理跨会话记住你的偏好 |
| **自我验证** | 使用 think 工具在完成前检查自己的工作 |
| **收尾提醒** | 接近轮次限制时提示完成 |
| **截断恢复** | 响应达到 token 上限时自动继续 |

### 开发者体验

| 功能 | 描述 |
|------|------|
| **开发者 UI** | 暗色主题聊天界面，支持 Markdown、语法高亮、文件浏览器、开发面板 |
| **用户 UI** | 浅色主题（Forest Canopy）面向用户的界面，支持活动指示器、简化对话框 |
| **终端 CLI** | 富文本 REPL，支持历史记录、自动补全、vi 模式、会话持久化 |
| **开发面板** | 浏览器中的原始 WebSocket 帧检查器 |
| **LLM 追踪** | 查看发送给模型的精确提示和响应 |
| **预设** | 可切换的系统提示人设（编码、办公等） |
| **技能** | 按需加载的专家知识（API 设计、Docker、PDF 生成等） |

## 架构

```
┌──────────────┐  ┌──────────────────┐  ┌──────────────┐
│   agent-ui   │  │  agent-user-ui   │  │  agent-cli   │
│  (开发者)    │  │     (用户)       │  │  (终端)      │
│  port 3500   │  │   port 3501      │  │              │
└──────┬───────┘  └────────┬─────────┘  └──────┬───────┘
       │ WebSocket         │ WebSocket         │ 直接调用
       └──────────┬────────┘                   │
                  └─────────────┬───────────────┘
                                ▼
                  ┌─────────────────┐
                  │    agent-api     │
                  │    (FastAPI)     │
                  ├─────────────────┤
                  │   代理循环       │  ◄── while not done: 流式 → 工具 → 重复
                  ├─────────────────┤
                  │   工具注册表     │  ◄── bash、文件、think、plan_mode、compact...
                  ├─────────────────┤
                  │   LLM 客户端    │  ◄── 提供商无关的适配器边界
                  └────────┬────────┘
                           ▼
                    ┌────────────┐
                    │  LLM 提供商 │ （任何已支持或兼容的后端）
                    └────────────┘
```

更多后端架构细节见 [agent-api/README.md](../agent-api/README.md) 和 [agent-api/CLAUDE.md](../agent-api/CLAUDE.md)。

## 项目结构

```
openagent/
├── agent-api/          # FastAPI 后端 + 代理逻辑
│   ├── src/agent_service/
│   │   ├── main.py           # 应用入口
│   │   ├── agent/loop.py     # 核心代理循环（约 1200 行）
│   │   ├── agent/llm.py      # 提供商无关的 LLM 抽象
│   │   ├── agent/tools/      # 所有工具实现
│   │   └── api/websocket.py  # WebSocket 流式处理器
│   ├── skills/               # SKILL.md 专家知识文件
│   ├── prompts/              # PROMPT.md 系统提示预设
│   └── tests/                # 后端测试套件
├── agent-cli/          # 终端 CLI 界面
│   ├── src/agent_cli/
│   │   ├── app.py            # REPL 调度器
│   │   ├── renderer.py       # Rich 终端输出
│   │   └── commands.py       # 斜杠命令（/plan、/model 等）
│   └── tests/                # CLI 测试套件
├── agent-ui/           # 开发者 Web 前端（无需构建步骤）
│   ├── index.html
│   ├── css/styles.css
│   └── js/                   # ES 模块（app、renderer、websocket 等）
├── agent-user-ui/      # 用户 Web 前端（无需构建步骤）
│   ├── index.html
│   ├── css/styles.css        # Forest Canopy 浅色主题
│   └── js/                   # ES 模块（app、renderer、websocket 等）
├── docs/                # 根 README 的多语言翻译
├── .github/             # CI、Issue 模板、PR 模板
├── HOW_IT_WORKS.md      # 运行时架构指南
├── CONTRIBUTING.md      # 贡献指南
├── CODE_OF_CONDUCT.md   # 社区行为准则
├── SECURITY.md          # 漏洞披露策略
├── LICENSE              # Business Source License 1.1
├── .env.example         # 环境变量参考
└── REMOTE-CONTROL.md    # 远程控制使用说明
```

## 测试

```bash
# 后端
cd agent-api && .venv/bin/python -m pytest tests/ -v

# CLI
cd agent-cli && .venv/bin/python -m pytest tests/ -v

# 开发者 UI
cd agent-ui && npm test

# 代码检查 + 类型检查
cd agent-api && .venv/bin/ruff check src/ tests/
cd agent-cli && .venv/bin/ruff check src/ tests/
```

## 配置

在 `agent-api/.env` 中设置环境变量：

| 变量 | 默认值 | 描述 |
|------|--------|------|
| `LLM_PROVIDER` | `anthropic` | 要使用的 LLM 后端（`anthropic` 或 `openai`） |
| `ANTHROPIC_API_KEY` | （Anthropic 必需） | 你的 Anthropic API 密钥 |
| `ANTHROPIC_BASE_URL` | 未设置 | 可选的 API 端点覆盖 |
| `OPENAI_API_KEY` | （OpenAI 必需） | 你的 OpenAI API 密钥 |
| `OPENAI_BASE_URL` | 未设置 | 可选的 OpenAI 兼容端点 |
| `MODEL` | `claude-sonnet-4-5-20250929` | 默认模型 |
| `SUBAGENT_MODEL` | 未设置 | 子代理的可选模型覆盖 |
| `TEAMMATE_MODEL` | 未设置 | 队友代理的可选模型覆盖 |
| `COMPACT_MODEL` | 未设置 | 上下文压缩的可选模型覆盖 |
| `THINKING_ENABLED` | `false` | 新会话默认是否启用模型思考输出 |
| `THINKING_EFFORT` | `high` | 默认思考强度（`high` 或 `max`） |
| `WORKSPACE_DIR` | `workspace` | 代理文件创建位置 |
| `ENABLE_MEMORY` | `true` | 跨会话记忆 |
| `MAX_TURNS` | `50` | 代理循环最大迭代次数 |
| `MAX_TOKEN_BUDGET` | `200000` | 每次会话的 token 消耗上限 |
| `OPENAGENT_TIMEOUT` | `1800` | CLI 代理循环硬超时（秒） |

### 使用其他 LLM 提供商

```bash
# OpenAI
LLM_PROVIDER=openai OPENAI_API_KEY=你的密钥 MODEL=gpt-4.1

# Anthropic 兼容端点
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic MODEL=deepseek-v4-pro

# DeepSeek V4，并默认显示思考输出
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic MODEL=deepseek-v4-pro SUBAGENT_MODEL=deepseek-v4-flash THINKING_ENABLED=true THINKING_EFFORT=max

# 其他兼容后端
# 在 agent-api/src/agent_service/agent/llm.py 中实现或扩展适配层
```

## 文档

| 文档 | 受众 | 描述 |
|------|------|------|
| [README.md](../README.md) | 所有人 | 产品概览、安装、测试和配置 |
| [HOW_IT_WORKS.md](../HOW_IT_WORKS.md) | 贡献者 | 运行时架构详解 |
| [REPOSITORY.md](REPOSITORY.md) | 贡献者 | 单体仓库结构与维护说明 |
| [CLAUDE.md](../agent-api/CLAUDE.md) | AI 代理 / 开发者 | 全面的技术参考 |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | 贡献者 | 分支命名、提交格式、PR 检查清单 |
| [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) | 社区 | 行为规范与执行流程 |
| [SECURITY.md](../SECURITY.md) | 安全研究人员 | 私密漏洞披露指引 |
| [REMOTE-CONTROL.md](../REMOTE-CONTROL.md) | 运维人员 | 远程控制设置与运维说明 |
| [.env.example](../.env.example) | 运维人员 | 所有环境变量及其描述 |

## 参与贡献

欢迎贡献！完整指南请参阅 [CONTRIBUTING.md](../CONTRIBUTING.md)。以下是一些好的起点：

- **添加新工具** — 复制 `agent-api/src/agent_service/agent/tools/compact_tool.py`，修改后在 `loop.py` 中注册
- **添加新技能** — 创建 `agent-api/skills/你的技能/SKILL.md`
- **添加新预设** — 创建 `agent-api/prompts/你的预设/PROMPT.md`
- **添加新 LLM 提供商** — 在 `agent/llm.py` 中实现 `LLMClient` 协议
- **改进开发者 UI** — 直接编辑 `agent-ui/` 中的文件（无需构建步骤）
- **改进用户 UI** — 直接编辑 `agent-user-ui/` 中的文件（无需构建步骤）

提交前请运行测试（CI 会在 PR 上自动运行这些测试）：

```bash
cd agent-api && .venv/bin/python -m pytest tests/ -v
cd agent-cli && .venv/bin/python -m pytest tests/ -v
cd agent-ui && npm test
```

你也可以使用 pre-commit 一次性运行所有检查：

```bash
pre-commit run --all-files
```

## 许可证

Business Source License 1.1（BSL 1.1）

详细条款、变更日期与后续变更许可证见 [LICENSE](../LICENSE)。

## 致谢

这是一个面向初学者的“边做边学”参考实现，采用接近生产环境的 Agent 模式，并通过提供商无关的 LLM 适配层保持灵活性。
