# Step 1. 프로젝트 초기화 (uv)

## 목표

`uv`를 사용해 재현 가능한(reproducible) Python 프로젝트 환경을 구성한다.  
GitHub Actions 에서도 동일한 환경이 복원될 수 있도록 lock 파일 기반으로 관리한다.

---

## 디렉토리 구조

```
kiwoom-portfolio-trader/
├── .github/
│   └── workflows/
│       ├── rebalance.yml
│       └── ci.yml
├── docs/
│   ├── step-01-project-init.md
│   ├── step-02-supabase-schema.md
│   ├── step-03-kiwoom-client.md
│   ├── step-04-rebalancing-logic.md
│   ├── step-05-github-actions.md
│   ├── step-06-telegram-notifier.md
│   └── step-07-ci.md
├── src/
│   └── trader/
│       ├── __init__.py
│       ├── main.py
│       ├── kiwoom.py
│       ├── portfolio.py
│       ├── supabase_client.py
│       └── notifier.py
├── tests/
│   ├── __init__.py
│   ├── test_portfolio.py
│   ├── test_kiwoom.py
│   └── conftest.py
├── .env.example
├── .python-version
├── pyproject.toml
└── uv.lock
```

---

## 실행 순서

### 1-1. uv 설치 확인

```bash
uv --version
# 없으면: curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 1-2. 프로젝트 초기화

```bash
uv init kiwoom-portfolio-trader
cd kiwoom-portfolio-trader
```

### 1-3. Python 버전 고정

```bash
uv python pin 3.12
# .python-version 파일 생성됨
```

### 1-4. 런타임 의존성 추가

```bash
uv add kiwoompy httpx supabase pydantic python-dotenv
```

| 패키지 | 용도 |
|---|---|
| `kiwoompy` | 키움증권 REST API 클라이언트 (https://meonji-gogo.github.io/kiwoompy/) |
| `httpx` | Telegram Bot API HTTP 클라이언트 (async 지원) |
| `supabase` | Supabase Python SDK |
| `pydantic` | 데이터 모델 검증 (ETF 목록, 주문 등) |
| `python-dotenv` | 로컬 `.env` 파일에서 환경변수 로드 |

### 1-5. 개발 의존성 추가

```bash
uv add --dev pytest pytest-asyncio pytest-mock ruff
```

| 패키지 | 용도 |
|---|---|
| `pytest` | 테스트 러너 |
| `pytest-asyncio` | async 함수 테스트 지원 |
| `pytest-mock` | Kiwoom API mock 처리 |
| `ruff` | 린터 + 포매터 (flake8 + black 대체) |

### 1-6. 소스 패키지 경로 설정 (`pyproject.toml`)

`uv init` 이후 `pyproject.toml`에 아래 내용을 반영한다.

```toml
[project]
name = "kiwoom-portfolio-trader"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "kiwoompy",
    "httpx",
    "supabase",
    "pydantic",
    "python-dotenv",
]

[project.scripts]
trader = "trader.main:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/trader"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

### 1-7. `.env.example` 생성

```dotenv
# Kiwoom OpenAPI
KIWOOM_ENV=demo           # demo | real
KIWOOM_APP_KEY=your_app_key_here
KIWOOM_APP_SECRET=your_app_secret_here

# Supabase
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=your_service_role_key_here

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# Runtime
DRY_RUN=false
```

> 실제 값은 `.env`에 작성하고, `.gitignore`에 `.env` 추가.

### 1-8. `.gitignore` 설정

```
.env
__pycache__/
.pytest_cache/
.ruff_cache/
dist/
*.egg-info/
```

---

## 검증

```bash
# 의존성 설치 확인
uv sync

# 패키지 경로 확인
uv run python -c "import trader; print(trader.__file__)"

# 린터 확인
uv run ruff check src/

# 테스트 확인 (빈 테스트)
uv run pytest
```

---

## 완료 조건

- [ ] `uv sync` 가 오류 없이 실행됨
- [ ] `uv.lock` 파일이 생성됨
- [ ] `src/trader/` 패키지가 import 가능
- [ ] `uv run ruff check src/` 가 통과
- [ ] `.env.example` 이 커밋됨, `.env` 는 `.gitignore` 처리

---

## 검증 명령

```bash
uv run python scripts/verify_step.py 1
```

모든 항목 ✅ 이면 완료입니다.

---

## 📦 커밋하고 세션 마무리

```bash
git add .
git commit -m "feat: step 1 - project init with uv"
```

커밋 후 이 세션은 여기서 닫습니다.
다음 세션에서 에이전트에게 **"다음 step 진행해줘"** 라고 말하면 이어서 시작합니다.

**다음:** `step-02-supabase-schema.md` — Supabase 테이블 스키마 설계
