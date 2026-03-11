<p align="center">
  <h1 align="center">OpenAgent</h1>
  <p align="center">
    ローカルで実行でき、完全に理解でき、自由に拡張できるオープンソースAIコーディングエージェント。
  </p>
  <p align="center">
    <a href="#クイックスタート">クイックスタート</a> &bull;
    <a href="#機能">機能</a> &bull;
    <a href="#アーキテクチャ">アーキテクチャ</a> &bull;
    <a href="#ドキュメント">ドキュメント</a> &bull;
    <a href="#コントリビューション">コントリビューション</a>
  </p>
  <p align="center">
    <strong>他の言語：</strong>&nbsp;
    <a href="../README.md">English</a> &bull;
    <a href="README_zh.md">中文</a> &bull;
    <a href="README_ko.md">한국어</a> &bull;
    <a href="README_es.md">Español</a> &bull;
    <a href="README_fr.md">Français</a>
  </p>
</p>

---

## これは何？

OpenAgentは、Claude Code、Cursor、Windsurfと同等の機能を持つAIコーディングエージェントです。**ローカルで実行**し、**すべてのコードを読み**、**自由にカスタマイズ**できます。

*「認証付きのREST APIを作成して」*とメッセージを入力すると、エージェントは：

1. コードベースを読んでコンテキストを理解する
2. アプローチを計画する（オプションで読み取り専用プランモードで）
3. ツールを使ってコードの作成、コマンドの実行、ファイルの作成を行う
4. 完了前に自分の作業を検証する
5. 結果をリアルタイムでストリーミング返却する

```
あなた: "JWTでユーザー認証を追加して"

エージェント: [思考] まずコードベースを調べます...
             [read_file] src/app.py — Flaskアプリを発見
             [read_file] requirements.txt — 認証ライブラリなし
             [bash] pip install PyJWT bcrypt
             [write_file] src/auth.py — JWTトークン生成
             [edit_file] src/app.py — ログイン/登録ルートを追加
             [bash] python -m pytest tests/ — 12テスト全てパス

             完了！ログインと登録エンドポイントを含むJWT認証を
             追加しました。作成した内容は以下の通りです：...
```

## なぜこのプロジェクト？

ほとんどのAIエージェントフレームワークは、抽象的すぎる（LangChain）か、クローズドすぎる（Claude Code）かのどちらかです。OpenAgentは：

- **読みやすい** — コアループはわずか約30行。フレームワークもマジックもなし。
- **完全な機能** — Web UI、ターミナルCLI、ストリーミング、ツール、メモリ、チーム、プランモード。
- **教育向け** — [初心者向けガイド](../HOW_IT_WORKS.md)と[動画コース大綱](../course-outline.md)付き。
- **拡張しやすい** — 20行で新しいツールを追加。アダプターを1つ変えるだけでLLMプロバイダーを切り替え。

## インストール

```bash
pip install openagent-app
export ANTHROPIC_API_KEY=あなたのキー
openagent
```

PyPI パッケージ：[`openagent-core`](https://pypi.org/project/openagent-core/)（バックエンドライブラリ）· [`openagent-app`](https://pypi.org/project/openagent-app/)（CLI）

## クイックスタート（開発）

### 前提条件

- Python 3.11+（3.14推奨）
- [Anthropic APIキー](https://console.anthropic.com/)

### 方法1a：開発者向けWeb UI

```bash
# リポジトリをクローン
git clone https://github.com/anthropics/openagent.git
cd openagent

# バックエンド
cd agent-api
python -m venv .venv && source .venv/bin/activate
pip install -e .
echo "ANTHROPIC_API_KEY=あなたのキー" > .env
uvicorn agent_service.main:app --reload

# 開発者向けフロントエンド（別のターミナルで）
cd agent-ui
python3 -m http.server 3500

# http://localhost:3500 を開く
```

### 方法1b：ユーザー向けWeb UI

```bash
# バックエンドは上記と同じ。別のターミナルで：
cd agent-user-ui
python3 -m http.server 3501

# http://localhost:3501 を開く
```

ユーザーUIは、Forest Canopyライトテーマを採用した、より軽量なユーザー向けインターフェースです。生のツールブロックの代わりにアクティビティインジケーターを表示し、承認ダイアログもシンプルになっています。両方のUIは同じバックエンドに接続します。

### 方法2：ターミナルCLI

```bash
cd agent-cli
python -m venv .venv && source .venv/bin/activate
pip install -e .
openagent
```

### 方法3：パイプモード（非対話型）

```bash
echo "バイナリサーチの仕組みを説明して" | openagent --no-approval
```

## 機能

### コア機能

| 機能 | 説明 |
|------|------|
| **エージェントループ** | LLMレスポンスをストリーミングし、ツールを実行し、完了まで繰り返すWhileループ |
| **15以上の組み込みツール** | Bash、ファイル読み書き編集、思考、圧縮、スキル、タスク、バックグラウンドコマンド |
| **ストリーミング** | WebSocket経由のリアルタイムトークン単位出力 |
| **ツール承認** | 危険な操作前のオプションの人間確認 |
| **プランモード** | 読み取り専用の探索フェーズ——変更前に計画を設計 |
| **エージェント自律計画** | 複雑なタスクに直面した際、エージェントが自律的にプランモードに入る |
| **サブエージェント** | サブタスク用のフォーカスした子エージェント（探索、コード、計画、調査）を生成 |
| **エージェントチーム** | 非同期メッセージパッシングで並行作業する複数の名前付きエージェント |

### インテリジェント機能

| 機能 | 説明 |
|------|------|
| **3層圧縮** | マイクロ圧縮、トランスクリプト付き自動圧縮、手動圧縮ツール |
| **永続メモリ** | セッション間であなたの好みを記憶 |
| **自己検証** | 完了前にthinkツールで自分の作業をチェック |
| **ラップアップ促進** | ターン制限に近づくと完了を促す |
| **切り詰め回復** | レスポンスがトークン制限に達した場合に自動継続 |

### 開発者体験

| 機能 | 説明 |
|------|------|
| **開発者UI** | マークダウン、シンタックスハイライト、ファイルブラウザ、開発パネルを備えたダークテーマのチャットインターフェース |
| **ユーザーUI** | アクティビティインジケーターとシンプルなダイアログを備えたライトテーマ（Forest Canopy）のユーザー向けインターフェース |
| **ターミナルCLI** | 履歴、オートコンプリート、viモード、セッション永続化を備えたリッチREPL |
| **開発パネル** | ブラウザ内のWebSocketフレームインスペクター |
| **LLMトレーシング** | モデルに送信されたプロンプトとレスポンスの詳細表示 |
| **プリセット** | 切り替え可能なシステムプロンプトのペルソナ（コーディング、オフィス業務など） |
| **スキル** | オンデマンドのエキスパート知識（API設計、Docker、PDF生成など） |

## アーキテクチャ

```
┌──────────────┐  ┌──────────────────┐  ┌──────────────┐
│   agent-ui   │  │  agent-user-ui   │  │  agent-cli   │
│  (開発者向け)│  │   (ユーザー向け) │  │ (ターミナル) │
│  port 3500   │  │   port 3501      │  │              │
└──────┬───────┘  └────────┬─────────┘  └──────┬───────┘
       │ WebSocket         │ WebSocket         │ 直接呼び出し
       └──────────┬────────┘                   │
                  └─────────────┬───────────────┘
                                ▼
                  ┌─────────────────┐
                  │    agent-api     │
                  │    (FastAPI)     │
                  ├─────────────────┤
                  │ エージェントループ│  ◄── while not done: ストリーム → ツール → 繰り返し
                  ├─────────────────┤
                  │  ツールレジストリ │  ◄── bash、ファイル、think、plan_mode、compact...
                  ├─────────────────┤
                  │   LLMクライアント│  ◄── プロバイダー非依存（アダプター1つで切り替え）
                  └────────┬────────┘
                           ▼
                    ┌────────────┐
                    │  Claude API │ （または任意のAnthropic互換API）
                    └────────────┘
```

すべてのサブシステムを含む完全なアーキテクチャ図は[HOW_IT_WORKS.md](../HOW_IT_WORKS.md#the-complete-architecture)にあります。

## プロジェクト構成

```
codingagents/
├── agent-api/          # FastAPIバックエンド + エージェントロジック
│   ├── src/agent_service/
│   │   ├── main.py           # アプリエントリーポイント
│   │   ├── agent/loop.py     # コアエージェントループ（約1200行）
│   │   ├── agent/llm.py      # プロバイダー非依存のLLM抽象化
│   │   ├── agent/tools/      # すべてのツール実装
│   │   └── api/websocket.py  # WebSocketストリーミングハンドラー
│   ├── skills/               # SKILL.mdエキスパート知識ファイル
│   ├── prompts/              # PROMPT.mdシステムプロンプトプリセット
│   └── tests/                # 236テスト
├── agent-cli/          # ターミナルCLIインターフェース
│   ├── src/agent_cli/
│   │   ├── app.py            # REPLオーケストレーター
│   │   ├── renderer.py       # Richターミナル出力
│   │   └── commands.py       # スラッシュコマンド（/plan、/modelなど）
│   └── tests/                # 160テスト
├── agent-ui/           # 開発者向けWebフロントエンド（ビルドステップ不要）
│   ├── index.html
│   ├── css/styles.css
│   └── js/                   # ESモジュール（app、renderer、websocketなど）
├── agent-user-ui/      # ユーザー向けWebフロントエンド（ビルドステップ不要）
│   ├── index.html
│   ├── css/styles.css        # Forest Canopyライトテーマ
│   └── js/                   # ESモジュール（app、renderer、websocketなど）
├── HOW_IT_WORKS.md     # 初心者向けアーキテクチャガイド
├── course-outline.md   # YouTubeコース大綱（24本）
├── CONTRIBUTING.md     # コントリビューションガイドライン
├── LICENSE             # MITライセンス
└── .env.example        # 環境変数リファレンス
```

## テスト

```bash
# バックエンド（236テスト、約2秒）
cd agent-api && .venv/bin/python -m pytest tests/ -v

# CLI（160テスト、1秒未満）
cd agent-cli && .venv/bin/python -m pytest tests/ -v

# リント + 型チェック
cd agent-api && .venv/bin/ruff check src/ tests/
cd agent-cli && .venv/bin/ruff check src/ tests/
```

## 設定

`agent-api/.env`で環境変数を設定します：

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `ANTHROPIC_API_KEY` | （必須） | Anthropic APIキー |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | APIエンドポイント（DeepSeek、プロキシなどに使用） |
| `MODEL` | `claude-sonnet-4-20250514` | 使用するモデル |
| `WORKSPACE_DIR` | `./workspace` | エージェントがファイルを作成する場所 |
| `ENABLE_MEMORY` | `true` | セッション間メモリ |
| `MAX_TURNS` | `50` | エージェントループの最大反復回数 |
| `MAX_TOKEN_BUDGET` | `200000` | セッションあたりのトークン消費上限 |
| `OPENAGENT_TIMEOUT` | `1800` | CLIエージェントループのハードタイムアウト（秒） |

### 代替LLMプロバイダーの使用

```bash
# DeepSeek（安価、高速）
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic MODEL=deepseek-chat

# Ollamaでローカル実行（無料）
# Anthropic互換プロキシが必要
```

## ドキュメント

| ドキュメント | 対象 | 説明 |
|-------------|------|------|
| [HOW_IT_WORKS.md](../HOW_IT_WORKS.md) | 初心者 | 図解付きビジュアルコンポーネントガイド |
| [CLAUDE.md](../agent-api/CLAUDE.md) | AIエージェント/開発者 | 包括的な技術リファレンス |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | コントリビューター | ブランチ命名規則、コミット形式、PRチェックリスト |
| [course-outline.md](../course-outline.md) | 教育者 | 24本のYouTubeコース計画 |
| [.env.example](../.env.example) | 運用担当者 | すべての環境変数と説明 |

## コントリビューション

コントリビューションを歓迎します！詳しくは[CONTRIBUTING.md](../CONTRIBUTING.md)をご覧ください。以下は良い出発点です：

- **新しいツールの追加** — `agent-api/src/agent_service/agent/tools/compact_tool.py`をコピーし、修正して`loop.py`に登録
- **新しいスキルの追加** — `agent-api/skills/your-skill/SKILL.md`を作成
- **新しいプリセットの追加** — `agent-api/prompts/your-preset/PROMPT.md`を作成
- **新しいLLMプロバイダーの追加** — `agent/llm.py`の`LLMClient`プロトコルを実装
- **開発者UIの改善** — `agent-ui/`のファイルを直接編集（ビルドステップ不要）
- **ユーザーUIの改善** — `agent-user-ui/`のファイルを直接編集（ビルドステップ不要）

提出前にテストスイートを実行してください（CIはPRで自動的にこれらを実行します）：

```bash
cd agent-api && .venv/bin/python -m pytest tests/ -v
cd agent-cli && .venv/bin/python -m pytest tests/ -v
```

pre-commitで全チェックを一括実行することもできます：

```bash
pre-commit run --all-files
```

## ライセンス

MIT

## 謝辞

[Anthropic Claude API](https://docs.anthropic.com/)を使用して構築。[Claude Code](https://docs.anthropic.com/en/docs/claude-code)にインスパイアされ、実際のプロダクションエージェントシステムのパターンを反映しています。
