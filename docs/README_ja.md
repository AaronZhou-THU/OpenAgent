<p align="center">
  <h1 align="center">OpenAgent</h1>
  <p align="center">
    実際に動かしながらエージェントの仕組みを学べる、初心者向けのソース公開型AIコーディングエージェントです。
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

OpenAgentは、現代的なエージェントがどう動くのか知りたい初心者のためのAIコーディングエージェントプロジェクトです。**ローカルで実行**し、**すべてのコードを読み**、**実際のコードを変えながら学ぶ**ことができます。

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

多くのAIエージェントプロジェクトは、初心者にとって抽象的すぎるか、学ぶには閉じすぎています。OpenAgentは：

- **読みやすい** — コアループはわずか約30行。フレームワークもマジックもなし。
- **学習向け** — 実行し、追跡し、変更しながらエージェントの仕組みを学びたい初心者向けに設計。
- **完全な機能** — Web UI、ターミナルCLI、ストリーミング、ツール、メモリ、チーム、プランモード。
- **ドキュメントが充実** — コントリビューションガイド、セキュリティポリシー、翻訳、コンポーネント別の技術資料を含みます。
- **LLM非依存** — コアループは単一ベンダーではなく、共通の`LLMClient`インターフェースに対して動作します。
- **拡張しやすい** — 20行で新しいツールを追加でき、プロバイダーアダプターの追加や差し替えでもループ本体は変えません。

## インストール

```bash
cd openagent
python -m venv .venv && source .venv/bin/activate
pip install -e agent-api -e agent-cli
openagent
```

## クイックスタート（開発）

### 前提条件

- Python 3.11+（3.14推奨）
- 利用するLLMプロバイダー、または互換エンドポイントの認証情報

### 方法1a：開発者向けWeb UI

```bash
# フォークまたはローカルコピーをクローン
git clone <your-fork-or-local-copy>
cd openagent

# バックエンド
cd agent-api
python -m venv .venv && source .venv/bin/activate
pip install -e .
cat > .env <<'EOF'
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=あなたのキー
EOF
uvicorn agent_service.main:app --reload

# 開発者向けフロントエンド（別のターミナルで）
cd /path/to/openagent/agent-ui
python3 -m http.server 3500

# http://localhost:3500 を開く
```

### 方法1b：ユーザー向けWeb UI

```bash
# バックエンドは上記と同じ。別のターミナルで：
cd /path/to/openagent/agent-user-ui
python3 -m http.server 3501

# http://localhost:3501 を開く
```

ユーザーUIは、Forest Canopyライトテーマを採用した、より軽量なユーザー向けインターフェースです。生のツールブロックの代わりにアクティビティインジケーターを表示し、承認ダイアログもシンプルになっています。両方のUIは同じバックエンドに接続します。

### 方法2：ターミナルCLI

```bash
cd openagent
python -m venv .venv && source .venv/bin/activate
pip install -e agent-api -e agent-cli
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
                  │   LLMクライアント│  ◄── プロバイダー非依存のアダプター境界
                  └────────┬────────┘
                           ▼
                    ┌────────────┐
                    │ LLMプロバイダー │  （対応済みまたは互換バックエンド）
                    └────────────┘
```

バックエンドの詳細は[agent-api/README.md](../agent-api/README.md)と[agent-api/CLAUDE.md](../agent-api/CLAUDE.md)にあります。

## プロジェクト構成

```
openagent/
├── agent-api/          # FastAPIバックエンド + エージェントロジック
│   ├── src/agent_service/
│   │   ├── main.py           # アプリエントリーポイント
│   │   ├── agent/loop.py     # コアエージェントループ（約1200行）
│   │   ├── agent/llm.py      # プロバイダー非依存のLLM抽象化
│   │   ├── agent/tools/      # すべてのツール実装
│   │   └── api/websocket.py  # WebSocketストリーミングハンドラー
│   ├── skills/               # SKILL.mdエキスパート知識ファイル
│   ├── prompts/              # PROMPT.mdシステムプロンプトプリセット
│   └── tests/                # バックエンドテストスイート
├── agent-cli/          # ターミナルCLIインターフェース
│   ├── src/agent_cli/
│   │   ├── app.py            # REPLオーケストレーター
│   │   ├── renderer.py       # Richターミナル出力
│   │   └── commands.py       # スラッシュコマンド（/plan、/modelなど）
│   └── tests/                # CLIテストスイート
├── agent-ui/           # 開発者向けWebフロントエンド（ビルドステップ不要）
│   ├── index.html
│   ├── css/styles.css
│   └── js/                   # ESモジュール（app、renderer、websocketなど）
├── agent-user-ui/      # ユーザー向けWebフロントエンド（ビルドステップ不要）
│   ├── index.html
│   ├── css/styles.css        # Forest Canopyライトテーマ
│   └── js/                   # ESモジュール（app、renderer、websocketなど）
├── docs/                # ルートREADMEの翻訳
├── .github/             # CI、Issueテンプレート、PRテンプレート
├── HOW_IT_WORKS.md      # ランタイムアーキテクチャガイド
├── CONTRIBUTING.md      # コントリビューションガイドライン
├── CODE_OF_CONDUCT.md   # コミュニティ行動規範
├── SECURITY.md          # 脆弱性報告ポリシー
├── LICENSE              # Business Source License 1.1
├── .env.example         # 環境変数リファレンス
└── REMOTE-CONTROL.md    # リモート操作メモ
```

## テスト

```bash
# バックエンド
cd agent-api && .venv/bin/python -m pytest tests/ -v

# CLI
cd agent-cli && .venv/bin/python -m pytest tests/ -v

# 開発者UI
cd agent-ui && npm test

# リント + 型チェック
cd agent-api && .venv/bin/ruff check src/ tests/
cd agent-cli && .venv/bin/ruff check src/ tests/
```

## 設定

`agent-api/.env`で環境変数を設定します：

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `LLM_PROVIDER` | `anthropic` | 利用するLLMバックエンド（`anthropic` または `openai`） |
| `ANTHROPIC_API_KEY` | （Anthropicで必須） | Anthropic APIキー |
| `ANTHROPIC_BASE_URL` | 未設定 | 任意のAPIエンドポイント上書き |
| `OPENAI_API_KEY` | （OpenAIで必須） | OpenAI APIキー |
| `OPENAI_BASE_URL` | 未設定 | 任意のOpenAI互換エンドポイント |
| `MODEL` | `claude-sonnet-4-5-20250929` | デフォルトモデル |
| `WORKSPACE_DIR` | `workspace` | エージェントがファイルを作成する場所 |
| `ENABLE_MEMORY` | `true` | セッション間メモリ |
| `MAX_TURNS` | `50` | エージェントループの最大反復回数 |
| `MAX_TOKEN_BUDGET` | `200000` | セッションあたりのトークン消費上限 |
| `OPENAGENT_TIMEOUT` | `1800` | CLIエージェントループのハードタイムアウト（秒） |

### 代替LLMプロバイダーの使用

```bash
# OpenAI
LLM_PROVIDER=openai OPENAI_API_KEY=あなたのキー MODEL=gpt-4.1

# Anthropic互換エンドポイント
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic MODEL=deepseek-chat

# その他の互換バックエンド
# agent-api/src/agent_service/agent/llm.py のアダプター層を実装または拡張
```

## ドキュメント

| ドキュメント | 対象 | 説明 |
|-------------|------|------|
| [README.md](../README.md) | 全員 | プロダクト概要、セットアップ、テスト、設定 |
| [HOW_IT_WORKS.md](../HOW_IT_WORKS.md) | コントリビューター | ランタイムアーキテクチャの詳細ガイド |
| [REPOSITORY.md](REPOSITORY.md) | コントリビューター | モノレポ構成とメンテナーメモ |
| [CLAUDE.md](../agent-api/CLAUDE.md) | AIエージェント/開発者 | 包括的な技術リファレンス |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | コントリビューター | ブランチ命名規則、コミット形式、PRチェックリスト |
| [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) | コミュニティ | 期待される行動と運用プロセス |
| [SECURITY.md](../SECURITY.md) | セキュリティ研究者 | 非公開の脆弱性報告ガイド |
| [REMOTE-CONTROL.md](../REMOTE-CONTROL.md) | 運用担当者 | リモート操作設定と運用メモ |
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
cd agent-ui && npm test
```

pre-commitで全チェックを一括実行することもできます：

```bash
pre-commit run --all-files
```

## ライセンス

Business Source License 1.1 (BSL 1.1)

追加利用許諾、Change Date、Change License は [LICENSE](../LICENSE) を参照してください。

## 謝辞

初心者向けの「動かして学ぶ」参照実装として、実運用に近いエージェントパターンと、プロバイダー非依存のLLMアダプター層を組み合わせています。
