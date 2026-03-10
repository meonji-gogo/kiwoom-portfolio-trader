#!/usr/bin/env python3
"""
각 Step의 완료 조건을 자동 검증하는 스크립트.
에이전트 또는 사용자가 `uv run python scripts/verify_step.py <step_number>` 로 실행한다.
"""

import importlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "trader"
TESTS = ROOT / "tests"


def run_cmd(cmd: list[str], cwd: Path = ROOT) -> tuple[int, str]:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return result.returncode, result.stdout + result.stderr


def check(label: str, ok: bool) -> bool:
    symbol = "✅" if ok else "❌"
    print(f"  {symbol} {label}")
    return ok


def verify_step_1() -> bool:
    """Step 1: 프로젝트 초기화 검증."""
    print("\n📋 Step 1: 프로젝트 초기화")
    results = []

    # pyproject.toml 존재
    results.append(check("pyproject.toml 존재", (ROOT / "pyproject.toml").exists()))

    # uv.lock 존재
    results.append(check("uv.lock 존재", (ROOT / "uv.lock").exists()))

    # .python-version 존재
    results.append(check(".python-version 존재", (ROOT / ".python-version").exists()))

    # .env.example 존재
    results.append(check(".env.example 존재", (ROOT / ".env.example").exists()))

    # .gitignore에 .env 포함
    gitignore = ROOT / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        results.append(check(".gitignore에 .env 포함", ".env" in content))
    else:
        results.append(check(".gitignore 파일 존재", False))

    # src/trader 패키지 구조
    results.append(check("src/trader/__init__.py 존재", (SRC / "__init__.py").exists()))
    results.append(check("src/trader/main.py 존재", (SRC / "main.py").exists()))

    # uv sync 성공
    code, output = run_cmd(["uv", "sync"])
    results.append(check("uv sync 성공", code == 0))

    # ruff check 통과
    if (SRC).exists():
        code, output = run_cmd(["uv", "run", "ruff", "check", "src/"])
        results.append(check("ruff check src/ 통과", code == 0))

    # import 가능
    code, output = run_cmd(["uv", "run", "python", "-c", "import trader; print(trader.__file__)"])
    results.append(check("trader 패키지 import 가능", code == 0))

    return all(results)


def verify_step_2() -> bool:
    """Step 2: Supabase 스키마 — 수동 확인 항목 안내."""
    print("\n📋 Step 2: Supabase 스키마")
    print("  ⚠️  이 Step은 Supabase Dashboard에서 수동으로 확인해야 합니다.")
    print("  확인 항목:")
    print("    - [ ] 5개 테이블 생성 (strategies, portfolios, rebalancing_runs, order_plans, order_executions)")
    print("    - [ ] 2개 ENUM 타입 생성 (run_mode, run_status)")
    print("    - [ ] portfolio_summary 뷰 생성")
    print("    - [ ] strategies 초기 데이터 INSERT")
    print("    - [ ] portfolios 초기 ETF 목록 INSERT (target_weight 합계 = 1.0000)")
    print("    - [ ] SUPABASE_URL, SUPABASE_KEY 메모 완료")
    return True


def verify_step_3() -> bool:
    """Step 3: Kiwoom 클라이언트 검증."""
    print("\n📋 Step 3: Kiwoom 클라이언트")
    results = []

    results.append(check("kiwoom.py 존재", (SRC / "kiwoom.py").exists()))

    # kiwoompy 설치 확인
    code, _ = run_cmd(["uv", "run", "python", "-c", "import kiwoompy"])
    results.append(check("kiwoompy import 가능", code == 0))

    # 클래스 존재 확인
    code, _ = run_cmd([
        "uv", "run", "python", "-c",
        "from trader.kiwoom import KiwoomGateway, Holding, PortfolioSnapshot, OrderResult"
    ])
    results.append(check("KiwoomGateway, Holding, PortfolioSnapshot, OrderResult 클래스 존재", code == 0))

    # mock 테스트 실행
    if (TESTS / "test_kiwoom.py").exists():
        code, output = run_cmd(["uv", "run", "pytest", "tests/test_kiwoom.py", "-v", "--tb=short"])
        results.append(check("test_kiwoom.py 테스트 통과", code == 0))
        if code != 0:
            print(f"    출력: {output[:500]}")

    return all(results)


def verify_step_4() -> bool:
    """Step 4: 리밸런싱 로직 검증."""
    print("\n📋 Step 4: 리밸런싱 로직")
    results = []

    results.append(check("portfolio.py 존재", (SRC / "portfolio.py").exists()))

    # 핵심 함수 존재 확인
    code, _ = run_cmd([
        "uv", "run", "python", "-c",
        "from trader.portfolio import calc_weights, calc_drifts, calc_rebalance_orders, TargetETF, RebalanceOrder"
    ])
    results.append(check("핵심 함수/클래스 import 가능", code == 0))

    # 테스트 실행
    if (TESTS / "test_portfolio.py").exists():
        code, output = run_cmd(["uv", "run", "pytest", "tests/test_portfolio.py", "-v", "--tb=short"])
        results.append(check("test_portfolio.py 테스트 통과", code == 0))
        if code != 0:
            print(f"    출력: {output[:500]}")

    return all(results)


def verify_step_5() -> bool:
    """Step 5: GitHub Actions 검증."""
    print("\n📋 Step 5: GitHub Actions")
    results = []

    rebalance_yml = ROOT / ".github" / "workflows" / "rebalance.yml"
    results.append(check("rebalance.yml 존재", rebalance_yml.exists()))

    if rebalance_yml.exists():
        content = rebalance_yml.read_text()
        results.append(check("schedule cron 설정 포함", "schedule:" in content))
        results.append(check("workflow_dispatch 설정 포함", "workflow_dispatch:" in content))
        results.append(check("uv sync --frozen 포함", "uv sync --frozen" in content))
        results.append(check("Secrets 참조 포함 (KIWOOM_APP_KEY)", "KIWOOM_APP_KEY" in content))

    print("  ⚠️  GitHub Secrets 등록은 GitHub UI에서 수동 확인 필요")

    return all(results)


def verify_step_6() -> bool:
    """Step 6: Telegram 알림 검증."""
    print("\n📋 Step 6: Telegram 알림")
    results = []

    results.append(check("notifier.py 존재", (SRC / "notifier.py").exists()))

    code, _ = run_cmd([
        "uv", "run", "python", "-c",
        "from trader.notifier import send_message"
    ])
    results.append(check("send_message 함수 import 가능", code == 0))

    print("  ⚠️  실제 알림 수신은 Bot Token/Chat ID 설정 후 수동 확인 필요")

    return all(results)


def verify_step_7() -> bool:
    """Step 7: CI 검증."""
    print("\n📋 Step 7: CI")
    results = []

    ci_yml = ROOT / ".github" / "workflows" / "ci.yml"
    results.append(check("ci.yml 존재", ci_yml.exists()))

    results.append(check("tests/conftest.py 존재", (TESTS / "conftest.py").exists()))
    results.append(check("tests/test_portfolio.py 존재", (TESTS / "test_portfolio.py").exists()))
    results.append(check("tests/test_kiwoom.py 존재", (TESTS / "test_kiwoom.py").exists()))

    # ruff check
    code, output = run_cmd(["uv", "run", "ruff", "check", "src/", "tests/"])
    results.append(check("ruff check 통과", code == 0))

    # ruff format check
    code, output = run_cmd(["uv", "run", "ruff", "format", "--check", "src/", "tests/"])
    results.append(check("ruff format --check 통과", code == 0))

    # pytest
    code, output = run_cmd(["uv", "run", "pytest", "--tb=short", "-q"])
    results.append(check("pytest 전체 통과", code == 0))
    if code != 0:
        print(f"    출력: {output[:500]}")

    return all(results)


def verify_step_8() -> bool:
    """Step 8: main.py 통합 검증."""
    print("\n📋 Step 8: main.py 통합")
    results = []

    results.append(check("main.py 존재", (SRC / "main.py").exists()))
    results.append(check("supabase_client.py 존재", (SRC / "supabase_client.py").exists()))
    results.append(check("__init__.py 존재", (SRC / "__init__.py").exists()))

    # 핵심 import 가능
    code, _ = run_cmd([
        "uv", "run", "python", "-c",
        "from trader.main import main, current_period, is_market_open"
    ])
    results.append(check("main.py 핵심 함수 import 가능", code == 0))

    code, _ = run_cmd([
        "uv", "run", "python", "-c",
        "from trader.supabase_client import SupabaseRepo"
    ])
    results.append(check("SupabaseRepo import 가능", code == 0))

    return all(results)


VERIFIERS = {
    1: verify_step_1,
    2: verify_step_2,
    3: verify_step_3,
    4: verify_step_4,
    5: verify_step_5,
    6: verify_step_6,
    7: verify_step_7,
    8: verify_step_8,
}


def main():
    if len(sys.argv) < 2:
        print("사용법: uv run python scripts/verify_step.py <step_number|all>")
        print("  예: uv run python scripts/verify_step.py 1")
        print("  예: uv run python scripts/verify_step.py all")
        sys.exit(1)

    arg = sys.argv[1]

    if arg == "all":
        steps = sorted(VERIFIERS.keys())
    else:
        try:
            steps = [int(arg)]
        except ValueError:
            print(f"잘못된 인수: {arg}")
            sys.exit(1)

    all_passed = True
    for step in steps:
        if step not in VERIFIERS:
            print(f"Step {step}은 지원되지 않습니다. (1~8)")
            continue
        passed = VERIFIERS[step]()
        if passed:
            print(f"\n  ✅ Step {step} 검증 통과!")
        else:
            print(f"\n  ❌ Step {step} 검증 실패 — 위 항목을 확인하세요.")
            all_passed = False

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
