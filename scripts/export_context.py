#!/usr/bin/env python3
"""
scripts/export_context.py
외부 Gemini 노트북 & 저사양 모델 협업을 위한 5대 고정 컨텍스트 스냅샷 생성기 (Facade & CLI).
하위 세부 구현은 `scripts.context_exporter` 패키지에 모듈화되어 있습니다.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT_DIR = Path(__file__).resolve().parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

from plepa_engine.config import DEFAULT_ROSTER, ROOT_DIR as PLEPA_ROOT, configure_stdio

configure_stdio()

from scripts.context_exporter import (  # noqa: E402
    DEFAULT_BASE_TOTAL_BUDGET,
    build_code_bundle,
    build_readme,
    build_refactoring_plan,
    build_tier1,
    build_tier2,
    build_tier3,
    cleanup_stale_snapshots,
    collect_genit_status,
    collect_skills_catalog,
    enforce_budget,
    extract_adrs,
    extract_constants,
    extract_dataclass_fields,
    extract_signatures,
    git_info,
    parse_module,
    sha,
)
from scripts.context_exporter.ast_extract import collect_active_modules  # noqa: E402
from scripts.context_exporter.builders import summarize_pose_db  # noqa: E402
from scripts.context_exporter.runtime_and_telemetry import (  # noqa: E402
    BASE_SNAPSHOT_FILES,
    collect_active_ssot_docs,
)

__all__ = [
    "PLEPA_ROOT",
    "sha",
    "parse_module",
    "extract_constants",
    "extract_signatures",
    "extract_dataclass_fields",
    "build_tier1",
    "build_tier2",
    "build_tier3",
    "build_readme",
    "build_refactoring_plan",
    "build_code_bundle",
    "git_info",
    "collect_snapshot_data",
    "export_context_snapshot",
    "main",
]


def collect_snapshot_data() -> Dict[str, Any]:
    """코드베이스 AST, 스킬 카탈로그, Active ADR, 포즈 DB 통계를 수집합니다."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mods = collect_active_modules()
    g = git_info()
    return {
        "generated_at": now,
        "snapshot_id": sha(f"{now}:{g.get('commit', '')}:{len(mods)}"),
        "git": g,
        "modules": mods,
        "adrs": extract_adrs(max_items=28),
        "skills": collect_skills_catalog(),
        "ssot_docs": collect_active_ssot_docs(),
        "genit": collect_genit_status(),
        "pose_stats": summarize_pose_db(),
    }


def export_context_snapshot(
    out_dir: Optional[Path] = None,
    kiro_root: Optional[Path] = None,
    include_prompts: bool = False,
    full_code: bool = False,
    run_tests: bool = False,
) -> Dict[str, Any]:
    """5대 고정 스냅샷 파일(+선택적 40_CORE_CODE)을 덮어쓰고 구버전 파일을 정리합니다."""
    snap_dir = out_dir or (PLEPA_ROOT / "context_snapshot")
    snap_dir.mkdir(parents=True, exist_ok=True)
    target_kiro = kiro_root or Path("C:/Users/rbsgh/kiro")

    hashes_path = snap_dir / ".hashes.json"
    prev_meta: Dict[str, Any] = {}
    if hashes_path.is_file():
        try:
            prev_meta = json.loads(hashes_path.read_text(encoding="utf-8"))
        except Exception:
            prev_meta = {}

    snap = collect_snapshot_data()
    prev_id = prev_meta.get("snapshot_id")
    prev_hashes: Dict[str, str] = prev_meta.get("file_hashes", {})

    cur_hashes: Dict[str, str] = {}
    for m in snap["modules"]:
        p = PLEPA_ROOT / m.rel_path
        if p.is_file():
            cur_hashes[m.rel_path] = sha(p.read_text(encoding="utf-8", errors="replace"))
    delta = sorted(
        [k for k, v in cur_hashes.items() if prev_hashes.get(k) != v]
        + [k for k in prev_hashes if k not in cur_hashes]
    )

    generated_list = list(BASE_SNAPSHOT_FILES)
    if full_code:
        generated_list.append("40_CORE_CODE.md")

    raw_files: Dict[str, str] = {
        "00_README_FOR_AI.md": build_readme(snap, delta, prev_id, generated_list),
        "10_TIER1_CONSTITUTION.md": build_tier1(snap),
        "20_TIER2_CORE_LOGIC.md": build_tier2(snap, include_prompts=include_prompts),
        "30_TIER3_RUNTIME.md": build_tier3(snap, target_kiro, run_tests, delta),
        "50_REFACTORING_PLAN.md": build_refactoring_plan(snap),
    }
    if full_code:
        raw_files["40_CORE_CODE.md"] = build_code_bundle(snap)

    final_files = enforce_budget(raw_files, base_total_budget=DEFAULT_BASE_TOTAL_BUDGET)
    keep_set = set(final_files.keys())
    removed = cleanup_stale_snapshots(snap_dir, keep_files=keep_set)

    written_sizes: Dict[str, int] = {}
    for fname, content in final_files.items():
        (snap_dir / fname).write_text(content, encoding="utf-8")
        written_sizes[fname] = len(content.encode("utf-8"))

    hashes_payload = {
        "snapshot_id": snap["snapshot_id"],
        "generated_at": snap["generated_at"],
        "file_hashes": cur_hashes,
    }
    hashes_path.write_text(json.dumps(hashes_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "out_dir": str(snap_dir),
        "files": list(final_files.keys()),
        "sizes": written_sizes,
        "base_total_bytes": sum(v for k, v in written_sizes.items() if k != "40_CORE_CODE.md"),
        "removed_stale": removed,
        "delta_count": len(delta),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="PLEPA Gemini 노트북 스냅샷 생성기 v2")
    parser.add_argument("--out-dir", type=Path, default=None, help="출력 폴더 (기본: context_snapshot/)")
    parser.add_argument("--kiro-dir", type=Path, default=Path("C:/Users/rbsgh/kiro"), help="Kiro 레포 경로")
    parser.add_argument("--include-prompts", action="store_true", help="H-씬 주요 프롬프트 상수 추가 포함")
    parser.add_argument("--full-code", action="store_true", help="40_CORE_CODE.md 전체 소스 번들 생성")
    parser.add_argument("--run-tests", action="store_true", help="(호환 옵션) 런타임 테스트 메타 기록")
    args = parser.parse_args(argv)

    res = export_context_snapshot(
        out_dir=args.out_dir,
        kiro_root=args.kiro_dir,
        include_prompts=args.include_prompts,
        full_code=args.full_code,
        run_tests=args.run_tests,
    )
    print(
        f"[export_context v2] {len(res['files'])}개 파일 갱신 완료 "
        f"(기본 5종 합계 {res['base_total_bytes'] / 1024:.1f} KB, "
        f"정리된 구 파일 {len(res['removed_stale'])}개)"
    )
    for fn, sz in res["sizes"].items():
        print(f"  - {fn}: {sz / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
