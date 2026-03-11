<p align="center">
  <h1 align="center">OpenAgent</h1>
  <p align="center">
    一个可以在本地运行、完全理解、自由扩展的开源 AI 编程代理。
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

OpenAgent 是一个功能完整的 AI 编程代理——类似于 Claude Code、Cursor 或 Windsurf——你可以**在本地运行**、**阅读每一行代码**、并**随意修改**。

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

大多数 AI 代理框架要么过于抽象（LangChain），要么过于封闭（Claude Code）。OpenAgent 的特点：

- **可读性强** — 核心循环只有约 30 行。没有框架，没有黑魔法。
- **功能完整** — Web UI、终端 CLI、流式输出、工具、记忆、团队、计划模式。
- **教育友好** — 附带[新手友好指南](../HOW_IT_WORKS.md)和[视频课程大纲](../course-outline.md)。
- **易于扩展** — 20 行代码添加新工具。更换一个适配器即可切换 LLM 提供商。

## 安装

```bash
pip install openagent-app
export ANTHROPIC_API_KEY=你的密钥
openagent
```

PyPI 包：[`openagent-core`](https://pypi.org/project/openagent-core/)（后端库）· [`openagent-app`](https://pypi.org/project/openagent-app/)（CLI）

## 快速开始（开发）

### 前置条件

- Python 3.11+（推荐 3.14）
- [Anthropic API 密钥](https://console.anthropic.com/)

### 方式1a：开发者 Web UI

```bash
# 克隆仓库
git clone https://github.com/anthropics/openagent.git
cd openagent

# 后端
cd agent-api
python -m venv .venv && source .venv/bin/activate
pip install -e .
echo "ANTHROPIC_API_KEY=你的密钥" > .env
uvicorn agent_service.main:app --reload

# 开发者前端（新终端）
cd agent-ui
python3 -m http.server 3500

# 打开 http://localhost:3500
```

### 方式1b：用户 Web UI

```bash
# 后端启动方式同上，然后在新终端中：
cd agent-user-ui
python3 -m http.server 3501

# 打开 http://localhost:3501
```

用户 UI 是一个更轻量的面向用户的界面，采用 Forest Canopy 浅色主题，使用活动指示器代替原始工具块，并提供简化的审批对话框。两个 UI 连接到同一个后端。

### 方式二：终端 CLI

```bash
cd agent-cli
python -m venv .venv && source .venv/bin/activate
pip install -e .
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
                  │   LLM 客户端    │  ◄── 提供商无关（一个适配器即可切换）
                  └────────┬────────┘
                           ▼
                    ┌────────────┐
                    │  Claude API │ （或任何 Anthropic 兼容 API）
                    └────────────┘
```

完整架构图详见 [HOW_IT_WORKS.md](../HOW_IT_WORKS.md#the-complete-architecture)。

## 项目结构

```
codingagents/
├── agent-api/          # FastAPI 后端 + 代理逻辑
│   ├── src/agent_service/
│   │   ├── main.py           # 应用入口
│   │   ├── agent/loop.py     # 核心代理循环（约 1200 行）
│   │   ├── agent/llm.py      # 提供商无关的 LLM 抽象
│   │   ├── agent/tools/      # 所有工具实现
│   │   └── api/websocket.py  # WebSocket 流式处理器
│   ├── skills/               # SKILL.md 专家知识文件
│   ├── prompts/              # PROMPT.md 系统提示预设
│   └── tests/                # 236 个测试
├── agent-cli/          # 终端 CLI 界面
│   ├── src/agent_cli/
│   │   ├── app.py            # REPL 调度器
│   │   ├── renderer.py       # Rich 终端输出
│   │   └── commands.py       # 斜杠命令（/plan、/model 等）
│   └── tests/                # 160 个测试
├── agent-ui/           # 开发者 Web 前端（无需构建步骤）
│   ├── index.html
│   ├── css/styles.css
│   └── js/                   # ES 模块（app、renderer、websocket 等）
├── agent-user-ui/      # 用户 Web 前端（无需构建步骤）
│   ├── index.html
│   ├── css/styles.css        # Forest Canopy 浅色主题
│   └── js/                   # ES 模块（app、renderer、websocket 等）
├── HOW_IT_WORKS.md     # 新手友好的架构指南
├── course-outline.md   # YouTube 课程大纲（24 个视频）
├── CONTRIBUTING.md     # 贡献指南
├── LICENSE             # MIT 许可证
└── .env.example        # 环境变量参考
```

## 测试

```bash
# 后端（236 个测试，约 2 秒）
cd agent-api && .venv/bin/python -m pytest tests/ -v

# CLI（160 个测试，不到 1 秒）
cd agent-cli && .venv/bin/python -m pytest tests/ -v

# 代码检查 + 类型检查
cd agent-api && .venv/bin/ruff check src/ tests/
cd agent-cli && .venv/bin/ruff check src/ tests/
```

## 配置

在 `agent-api/.env` 中设置环境变量：

| 变量 | 默认值 | 描述 |
|------|--------|------|
| `ANTHROPIC_API_KEY` | （必需） | 你的 Anthropic API 密钥 |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | API 端点（用于 DeepSeek、代理等） |
| `MODEL` | `claude-sonnet-4-20250514` | 使用的模型 |
| `WORKSPACE_DIR` | `./workspace` | 代理文件创建位置 |
| `ENABLE_MEMORY` | `true` | 跨会话记忆 |
| `MAX_TURNS` | `50` | 代理循环最大迭代次数 |
| `MAX_TOKEN_BUDGET` | `200000` | 每次会话的 token 消耗上限 |
| `OPENAGENT_TIMEOUT` | `1800` | CLI 代理循环硬超时（秒） |

### 使用其他 LLM 提供商

```bash
# DeepSeek（便宜、快速）
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic MODEL=deepseek-chat

# 使用 Ollama 本地运行（免费）
# 需要 Anthropic 兼容代理
```

## 文档

| 文档 | 受众 | 描述 |
|------|------|------|
| [HOW_IT_WORKS.md](../HOW_IT_WORKS.md) | 初学者 | 包含图表的可视化组件指南 |
| [CLAUDE.md](../agent-api/CLAUDE.md) | AI 代理 / 开发者 | 全面的技术参考 |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | 贡献者 | 分支命名、提交格式、PR 检查清单 |
| [course-outline.md](../course-outline.md) | 教育者 | 24 个视频的 YouTube 课程计划 |
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
```

你也可以使用 pre-commit 一次性运行所有检查：

```bash
pre-commit run --all-files
```

## 许可证

MIT

## 致谢

基于 [Anthropic Claude API](https://docs.anthropic.com/) 构建。本项目的设计模式借鉴了 [Claude Code](https://docs.anthropic.com/en/docs/claude-code)，反映了真实的生产级代理系统架构。
