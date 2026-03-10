# Agent Instructions — Kiwoom Portfolio Trader

이 파일은 AI 코딩 에이전트(Copilot, Cursor, Claude 등)가 이 프로젝트를 빌드할 때 자동으로 참조하는 지침서입니다.

---

## 프로젝트 개요

키움증권 REST API를 사용한 ETF 포트폴리오 자동 리밸런싱 시스템.
GCP free tier e2-micro VM (고정 IP)에서 Ubuntu crontab으로 매월 1~4일 자동 실행된다 (Day 1: dry-run, Day 2: 주문, Day 3~4: buy retry). Supabase에 상태를 저장하고 Telegram으로 알림을 보낸다.
키움증권 REST API는 IP 화이트리스트 정책이므로 고정 IP가 필요하여 GitHub Actions 대신 GCP VM을 사용한다.

---

## 세션 시작 시 에이전트 행동 (필수)

새 대화 세션이 시작될 때 **항상 아래 순서로 행동**한다:

1. `uv run python scripts/verify_step.py all` 을 실행해 완료된 step을 파악한다.
2. 결과를 사용자에게 보고한다:
   ```
   📊 진행 현황
   - Step 1 ✅ / Step 2 ❌ / ...
   - 다음 진행할 step: Step N
   ```
3. 사용자가 "다음 step 진행해줘" 또는 "step N 해줘"라고 명시적으로 요청할 때만 해당 step 문서를 읽고 시작한다.
4. 요청 없이 먼저 코드를 작성하거나 다음 step을 시작하지 않는다.

---

## 핵심 원칙

1. **docs/ 폴더의 step 문서가 유일한 진실(source of truth)이다.**
   구현 시 반드시 해당 step 문서를 읽고 그대로 따른다.

2. **step 순서를 반드시 지킨다.**
   `step-01` → `step-02` → ... → `step-07` 순서로 진행한다.
   이전 step의 완료 조건이 모두 충족되어야 다음 step으로 넘어간다.

3. **step은 세션 단위로 끊는다.**
   각 step이 완료되면 커밋을 유도하고 세션을 마무리한다.
   다음 step은 새 세션에서 시작한다. 사용자가 명시적으로 요청하지 않으면 절대로 다음 step을 시작하지 않는다.

4. **사용자 입력이 필요한 지점에서 반드시 멈춘다.**
   `⏸️ USER ACTION` 표시가 있는 곳에서 사용자에게 안내하고 대기한다.

5. **외부 API 문서는 URL로 fetch해서 참조한다.**
   특히 kiwoompy의 `llms-full.txt`는 구현 시 반드시 fetch해서 읽는다.

6. **코드 스타일: ruff 규칙을 따른다.**
   `pyproject.toml`의 `[tool.ruff]` 설정 기준.

---

## Step 실행 순서

각 step은 **1세션** 단위다. step이 끝나면 커밋하고 세션을 닫는다.

| Step | 문서 | 핵심 산출물 | 사용자 입력 필요 |
|------|------|------------|:---:|
| 1 | `step-01-project-init.md` | `pyproject.toml`, `uv.lock`, 디렉토리 구조 | ❌ |
| 2 | `step-02-supabase-schema.md` | 5개 테이블 + DDL | ⏸️ Supabase 프로젝트 생성 + DDL 실행 |
| 3 | `step-03-kiwoom-client.md` | `src/trader/kiwoom.py` | ⏸️ 키움 API 키 발급 |
| 4 | `step-04-rebalancing-logic.md` | `src/trader/portfolio.py` | ❌ |
| 5 | `step-05-gcp-cron.md` | `scripts/run_rebalance.sh`, crontab | ⏸️ GCP VM 생성 + IP 화이트리스트 등록 + `.env` 작성 |
| 6 | `step-06-telegram-notifier.md` | `src/trader/notifier.py` | ⏸️ Telegram Bot 생성 |
| 7 | `step-07-main-entry.md` | `src/trader/main.py`, `supabase_client.py` | ❌ |

---

## step 완료 후 세션 마무리 규칙

step이 완료되면 반드시 아래 순서로 마무리한다.

### 완료 후 에이전트 행동 순서

1. `uv run python scripts/verify_step.py <N>` 실행 → 전체 통과 확인
2. 코드가 있는 step이면 ruff lint/format 통과 확인
3. 커밋 안내 (아래 형식)
4. 다음 step 한 줄 예고만 남기고 **세션 종료 유도** — 절대 다음 step 코드 작성 시작 금지

### 커밋 안내 형식

```
📦 Step N 완료! 커밋하고 마무리합시다.

추천 커밋 메시지:
  feat: step N - [한 줄 요약]

커밋 후 새 세션에서 "다음 step 진행해줘"라고 말씀해 주세요.
다음은 Step N+1: [다음 step 한 줄 설명]입니다.
```

### 새 세션에서 이어하기

새 세션이 시작되면 에이전트는 항상 `verify_step.py all`로 현황을 파악하고,
완료된 마지막 step 이후부터 어디서 이어할지 사용자에게 먼저 보고한다.

---

## 사용자 입력 대기 패턴

사용자 입력이 필요한 지점에서는 다음 형태로 안내한다:

```
⏸️ USER ACTION REQUIRED

[무엇을 해야 하는지 구체적 안내]

완료되면 알려주세요.
```

절대로 사용자 대신 API 키를 생성하거나, 외부 서비스에 가입하지 않는다.

---

## 파일 생성 규칙

- `src/trader/` 하위에만 소스 코드를 둔다.
- 모든 Python 파일은 `from __future__ import annotations`로 시작하지 않는다 (Python 3.12+).
- 금액 관련 값은 항상 `Decimal`을 사용한다 (`float` 금지).
- 환경변수는 `os.environ[]`으로 접근한다 (KeyError가 빠른 실패를 보장).
- 비동기 함수는 `async def`로 정의하되, 진입점(`main.py`)에서 `asyncio.run()`으로 실행한다.

---

## 테스트 규칙

- 외부 API를 호출하는 테스트는 반드시 mock 처리한다.
- fixture는 `tests/conftest.py`에 집중한다.
- 테스트 파일명: `test_{모듈명}.py`
- pytest-asyncio의 `asyncio_mode = "auto"` 사용.

---

## 완료 조건 검증

각 step의 "완료 조건" 섹션을 모두 확인한 뒤에만 다음 step으로 진행한다.
`scripts/verify_step.py` 스크립트로 자동 검증 가능한 항목은 자동 검증한다.

### 코드가 포함된 step 완료 후 반드시 실행

소스 코드나 테스트를 작성한 step이 끝나면 아래 두 명령을 **항상** 실행하고 모두 통과해야 다음 step으로 넘어간다:

```bash
# lint + format 검사
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

오류가 있으면 즉시 수정한 뒤 재실행한다.

---

## 실제 동작 테스트 규칙

새 기능이 추가되는 step(3, 4, 6, 7)이 끝날 때마다 **실제 API를 사용한 동작 테스트**를 진행한다.  
자동 실행하지 않고 반드시 사용자에게 안내 → 승인 → 결과 확인 순서로 진행한다.

### 안내 형식

```
🧪 실제 동작 테스트

[무엇을 테스트하는지 한 줄 설명]

기댓값:
- [구체적으로 어떤 결과가 나와야 하는지]
- [Telegram 알림, Supabase 저장 등 눈으로 확인할 수 있는 것]

실행 명령:
  [사용자가 실행할 명령어]

테스트를 진행하시겠습니까?
```

### 결과 확인 형식

사용자가 테스트를 실행한 뒤, 아래 형태로 결과를 확인시킨다:

```
✅ 확인 항목
- [ ] [기대 결과 1] — 실제로 확인되었나요?
- [ ] [기대 결과 2] — 실제로 확인되었나요?

모두 ✅이면 다음 step으로 진행합니다.
문제가 있으면 어떤 항목이 실패했는지 알려주세요.
```

---

## 에러 발생 시

1. 에러 메시지를 사용자에게 보여준다.
2. 해당 step 문서의 관련 섹션을 다시 참조한다.
3. 해결이 불가능하면 사용자에게 상황을 설명하고 선택지를 제시한다.

---

## 참조 URL

| 리소스 | URL |
|--------|-----|
| kiwoompy 전체 API (LLM용) | https://meonji-gogo.github.io/kiwoompy/llms-full.txt |
| kiwoompy 요약 (LLM용) | https://meonji-gogo.github.io/kiwoompy/llms.txt |
| kiwoompy 문서 (사람용) | https://meonji-gogo.github.io/kiwoompy/ |
| Supabase Python SDK | https://supabase.com/docs/reference/python/introduction |
