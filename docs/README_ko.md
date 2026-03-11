<p align="center">
  <h1 align="center">OpenAgent</h1>
  <p align="center">
    로컬에서 실행하고, 완전히 이해하고, 자유롭게 확장할 수 있는 오픈소스 AI 코딩 에이전트.
  </p>
  <p align="center">
    <a href="#빠른-시작">빠른 시작</a> &bull;
    <a href="#기능">기능</a> &bull;
    <a href="#아키텍처">아키텍처</a> &bull;
    <a href="#문서">문서</a> &bull;
    <a href="#기여하기">기여하기</a>
  </p>
  <p align="center">
    <strong>다른 언어:</strong>&nbsp;
    <a href="../README.md">English</a> &bull;
    <a href="README_zh.md">中文</a> &bull;
    <a href="README_ja.md">日本語</a> &bull;
    <a href="README_es.md">Español</a> &bull;
    <a href="README_fr.md">Français</a>
  </p>
</p>

---

## 이것은 무엇인가요?

OpenAgent는 Claude Code, Cursor, Windsurf와 유사한 완전한 기능의 AI 코딩 에이전트입니다. **로컬에서 실행**하고, **모든 코드를 읽고**, **원하는 대로 수정**할 수 있습니다.

*"인증 기능이 있는 REST API 만들어줘"*라고 메시지를 입력하면, 에이전트는:

1. 코드베이스를 읽어 컨텍스트를 파악합니다
2. 접근 방식을 계획합니다 (선택적으로 읽기 전용 플랜 모드에서)
3. 도구를 사용하여 코드 작성, 명령 실행, 파일 생성을 합니다
4. 완료 전에 자신의 작업을 검증합니다
5. 결과를 실시간으로 스트리밍합니다

```
사용자: "JWT로 사용자 인증 추가해줘"

에이전트: [생각] 먼저 코드베이스를 살펴보겠습니다...
         [read_file] src/app.py — Flask 앱 발견
         [read_file] requirements.txt — 인증 라이브러리 없음
         [bash] pip install PyJWT bcrypt
         [write_file] src/auth.py — JWT 토큰 생성
         [edit_file] src/app.py — 로그인/회원가입 라우트 추가
         [bash] python -m pytest tests/ — 12개 테스트 모두 통과

         완료! 로그인과 회원가입 엔드포인트가 포함된
         JWT 인증을 추가했습니다. 생성한 내용은 다음과 같습니다: ...
```

## 왜 이 프로젝트인가요?

대부분의 AI 에이전트 프레임워크는 너무 추상적이거나(LangChain) 너무 폐쇄적입니다(Claude Code). OpenAgent는:

- **읽기 쉽습니다** — 핵심 루프는 약 30줄. 프레임워크도, 마법도 없습니다.
- **완전합니다** — Web UI, 터미널 CLI, 스트리밍, 도구, 메모리, 팀, 플랜 모드.
- **교육적입니다** — [초보자 가이드](../HOW_IT_WORKS.md)와 [영상 강좌 개요](../course-outline.md) 포함.
- **확장 가능합니다** — 20줄로 새 도구 추가. 어댑터 하나만 바꾸면 LLM 제공업체 교체.

## 설치

```bash
pip install openagent-app
export ANTHROPIC_API_KEY=당신의키
openagent
```

PyPI 패키지: [`openagent-core`](https://pypi.org/project/openagent-core/) (백엔드 라이브러리) · [`openagent-app`](https://pypi.org/project/openagent-app/) (CLI)

## 빠른 시작 (개발)

### 사전 요구 사항

- Python 3.11+ (3.14 권장)
- [Anthropic API 키](https://console.anthropic.com/)

### 방법 1a: 개발자 Web UI

```bash
# 레포지토리 클론
git clone https://github.com/anthropics/openagent.git
cd openagent

# 백엔드
cd agent-api
python -m venv .venv && source .venv/bin/activate
pip install -e .
echo "ANTHROPIC_API_KEY=여기에-키-입력" > .env
uvicorn agent_service.main:app --reload

# 개발자 프론트엔드 (새 터미널)
cd agent-ui
python3 -m http.server 3500

# http://localhost:3500 열기
```

### 방법 1b: 사용자 Web UI

```bash
# 위와 동일한 백엔드를 실행한 후, 새 터미널에서:
cd agent-user-ui
python3 -m http.server 3501

# http://localhost:3501 열기
```

사용자 UI는 Forest Canopy 라이트 테마, 원시 도구 블록 대신 활동 표시기, 간소화된 승인 다이얼로그를 갖춘 가벼운 사용자 대면 인터페이스입니다. 두 UI 모두 동일한 백엔드에 연결됩니다.

### 방법 2: 터미널 CLI

```bash
cd agent-cli
python -m venv .venv && source .venv/bin/activate
pip install -e .
openagent
```

### 방법 3: 파이프 모드 (비대화형)

```bash
echo "이진 탐색이 어떻게 작동하는지 설명해줘" | openagent --no-approval
```

## 기능

### 핵심 기능

| 기능 | 설명 |
|------|------|
| **에이전트 루프** | LLM 응답을 스트리밍하고, 도구를 실행하고, 완료될 때까지 반복하는 While 루프 |
| **15개 이상의 내장 도구** | Bash, 파일 읽기/쓰기/편집, 생각, 압축, 스킬, 태스크, 백그라운드 명령 |
| **스트리밍** | WebSocket을 통한 실시간 토큰 단위 출력 |
| **도구 승인** | 위험한 작업 전 선택적 사용자 확인 |
| **플랜 모드** | 읽기 전용 탐색 단계 — 변경 전에 계획을 설계 |
| **에이전트 자율 계획** | 복잡한 작업에 직면하면 에이전트가 자율적으로 플랜 모드 진입 |
| **서브 에이전트** | 하위 작업을 위한 집중 자식 에이전트 (탐색, 코드, 계획, 연구) 생성 |
| **에이전트 팀** | 비동기 메시지 전달로 병렬 작업하는 다수의 이름 있는 에이전트 |

### 지능형 기능

| 기능 | 설명 |
|------|------|
| **3단계 압축** | 마이크로 압축, 트랜스크립트 포함 자동 압축, 수동 압축 도구 |
| **영구 메모리** | 세션 간 사용자 선호도 기억 |
| **자기 검증** | 완료 전 think 도구로 자체 작업 확인 |
| **마무리 알림** | 턴 제한에 가까워지면 완료 안내 |
| **잘림 복구** | 응답이 토큰 한도에 도달하면 자동 계속 |

### 개발자 경험

| 기능 | 설명 |
|------|------|
| **개발자 UI** | 마크다운, 구문 강조, 파일 브라우저, 개발자 패널이 포함된 다크 테마 채팅 인터페이스 |
| **사용자 UI** | 활동 표시기, 간소화된 다이얼로그를 갖춘 라이트 테마(Forest Canopy) 사용자 대면 인터페이스 |
| **터미널 CLI** | 히스토리, 자동완성, vi 모드, 세션 지속성을 갖춘 Rich REPL |
| **개발자 패널** | 브라우저 내 원시 WebSocket 프레임 인스펙터 |
| **LLM 추적** | 모델에 전송되는 정확한 프롬프트와 응답 확인 |
| **프리셋** | 교체 가능한 시스템 프롬프트 페르소나 (코딩, 오피스 생산성 등) |
| **스킬** | 온디맨드 전문 지식 (API 설계, Docker, PDF 생성 등) |

## 아키텍처

```
┌──────────────┐  ┌──────────────────┐  ┌──────────────┐
│   agent-ui   │  │  agent-user-ui   │  │  agent-cli   │
│  (개발자)    │  │     (사용자)     │  │  (터미널)    │
│  port 3500   │  │   port 3501      │  │              │
└──────┬───────┘  └────────┬─────────┘  └──────┬───────┘
       │ WebSocket         │ WebSocket         │ 직접 호출
       └──────────┬────────┘                   │
                  └─────────────┬───────────────┘
                                ▼
                  ┌─────────────────┐
                  │    agent-api     │
                  │    (FastAPI)     │
                  ├─────────────────┤
                  │  에이전트 루프   │  ◄── while not done: 스트림 → 도구 → 반복
                  ├─────────────────┤
                  │  도구 레지스트리 │  ◄── bash, 파일, think, plan_mode, compact...
                  ├─────────────────┤
                  │  LLM 클라이언트  │  ◄── 제공업체 무관 (어댑터 하나로 교체)
                  └────────┬────────┘
                           ▼
                    ┌────────────┐
                    │  Claude API │ (또는 Anthropic 호환 API)
                    └────────────┘
```

전체 아키텍처 다이어그램과 모든 하위 시스템은 [HOW_IT_WORKS.md](../HOW_IT_WORKS.md#the-complete-architecture)에서 확인할 수 있습니다.

## 프로젝트 구조

```
codingagents/
├── agent-api/          # FastAPI 백엔드 + 에이전트 로직
│   ├── src/agent_service/
│   │   ├── main.py           # 앱 엔트리포인트
│   │   ├── agent/loop.py     # 핵심 에이전트 루프 (~1200줄)
│   │   ├── agent/llm.py      # 제공업체 무관 LLM 추상화
│   │   ├── agent/tools/      # 모든 도구 구현
│   │   └── api/websocket.py  # WebSocket 스트리밍 핸들러
│   ├── skills/               # SKILL.md 전문 지식 파일
│   ├── prompts/              # PROMPT.md 시스템 프롬프트 프리셋
│   └── tests/                # 236개 테스트
├── agent-cli/          # 터미널 CLI 인터페이스
│   ├── src/agent_cli/
│   │   ├── app.py            # REPL 오케스트레이터
│   │   ├── renderer.py       # Rich 터미널 출력
│   │   └── commands.py       # 슬래시 명령어 (/plan, /model 등)
│   └── tests/                # 160개 테스트
├── agent-ui/           # 개발자 웹 프론트엔드 (빌드 단계 없음)
│   ├── index.html
│   ├── css/styles.css
│   └── js/                   # ES 모듈 (app, renderer, websocket 등)
├── agent-user-ui/      # 사용자 대면 웹 프론트엔드 (빌드 단계 없음)
│   ├── index.html
│   ├── css/styles.css        # Forest Canopy 라이트 테마
│   └── js/                   # ES 모듈 (app, renderer, websocket 등)
├── HOW_IT_WORKS.md     # 초보자 친화적 아키텍처 가이드
├── course-outline.md   # YouTube 강좌 개요 (24개 영상)
├── CONTRIBUTING.md     # 기여 가이드라인
├── LICENSE             # MIT 라이선스
└── .env.example        # 환경 변수 참조
```

## 테스트

```bash
# 백엔드 (236개 테스트, ~2초)
cd agent-api && .venv/bin/python -m pytest tests/ -v

# CLI (160개 테스트, <1초)
cd agent-cli && .venv/bin/python -m pytest tests/ -v

# 린트 + 타입 검사
cd agent-api && .venv/bin/ruff check src/ tests/
cd agent-cli && .venv/bin/ruff check src/ tests/
```

## 설정

`agent-api/.env`에서 환경 변수를 설정합니다:

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `ANTHROPIC_API_KEY` | (필수) | Anthropic API 키 |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | API 엔드포인트 (DeepSeek, 프록시 등에 사용) |
| `MODEL` | `claude-sonnet-4-20250514` | 사용할 모델 |
| `WORKSPACE_DIR` | `./workspace` | 에이전트가 파일을 생성하는 위치 |
| `ENABLE_MEMORY` | `true` | 세션 간 메모리 |
| `MAX_TURNS` | `50` | 에이전트 루프 최대 반복 횟수 |
| `MAX_TOKEN_BUDGET` | `200000` | 세션당 토큰 사용 한도 |
| `OPENAGENT_TIMEOUT` | `1800` | CLI 에이전트 루프 하드 타임아웃 (초) |

### 대체 LLM 제공업체 사용

```bash
# DeepSeek (저렴, 빠름)
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic MODEL=deepseek-chat

# Ollama로 로컬 실행 (무료)
# Anthropic 호환 프록시 필요
```

## 문서

| 문서 | 대상 | 설명 |
|------|------|------|
| [HOW_IT_WORKS.md](../HOW_IT_WORKS.md) | 초보자 | 다이어그램이 포함된 시각적 컴포넌트 가이드 |
| [CLAUDE.md](../agent-api/CLAUDE.md) | AI 에이전트 / 개발자 | 포괄적인 기술 레퍼런스 |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | 기여자 | 브랜치 명명, 커밋 형식, PR 체크리스트 |
| [course-outline.md](../course-outline.md) | 교육자 | 24개 영상 YouTube 강좌 계획 |
| [.env.example](../.env.example) | 운영자 | 설명이 포함된 모든 환경 변수 |

## 기여하기

기여를 환영합니다! 자세한 가이드라인은 [CONTRIBUTING.md](../CONTRIBUTING.md)를 참조하세요. 좋은 시작점:

- **새 도구 추가** — `agent-api/src/agent_service/agent/tools/compact_tool.py`를 복사하고, 수정 후 `loop.py`에 등록
- **새 스킬 추가** — `agent-api/skills/your-skill/SKILL.md` 생성
- **새 프리셋 추가** — `agent-api/prompts/your-preset/PROMPT.md` 생성
- **새 LLM 제공업체 추가** — `agent/llm.py`의 `LLMClient` 프로토콜 구현
- **개발자 UI 개선** — `agent-ui/`의 파일을 직접 편집 (빌드 단계 불필요)
- **사용자 UI 개선** — `agent-user-ui/`의 파일을 직접 편집 (빌드 단계 불필요)

제출 전 테스트 스위트를 실행해 주세요 (CI가 PR에서 자동으로 실행합니다):

```bash
cd agent-api && .venv/bin/python -m pytest tests/ -v
cd agent-cli && .venv/bin/python -m pytest tests/ -v
```

pre-commit으로 모든 검사를 한 번에 실행할 수도 있습니다:

```bash
pre-commit run --all-files
```

## 라이선스

MIT

## 감사의 말

[Anthropic Claude API](https://docs.anthropic.com/)로 구축. [Claude Code](https://docs.anthropic.com/en/docs/claude-code)에서 영감을 받아, 실제 프로덕션 에이전트 시스템의 패턴을 반영합니다.
