"""
scripts.context_exporter.report_builders
런타임(30_TIER3_RUNTIME), 리팩토링 현황(50_REFACTORING_PLAN), 코드 번들(40) 및 용량 예산 가드.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from plepa_engine.config import ROOT_DIR as PLEPA_ROOT

from .ast_extract import ast_telemetry, count_quarantined_scripts
from .builders import get_live_modules
from .runtime_and_telemetry import (
    COLLECTED_FILE_BUDGETS,
    DEFAULT_BASE_TOTAL_BUDGET,
    build_asset_matrix,
    build_drift,
    collect_genit_status,
    collect_novelchat_status,
    parse_refactoring_progress,
)


def _format_chatbot_doc_table(heading: str, rows: List[Dict[str, Any]]) -> List[str]:
    """`docs/{genit|novelchat}/` 마크다운 상태 테이블을 생성합니다."""
    lines: List[str] = [
        heading,
        "| 파일명 | 줄 수 | 상태 | 버전 |",
        "| :--- | :---: | :---: | :---: |",
    ]
    for row in rows:
        lines.append(f"| `{row['name']}` | {row['lines']}L | `{row['status']}` | `{row['version']}` |")
    return lines


def build_tier3(snap: Dict[str, Any], kiro_root: Path, run_tests: bool, delta: List[str]) -> str:
    """`30_TIER3_RUNTIME.md`: 12개 로스터 자산 매트릭스, Gen-IT/노벨챗 현황, 최근 일지/감사 요약, 드리프트."""
    matrix_md, _ = build_asset_matrix()
    genit_rows = collect_genit_status()
    novelchat_rows = collect_novelchat_status()
    journal_p = PLEPA_ROOT / "docs" / "개발일지.md"
    recent_journal: List[str] = []
    if journal_p.is_file():
        for line in journal_p.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("### ") and "차" in line:
                recent_journal.append(f"- {line[4:].strip()}")
                if len(recent_journal) >= 6:
                    break

    audit_p = PLEPA_ROOT / "output" / "overnight_full_audit" / "REPORT.md"
    audit_head = ""
    if audit_p.is_file():
        audit_head = "\n".join(audit_p.read_text(encoding="utf-8", errors="replace").splitlines()[:25])

    out: List[str] = [
        "# 📊 TIER 3: 런타임 자산 매트릭스 · Gen-IT 현황 · 최근 작업 로그",
        "",
        "## 1. 12개 로스터 메타 & 에셋 매트릭스",
        matrix_md,
        "",
        *_format_chatbot_doc_table("## 2. Gen-IT 상용 패키지 현황 (`docs/genit/`)", genit_rows),
        "",
        *_format_chatbot_doc_table("## 2-1. 노벨챗(NovelChat) 패키지 현황 (`docs/novelchat/`)", novelchat_rows),
    ]

    out.extend(["", "## 3. 최근 개발일지 요약 (`docs/개발일지.md`)"])
    out.extend(recent_journal or ["- 기록 없음"])
    if audit_head:
        out.extend(["", "## 4. 최근 야간 전수 감사 상단 요약 (`overnight_full_audit/REPORT.md`)", "```markdown", audit_head, "```"])
    out.extend(["", "## 5. 형제 저장소(`kiro`) 드리프트 & 런타임 설정", build_drift(kiro_root)])
    return "\n".join(out) + "\n"


def build_refactoring_plan(snap: Dict[str, Any]) -> str:
    """`50_REFACTORING_PLAN.md`: Wave 0~5 진행 트래커, AST 크기/래칫 실시간 텔레메트리 및 협업 지시서 템플릿."""
    mods = get_live_modules(snap)
    tel = ast_telemetry(mods)
    waves = parse_refactoring_progress()

    out: List[str] = [
        "# 🧭 Wave 0~5 리팩토링 현황 & Live AST 텔레메트리 (`50_REFACTORING_PLAN.md`)",
        "",
        "## 1. Wave 0~5 마스터 진척도 (`docs/archive/plepa_refactoring_analysis.md` 기반)",
        "| Wave 단계 | 상태 | 핵심 내역 요약 |",
        "| :--- | :---: | :--- |",
    ]
    for w in waves:
        status = "✅ 완료" if w["todo"] == 0 and w["done"] > 0 else ("⏳ 진행중" if w["done"] > 0 else "🕒 대기")
        detail = (w.get("detail") or f"완료 {w['done']} / 잔여 {w['todo']}")[:140]
        out.append(f"| **{w['wave']}** | {status} | {detail} |")

    q_counts = count_quarantined_scripts()
    q_total = sum(q_counts.values())
    over_mod_cnt = len(tel["oversized_modules"])
    over_fn_cnt = len(tel["oversized_functions"])

    out.extend([
        "",
        f"## 2. Live AST 래칫 텔레메트리 (활성 `{tel['total_modules']}`모듈 / `{tel['total_lines']:,}`줄)",
        f"- **격리/아카이브 스크립트 (`scripts/{{archive,benchmarks,ml}}`)**: 총 `{q_total}`개 (`archive` {q_counts.get('archive', 0)} · `benchmarks` {q_counts.get('benchmarks', 0)} · `ml` {q_counts.get('ml', 0)} — 활성 AST 부채 제외)",
    ])
    if over_mod_cnt == 0 and over_fn_cnt == 0:
        out.append("- ✅ **활성 코드베이스 `>350L` 0건 · `>120L` 0건 · Allowlist 0건 (Wave 0~5 완결)**")
    else:
        out.extend([
            f"- **350줄 초과 비대 모듈 (`{over_mod_cnt}`개)** — 분해 대상 목록:",
            "| 모듈 경로 | 현재 줄 수 | 초과 함수 (`>120L`) |",
            "| :--- | :---: | :--- |",
        ])
        for m in tel["oversized_modules"]:
            fns = ", ".join(m.oversized_functions[:4]) or "-"
            out.append(f"| `{m.rel_path}` | **{m.line_count}L** | {fns} |")

        out.extend([
            "",
            f"- **120줄 초과 비대 함수 (총 `{over_fn_cnt}`개)** 중 상위 15개:",
        ])
        for item in tel["oversized_functions"][:15]:
            out.append(f"  - `{item['module']}` :: `{item['func']}`")

    out.extend([
        "",
        "## 3. 외부 Gemini 노트북 ➔ 로컬 Antigravity 표준 지시서 템플릿",
        "```text",
        "[PLEPA 작업 지시서]",
        "1. 대상 작업: (예: 신규 포즈 추가·라벨 동기화 / GENERATION_OPTION_SPECS CLI·GUI 옵션 확장)",
        "2. 활성화할 스킬: .agents/skills/<skill-name>/SKILL.md 준수",
        "3. 제약 조건: 활성 모듈 <=350줄 / 함수 <=120줄, projects/*/assets/ 무접촉, legacy·archive 열람 금지",
        "4. 완료 검증 게이트: .\\.venv\\Scripts\\python.exe -m pytest -q && .\\.venv\\Scripts\\python.exe -m plepa_engine.precheck -r campus && .\\.venv\\Scripts\\python.exe scripts/validate_genit_work.py --force && .\\.venv\\Scripts\\python.exe scripts/export_context.py",
        "```",
    ])
    return "\n".join(out) + "\n"


def build_code_bundle(snap: Dict[str, Any]) -> str:
    """`--full-code` 옵션 지정 시에만 생성되는 코어 Python 소스 번들."""
    core_paths = [
        "plepa_engine/config.py",
        "plepa_engine/models.py",
        "plepa_engine/precheck.py",
        "plepa_engine/services/generation_service.py",
    ]
    out = ["# 💻 CORE CODE SNAPSHOT (`--full-code`)\n"]
    for rel in core_paths:
        p = PLEPA_ROOT / rel
        if p.is_file():
            out.append(f"## `{rel}`\n```python\n{p.read_text(encoding='utf-8', errors='replace')}\n```\n")
    return "\n".join(out)


def enforce_budget(files_map: Dict[str, str], base_total_budget: int = DEFAULT_BASE_TOTAL_BUDGET) -> Dict[str, str]:
    """개별 파일 바이트 상한 및 기본 5개 파일 합계 상한(<=160KB)을 초과 시 안전 절단합니다."""
    capped: Dict[str, str] = {}
    for fname, content in files_map.items():
        limit = COLLECTED_FILE_BUDGETS.get(fname, 50 * 1024)
        raw = content.encode("utf-8")
        if len(raw) > limit:
            notice = "\n\n<!-- [TRUNCATED BY CONTEXT BUDGET] -->\n".encode("utf-8")
            trimmed = raw[: max(256, limit - len(notice))].decode("utf-8", errors="ignore")
            capped[fname] = trimmed + notice.decode("utf-8")
        else:
            capped[fname] = content

    base_keys = [k for k in capped if k != "40_CORE_CODE.md"]
    total_bytes = sum(len(capped[k].encode("utf-8")) for k in base_keys)
    if total_bytes > base_total_budget:
        for k in sorted(base_keys, key=lambda name: len(capped[name].encode("utf-8")), reverse=True):
            if total_bytes <= base_total_budget:
                break
            over = total_bytes - base_total_budget
            raw_k = capped[k].encode("utf-8")
            if len(raw_k) > over + 1024:
                notice = "\n<!-- [TRUNCATED: TOTAL 160KB CAP] -->\n"
                new_text = raw_k[: len(raw_k) - over - len(notice.encode("utf-8"))].decode("utf-8", errors="ignore") + notice
                total_bytes -= len(raw_k) - len(new_text.encode("utf-8"))
                capped[k] = new_text
    return capped
