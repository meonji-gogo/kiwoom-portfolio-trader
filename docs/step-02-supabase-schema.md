# Step 2. Supabase 스키마 설계

## 목표

포트폴리오 자동매매 시스템의 **상태(state)** 와 **이력(history)** 을 저장할 Supabase(PostgreSQL) 스키마를 설계한다.  
GitHub Actions 코드는 Supabase에서 전략 파라미터와 목표 비중을 읽고, 실행 결과를 기록한다.

---

## 실행 정책 요약

| 날짜 | 모드 | 조건 | 동작 |
|---|---|---|---|
| 매월 1일 | `full / dry_run=true` | 이번 주기 dry run 없음 + N개월 경과 | **dry run** (`order_plans` 생성 + Telegram 예고, 주문 없음) |
| 매월 1일 | - | N개월 미경과 | 조용히 종료 |
| 매월 2일 | `full / dry_run=false` | 1일 dry run 완료 | **full rebalancing** (매도 → 매수) |
| 매월 2일 | - | 1일 dry run 없음 | 조용히 종료 |
| 매월 3일 | `buy_retry` | 2일 full run 완료 + 미체결 매수 있음 | **buy retry** |
| 매월 3일 | - | 미체결 없음 | 조용히 종료 |
| 매월 4일 | `buy_retry` | 미체결 매수 여전히 있음 | **buy retry** (마지막 시도) |
| 매월 4일 | - | 미체결 없음 | 조용히 종료 |

---

## 테이블 구성 개요

| 테이블 | 역할 | 성격 |
|---|---|---|
| `strategies` | 리밸런싱 전략 파라미터 관리 | 설정 (수동 관리) |
| `portfolios` | ETF 목표 비중 정의 | 설정 (수동 관리) |
| `rebalancing_runs` | 리밸런싱 실행 단위 (1 run = 1회 시도) | 이력 (자동 기록) |
| `order_plans` | run 시점 주문 계획 산출 결과 (lot-size rounding 후) | 이력 (자동 기록) |
| `order_executions` | 개별 주문 체결 내역 | 이력 (자동 기록) |

---

## DDL

### 2-1. `strategies`

전략 파라미터를 key-value 형태로 저장한다.  
코드 변경 없이 Supabase에서 직접 파라미터를 수정할 수 있다.

```sql
CREATE TABLE strategies (
    id            bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    key           text NOT NULL UNIQUE,
    value         text NOT NULL,
    description   text,
    updated_at    timestamptz NOT NULL DEFAULT now()
);

-- 초기값 삽입
INSERT INTO strategies (key, value, description) VALUES
    ('rebalance_interval_months', '6',    '리밸런싱 주기 (개월)'),
    ('drift_threshold',           '0.05', '리밸런싱 트리거 drift 임계값 (비율)');
```

### 2-2. `portfolios`

ETF 목표 비중을 정의한다. 이상적인 목표 비중이며 lot-size rounding 전의 값이다.

```sql
CREATE TABLE portfolios (
    id            bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    ticker        text NOT NULL,
    name          text NOT NULL,
    target_weight numeric(5,4) NOT NULL        -- 목표 비중 (0.0000 ~ 1.0000)
                  CHECK (target_weight > 0 AND target_weight <= 1),
    is_active     boolean NOT NULL DEFAULT true,
    note          text,
    updated_at    timestamptz NOT NULL DEFAULT now()
);

-- target_weight 합계 검증용 뷰
CREATE VIEW portfolio_summary AS
SELECT
    COUNT(*)                                   AS etf_count,
    SUM(target_weight)                         AS total_weight,
    array_agg(ticker ORDER BY target_weight DESC) AS tickers
FROM portfolios
WHERE is_active = true;

-- 초기값 예시
INSERT INTO portfolios (ticker, name, target_weight) VALUES
    ('069500', 'KODEX 200',           0.3000),
    ('139260', 'KODEX K-신재생에너지', 0.2000),
    ('148070', 'KOSEF 국고채10년',     0.5000);
```

> ⚠️ `is_active = true` 인 행의 `target_weight` 합이 반드시 1.0000 이어야 한다.  
> 실행 시 코드에서 합계 검증 후 불일치 시 실행 중단.

### 2-3. `rebalancing_runs`

리밸런싱 1회 실행의 단위 레코드. `order_plans`와 `order_executions`의 부모 키.

```sql
CREATE TYPE run_mode   AS ENUM ('full', 'buy_retry');
CREATE TYPE run_status AS ENUM ('running', 'completed', 'failed');

CREATE TABLE rebalancing_runs (
    id                    bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    period                text NOT NULL,          -- 주기 시작 월 e.g. '2026-01', '2026-07' (반기) | '2026-04' (분기)
    mode                  run_mode NOT NULL,       -- 'full' | 'buy_retry'
    status                run_status NOT NULL DEFAULT 'running',
    dry_run               boolean NOT NULL DEFAULT false,

    -- full 모드 실행 시 기록
    total_assets_krw      numeric(18,2),           -- 실행 시점 총 자산 (원)

    -- 결과 요약
    orders_placed         integer DEFAULT 0,       -- 제출된 주문 수
    orders_filled         integer DEFAULT 0,       -- 완전 체결된 주문 수
    orders_partial        integer DEFAULT 0,       -- 부분 체결
    orders_failed         integer DEFAULT 0,       -- 실패/취소

    -- buy_retry 모드일 때 원 run 참조
    parent_run_id         bigint REFERENCES rebalancing_runs(id),

    started_at            timestamptz NOT NULL DEFAULT now(),
    finished_at           timestamptz,
    error_message         text
);

CREATE INDEX idx_runs_period  ON rebalancing_runs (period);
CREATE INDEX idx_runs_status  ON rebalancing_runs (status);
```

**`period` 산출 규칙:**

```python
from datetime import date

def current_period(today: date, interval_months: int) -> str:
    """
    해당 날짜가 속한 주기의 시작 월을 반환한다.
    period는 주기 시작 월 기준으로 식별되며, 주기 내 중복 실행을 방지하는 키로 사용된다.

    interval_months=6 (반기)
      2026-01-15 → '2026-01'  (1~6월 → 1월 시작)
      2026-08-01 → '2026-07'  (7~12월 → 7월 시작)

    interval_months=3 (분기)
      2026-05-01 → '2026-04'  (4~6월 → 4월 시작)

    interval_months=1 (월)
      2026-03-01 → '2026-03'
    """
    start_month = ((today.month - 1) // interval_months) * interval_months + 1
    return f"{today.year}-{start_month:02d}"
```

**실행 진입 로직 (main.py):**

```python
today = date.today()
day   = today.day   # 1, 2, 3, 4

# strategies 에서 파라미터 로드
config = supabase.table("strategies").select("key, value").execute()
cfg = {r["key"]: r["value"] for r in config.data}
interval_months = int(cfg["rebalance_interval_months"])
drift_threshold = Decimal(cfg["drift_threshold"])
period = current_period(today, interval_months)

# 마지막 full run으로부터 N개월 경과 여부 확인 (1일 진입 조건)
def is_interval_elapsed() -> bool:
    last_full = (
        supabase.table("rebalancing_runs")
        .select("finished_at")
        .eq("mode", "full")
        .eq("dry_run", False)
        .eq("status", "completed")
        .order("finished_at", desc=True)
        .limit(1)
        .execute()
    )
    if not last_full.data:
        return True  # 최초 실행
    return months_since(last_full.data[0]["finished_at"]) >= interval_months

# 이번 주기 run 조회 헬퍼
def get_run(mode: str, dry_run: bool) -> dict | None:
    result = (
        supabase.table("rebalancing_runs")
        .select("id")
        .eq("period", period)
        .eq("mode", mode)
        .eq("dry_run", dry_run)
        .eq("status", "completed")
        .execute()
    )
    return result.data[0] if result.data else None

def get_unfilled_buys(run_id: int) -> list:
    return (
        supabase.table("order_executions")
        .select("id")
        .eq("run_id", run_id)
        .eq("side", "buy")
        .in_("status", ["pending", "partial"])
        .execute()
    ).data

# --- 날짜별 진입 ---

if day == 1:
    if not is_interval_elapsed():
        return  # 주기 미경과
    if get_run(mode="full", dry_run=True):
        return  # 이미 dry run 완료
    run_dry_run()  # order_plans 생성 + Telegram 예고, DB 기록

elif day == 2:
    dry = get_run(mode="full", dry_run=True)
    if not dry:
        return  # 1일 dry run 없음
    if get_run(mode="full", dry_run=False):
        return  # 이미 full 완료
    run_full_rebalancing()

elif day in (3, 4):
    full = get_run(mode="full", dry_run=False)
    if not full:
        return  # 2일 full run 없음
    if not get_unfilled_buys(full["id"]):
        return  # 미체결 없음
    run_buy_retry(parent_run_id=full["id"])
```

### 2-4. `order_plans`

full run 시점에 산출된 종목별 주문 계획 (목표 수량·비중).  
목표 비중을 현재가 기준 정수 주 단위로 내림한 결과를 기록한다. 산출 후 불변.

```sql
CREATE TABLE order_plans (
    id                bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    run_id            bigint NOT NULL REFERENCES rebalancing_runs(id),
    ticker            text NOT NULL,
    name              text NOT NULL,

    -- 목표 비중 (portfolios 기준)
    model_weight      numeric(5,4) NOT NULL,

    -- 주문 계획 산출 결과 (lot-size rounding 후)
    price_at_calc     numeric(12,2) NOT NULL,       -- 산출 시점 현재가
    target_quantity   integer NOT NULL,             -- 목표 보유 수량 (정수)
    target_amount     numeric(16,2) NOT NULL,       -- target_quantity * price_at_calc
    realized_weight   numeric(5,4) NOT NULL,        -- target_amount / total_assets

    -- MP 대비 rounding 오차
    weight_error      numeric(5,4) NOT NULL,        -- realized_weight - model_weight

    calculated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_op_run_id ON order_plans (run_id);
```

### 2-5. `order_executions`

실제로 제출된 개별 주문과 체결 결과.  
`retry_of`로 재시도 체인을 추적한다.

```sql
CREATE TABLE order_executions (
    id              bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    run_id          bigint NOT NULL REFERENCES rebalancing_runs(id),
    order_id        text,                    -- 키움 주문번호
    ticker          text NOT NULL,
    name            text NOT NULL,
    side            text NOT NULL CHECK (side IN ('buy', 'sell')),
    order_type      text NOT NULL CHECK (order_type IN ('market', 'limit', 'best')),

    quantity        integer NOT NULL,        -- 주문 수량
    price           numeric(12,2),           -- 지정가 (시장가·최유리지정가는 null)
    filled_price    numeric(12,2),           -- 체결 평균가
    filled_quantity integer NOT NULL DEFAULT 0,

    status          text NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'filled', 'partial', 'rejected', 'cancelled')),
    reason          text,                    -- 주문 사유 (e.g. 'drift +0.08 > threshold 0.05')

    -- 재시도 추적
    retry_of        bigint REFERENCES order_executions(id),  -- 원주문 ID (재시도 시)
    attempt_no      integer NOT NULL DEFAULT 1,              -- 1차, 2차, ...

    dry_run         boolean NOT NULL DEFAULT false,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_oe_run_id     ON order_executions (run_id);
CREATE INDEX idx_oe_ticker     ON order_executions (ticker);
CREATE INDEX idx_oe_retry_of   ON order_executions (retry_of);
CREATE INDEX idx_oe_created_at ON order_executions (created_at DESC);
```

**재시도 체인 조회 예시:**

```sql
-- 특정 run의 069500 매수 시도 전체 이력
SELECT attempt_no, quantity, filled_quantity, filled_price, status, created_at
FROM order_executions
WHERE run_id = 3
  AND ticker = '069500'
  AND side = 'buy'
ORDER BY attempt_no;
```

---

## ERD 관계 요약

```
strategies          (설정, 단독)
portfolios          (설정, 단독)

rebalancing_runs
    ├── order_plans           (run_id FK)
    └── order_executions      (run_id FK)
            └── order_executions (retry_of FK, 자기 참조)
```

---

## RLS (Row Level Security)

GitHub Actions는 `service_role` 키를 사용하므로 RLS를 우회한다.

```sql
ALTER TABLE strategies          ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolios          ENABLE ROW LEVEL SECURITY;
ALTER TABLE rebalancing_runs    ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_plans         ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_executions    ENABLE ROW LEVEL SECURITY;

-- anon/authenticated 는 읽기 전용
CREATE POLICY "read_only" ON rebalancing_runs  FOR SELECT USING (true);
CREATE POLICY "read_only" ON order_plans        FOR SELECT USING (true);
CREATE POLICY "read_only" ON order_executions  FOR SELECT USING (true);
```

---

## Python에서의 주요 조회 패턴

```python
# 전략 파라미터 전체 로드
params = supabase.table("strategies").select("key, value").execute()
config = {row["key"]: row["value"] for row in params.data}
rebalance_interval_months = int(config["rebalance_interval_months"])   # 6
drift_threshold = Decimal(config["drift_threshold"])                   # 0.05

# 목표 비중 조회
targets = (
    supabase.table("portfolios")
    .select("ticker, name, target_weight")
    .eq("is_active", True)
    .execute()
)

# 이번 반기 completed full run 조회
completed = (
    supabase.table("rebalancing_runs")
    .select("id, finished_at")
    .eq("period", current_period(date.today(), rebalance_interval_months))
    .eq("mode", "full")
    .eq("status", "completed")
    .execute()
)

# 특정 run의 미체결 매수 주문 조회
unfilled_buys = (
    supabase.table("order_executions")
    .select("*")
    .eq("run_id", run_id)
    .eq("side", "buy")
    .in_("status", ["pending", "partial"])
    .execute()
)
```

---

## ⏸️ USER ACTION — Supabase 프로젝트 생성

Supabase MCP가 세팅된 환경이므로 **DDL 실행 및 검증은 에이전트가 MCP로 직접 처리**한다.  
사용자가 직접 해야 하는 작업은 아래 두 가지뿐이다:

1. [Supabase](https://supabase.com/) 에 가입하고 새 프로젝트를 생성한다.
2. Supabase Dashboard → **Settings → API** 에서 **`service_role` key** 를 메모한다.  
   (이 키는 MCP로 조회할 수 없으며, GCP VM의 `.env`에 `SUPABASE_KEY`로 사용된다.)

> 완료되면 에이전트에게 "Supabase 설정 완료" 라고 알려주세요.

---

## 에이전트 실행 절차 (MCP 사용)

사용자가 "Supabase 설정 완료"를 알리면 에이전트가 아래 순서로 MCP 도구를 사용해 작업한다:

1. **`mcp_supabase_apply_migration`** 으로 DDL 전체를 마이그레이션으로 적용한다.  
   (테이블 5개, ENUM 2개, 뷰 1개, 인덱스 전체)
2. **`mcp_supabase_execute_sql`** 로 초기 데이터(`strategies`, `portfolios`)를 INSERT한다.
3. **`mcp_supabase_execute_sql`** 로 `portfolio_summary` 뷰를 조회해 `total_weight = 1.0000` 을 검증한다.
4. **`mcp_supabase_get_project_url`** 로 `SUPABASE_URL`을 확인한다.
5. `portfolios` ETF 목록이 사용자 전략과 다를 경우, MCP로 직접 수정 SQL을 실행한다.

> ⚠️ `service_role key`는 MCP 범위 밖이므로 사용자가 Dashboard에서 직접 확인해야 한다.

---

## 완료 조건

- [ ] 5개 테이블 + 2개 ENUM 타입 생성 완료 (MCP `apply_migration` 으로 확인)
- [ ] `portfolio_summary` 뷰 생성 완료
- [ ] `strategies` 초기 파라미터 INSERT (`rebalance_interval_months`, `drift_threshold`)
- [ ] `portfolios` 초기 ETF 목록 INSERT, `total_weight = 1.0000` 검증 (MCP `execute_sql` 으로 확인)
- [ ] `SUPABASE_URL` 확인 (MCP `get_project_url` 으로 확인)
- [ ] `service_role key` 사용자가 Dashboard에서 확인 후 메모

---

## 검증 절차

MCP가 세팅된 환경이므로 에이전트가 직접 SQL로 검증한다:

```sql
-- 1. 테이블 존재 확인
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('strategies','portfolios','rebalancing_runs','order_plans','order_executions')
ORDER BY table_name;

-- 2. 목표 비중 합계 확인
SELECT * FROM portfolio_summary;

-- 3. strategies 초기값 확인
SELECT key, value FROM strategies ORDER BY key;
```

> `uv run python scripts/verify_step.py 2` 는 MCP 검증 후 보조 확인용으로만 실행한다.

---

## 📦 커밋하고 세션 마무리

DDL 파일을 저장소에 보관합니다:

```bash
git add docs/
git commit -m "feat: step 2 - supabase schema DDL"
```

커밋 후 이 세션은 여기서 닫습니다.
다음 세션에서 에이전트에게 **"다음 step 진행해줘"** 라고 말하면 이어서 시작합니다.

**다음:** `step-03-kiwoom-client.md` — Kiwoom REST API 클라이언트 구현 (API 키 필요)
