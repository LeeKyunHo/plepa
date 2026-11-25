"""
scripts.context_exporter.builders
핵심 3종 스냅샷(00_README_FOR_AI, 10_TIER1_CONSTITUTION, 20_TIER2_CORE_LOGIC) 빌더.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from plepa_engine.config import ROOT_DIR as PLEPA_ROOT

from .ast_extract import (
    ModuleSummary,
    collect_active_modules,
    extract_dataclass_fields,
    extract_signatures,
    format_constants_snippet,
)
from .runtime_and_telemetry import (
    collect_active_ssot_docs,
    collect_skills_catalog,
    extract_adrs,
)


def get_live_modules(snap: Dict[str, Any]) -> List[ModuleSummary]:
    """스냅샷 딕셔너리에서 모듈 요약 리스트를 가져오거나 실시간 AST 스캔으로 보완합니다."""
    raw = snap.get("modules")
    if isinstance(raw, list) and raw and isinstance(raw[0], ModuleSummary):
        return raw
    return collect_active_modules()


def summarize_pose_db() -> Dict[str, Any]:
    """`sdxl_pose_database.json` 및 `pose_sets.json`의 V3 통계 요약을 생성합니다."""
    db_path = PLEPA_ROOT / "data" / "sdxl_pose_database.json"
    sets_path = PLEPA_ROOT / "data" / "pose_sets.json"
    sections: List[str] = []
    total_keys, dep_keys = 0, 0
    if db_path.is_file():
        db = json.loads(db_path.read_text(encoding="utf-8"))
        for sec, val in db.items():
            if isinstance(val, dict) and not sec.startswith("_"):
                keys = [k for k in val if not k.startswith("_")]
                deps = [k for k in keys if isinstance(val[k], dict) and val[k].get("status") == "deprecated"]
                total_keys += len(keys)
                dep_keys += len(deps)
                sections.append(f"`{sec}`({len(keys)}키/{len(deps)} dep)")
    pset_ids: List[str] = []
    if sets_path.is_file():
        for item in json.loads(sets_path.read_text(encoding="utf-8")):
            if isinstance(item, dict) and "id" in item:
                pset_ids.append(f"{item['id']}({len(item.get('codes', []))})")
    return {
        "total_keys": total_keys,
        "active_keys": total_keys - dep_keys,
        "deprecated_keys": dep_keys,
        "sections": sections,
        "pose_sets": pset_ids,
    }


def _collect_trinity_and_routes() -> str:
    lines: List[str] = ["### 2.1 Trinity Sync (`GENERATION_OPTION_SPECS` ↔ `GenerationParams` ↔ CLI)"]
    try:
        import batch_generator
        from plepa_engine.services.generation_service import GENERATION_OPTION_SPECS, GenerationParams

        parser_flags = {
            opt for act in batch_generator.create_parser()._actions for opt in getattr(act, "option_strings", [])
        }
        param_fields = set(GenerationParams.__dataclass_fields__.keys())
        lines.append("| `field` | `cli_flag` | `GenerationParams` | CLI Parser | `default` |")
        lines.append("| :--- | :--- | :---: | :---: | :--- |")
        for spec in GENERATION_OPTION_SPECS:
            f_name = spec["field"]
            c_flag = spec["cli_flag"]
            lines.append(
                f"| `{f_name}` | `{c_flag}` | {'OK' if f_name in param_fields else 'MISS'} | "
                f"{'OK' if c_flag in parser_flags else 'MISS'} | `{spec.get('default')}` |"
            )
    except Exception as e:
        lines.append(f"- Trinity 동적 수집 예외: {e}")

    app_py = PLEPA_ROOT / "plepa_gui" / "app.py"
    api_py = PLEPA_ROOT / "plepa_gui" / "api_routes.py"
    lines.append("\n### 2.2 NiceGUI 페이지 & FastAPI REST 엔드포인트")
    if app_py.is_file():
        app_routes = [
            l.strip()
            for l in app_py.read_text(encoding="utf-8").splitlines()
            if l.strip().startswith(("@ui.page", "@app."))
        ]
        lines.append("- **App Routes**: " + ", ".join(f"`{r}`" for r in app_routes[:20]))
    if api_py.is_file():
        api_eps = [
            l.strip() for l in api_py.read_text(encoding="utf-8").splitlines() if l.strip().startswith("@api_router.")
        ]
        lines.append("- **API (`/api/assets`)**: " + ", ".join(f"`{r}`" for r in api_eps[:16]))
    return "\n".join(lines)


def build_readme(snap: Dict[str, Any], delta: List[str], prev_id: Optional[str], files: List[str]) -> str:
    """`00_README_FOR_AI.md`: 노트북 온보딩, V3 Deprecation Ledger, 스킬 카탈로그, Active SSOT 문서 맵."""
    g = snap.get("git", {})
    skills = snap.get("skills") or collect_skills_catalog()
    ssot_docs = snap.get("ssot_docs") or collect_active_ssot_docs()
    out: List[str] = [
        "# 🧭 PLEPA Context Snapshot README (Gemini Notebook SSOT)",
        "",
        f"- **Generated**: `{snap.get('generated_at', '')}` | **Git**: `{g.get('branch', '?')}@{g.get('commit', '?')}` | **Snapshot ID**: `{snap.get('snapshot_id', '?')}` (Prev: `{prev_id or 'none'}`)",
        "- **Generated Files**: " + ", ".join(f"`{f}`" for f in files),
        "- **Changed Since Prev**: " + (", ".join(f"`{d}`" for d in delta[:20]) if delta else "변경 없음 또는 최초 스냅샷"),
        "",
        "## 0. 📖 외부 AI 읽기 규칙 (Reading Guide)",
        "- **단일 진실 공급원(SSOT)**: 이 `context_snapshot/` 5개 고정 파일(`00~30` + `50_REFACTORING_PLAN.md`)만 읽고, `docs/archive/`, `plepa_engine/legacy/`, `data/legacy/`는 절대 참조하지 마십시오.",
        "- **로컬 변경 요청 작성 시**: `50_REFACTORING_PLAN.md` 하단의 표준 지시서 템플릿(`<=350L` / `<=120L` 제약)을 사용하십시오.",
        "",
        "## 1. ⛔ 폐지 목록 (Deprecation Ledger) — V3 기준 (절대 참조·제안 금지 레거시)",
        "| 폐기/격리 항목 | 현행 V3 단일 진실 공급원(SSOT) | 비고 |",
        "| :--- | :--- | :--- |",
        "| `FLUX` / `flux_pose_database.json` | SDXL 단일 (`data/sdxl_pose_database.json`) | `plepa_engine/legacy/`, `data/legacy/` 열람 금지 |",
        "| `docs/POSE_MAPPING_V2.md`, `POSE_CATALOG.md` | 루트 **`POSE_MAPPING.md`** (단일 매핑 SSOT) | `docs/archive/` 이관 완료 |",
        "| `scripts/sync_to_kiro.py` | **기본 실행 차단(`exit 2`)** | 최신 Kiro 보호 (`--force-unsafe` 전용) |",
        "| 중복 봉사 `096~102,117,120,125~127` / `169~172,187,191,195~197` | 공통 봉사 **`064~079`** (`romance`) 통합 | DB `status=deprecated` 호환 보존 |",
        "| 코어 DB `200~202`, `#121`, `#128/#198` | `133~135` (단 로스터 `events.json`은 `200~202`), `#079` | `#128/#198` 공식 폐기(ADR-107) |",
        "| `bald` / `faceless` / `male hair over eyes` | **`_MOB_SHADOW_EYES_POS`** (상안부 그림자 음영) | 마네킹·앞머리 이염 방지 (ADR-105) |",
        "| `ADR-01~79` / `1차~54차` 일지 원문 | **`docs/AI_HANDOVER_GUIDE.md`** & **`docs/개발일지.md`** | 과거 이력 `docs/archive/` 분리 |",
        "",
        "## 2. 🤖 Antigravity 미니 에이전트 & Hook 가드 (`.agents/`)",
        "- **PreToolUse 물리 가드**: `.agents/hooks.json` ➔ `hooks/plepa_guard.py` (`projects/*/assets/`, `*_origin/`, `legacy/`, `sync_to_kiro.py`, 민감 커밋 자동 차단)",
        "| 스킬 이름 | 경로 | 적용 도메인 & 트리거 |",
        "| :--- | :--- | :--- |",
    ]
    for sk in skills:
        out.append(f"| `{sk['name']}` | `{sk['path']}` | {sk['description']} |")

    out.extend([
        "",
        "## 3. 📚 Active SSOT 문서 맵 (`docs/archive/` 제외)",
        "| 경로 | 줄 수 | 역할 |",
        "| :--- | :---: | :--- |",
    ])
    for d in ssot_docs:
        out.append(f"| `{d['path']}` | {d['lines']}L | {d['role']} |")
    return "\n".join(out) + "\n"


def build_tier1(snap: Dict[str, Any]) -> str:
    """`10_TIER1_CONSTITUTION.md`: 헌법 규칙, Active ADR, V3 포즈 대역, 전체 모듈 맵(>350L 뱃지 포함)."""
    mods = get_live_modules(snap)
    adrs = snap.get("adrs") or extract_adrs(max_items=28)
    gemini_p = PLEPA_ROOT / "GEMINI.md"
    gemini_headings = []
    if gemini_p.is_file():
        gemini_headings = [l.strip() for l in gemini_p.read_text(encoding="utf-8").splitlines() if l.startswith(("# ", "## "))]

    out: List[str] = [
        "# 📜 TIER 1: 아키텍처 헌법 · V3 포즈 규약 · 전체 모듈 맵",
        f"> **Snapshot ID**: `{snap.get('snapshot_id', 'LIVE')}` | **Generated**: `{snap.get('generated_at', '')}`",
        "",
        "## 1. `GEMINI.md` 최상위 규칙 목차",
    ]
    out.extend(f"- {h}" for h in gemini_headings)
    out.extend(["", "## 2. Active ADR 결정 요약 (`docs/AI_HANDOVER_GUIDE.md` 기반)"])
    for title, body in adrs:
        short_b = body[:1200] + ("..." if len(body) > 1200 else "")
        out.append(f"### {title}\n{short_b}\n")

    out.extend([
        "## 3. V3 포즈 번호 대역 체계 (`data/sdxl_pose_database.json` & `events.json`)",
        "- `000~019` (`emotions`, 20): 기본 감정 표현 (`832×1216` 세로)",
        "- `020~050` (`poses`, 31): 일상·스킨십·탈의·범용 이벤트 (`049` 전라, `050` 야경)",
        "- `051~055` (로스터 `events.json`): 세계관 고유 일상 (`campus`, `spy` 등)",
        "- `060~079` (`romance`, 20): 로맨스(`060~063`) + 공통 봉사 통합 대역(`064~079`)",
        "- `080~127` (`h_scenes`, 47키 = 활성 35 + deprecated 12), `130~132` (`special_h`, 3)",
        "- `150~197` (`scenes_otokonoko`, 48키 = 활성 39 + deprecated 9), `133~135`/`200~202` (`special_otokonoko`)",
        "",
        "## 4. 전체 코드베이스 모듈 맵 (`>350L` 리팩토링 대상 표시)",
        "| 모듈 경로 | 줄 수 | 상태 | 핵심 클래스/상수 요약 |",
        "| :--- | :---: | :---: | :--- |",
    ])
    for m in mods:
        badge = "**[>350L]**" if m.over_module_limit else "OK"
        syms = ", ".join(m.classes[:4] + m.constants[:3]) or "-"
        out.append(f"| `{m.rel_path}` | {m.line_count}L | {badge} | {syms} |")
    return "\n".join(out) + "\n"


def build_tier2(snap: Dict[str, Any], include_prompts: bool = False) -> str:
    """`20_TIER2_CORE_LOGIC.md`: 7대 Mutator, Trinity Sync 매트릭스, FastAPI/GUI 라우트, P2.5 검열 & QC, 포즈 요약."""
    pp_path = PLEPA_ROOT / "plepa_engine" / "prompt_pipeline.py"
    gs_path = PLEPA_ROOT / "plepa_engine" / "services" / "generation_service.py"
    ce_path = PLEPA_ROOT / "plepa_engine" / "censor.py"
    qa_path = PLEPA_ROOT / "plepa_engine" / "qa_validator.py"
    p_stats = snap.get("pose_stats") or summarize_pose_db()

    out: List[str] = [
        "# ⚙️ TIER 2: 코어 파이프라인 · 삼위일체 동기화 · 검열/QC 로직",
        f"> **Snapshot ID**: `{snap.get('snapshot_id', 'LIVE')}` | **Generated**: `{snap.get('generated_at', '')}`",
        "",
        "## 1. SDXL 7단계 Mutator 체인 (`plepa_engine/prompt_pipeline.py`)",
        "- 실행 순서: `PoseTagPreparationMutator` ➔ `PositiveAssemblyMutator` ➔ `NegativeBaseMutator` ➔ `DefectDefenseMutator` ➔ `TwoPersonMobMutator` ➔ `CompositionAntiDriftMutator` ➔ `SanitizerMutator`",
    ]
    if pp_path.is_file():
        const_names = ["_MOB_TIER_SPECS", "_PARTNER_POS_SPECS", "_MOB_SHADOW_EYES_POS"]
        if include_prompts:
            const_names.extend(["_H_SCENE_WET_SKIN_TAGS", "_H_SCENE_MOOD_LIGHTING_TAGS"])
        consts = format_constants_snippet(pp_path, const_names)
        if consts:
            out.append("```python\n" + consts + "\n```")
        out.append("- `PromptContext` fields: " + ", ".join(f"`{f[0]}: {f[1]}`" for f in extract_dataclass_fields(pp_path, "PromptContext")[:18]))

    out.extend(["", "## 2. " + _collect_trinity_and_routes().lstrip("# ")])
    if gs_path.is_file():
        fields = extract_dataclass_fields(gs_path, "GenerationParams")
        out.append(f"- `GenerationParams` fields ({len(fields)}): " + ", ".join(f"`{f[0]}`" for f in fields))

    out.extend(["", "## 3. `censor.py` (Phase P2.5 동결) & Auto-QC 파라미터 (`qa_validator.py`)"])
    if ce_path.is_file():
        ce_const = format_constants_snippet(ce_path, ["NON_EXPOSURE_H_POSES", "POSE_SAFE_ANCHORS"])
        if ce_const:
            out.append("```python\n" + ce_const + "\n```")
        out.append("- Censor 공개 API: " + ", ".join(f"`{s}`" for s in extract_signatures(ce_path, ["censor_image", "censor_file", "is_pose_censor_required", "unload_censor_models"])))
    if qa_path.is_file():
        out.append("- Auto-QC API: " + ", ".join(f"`{s}`" for s in extract_signatures(qa_path, ["validate_generated_image", "configure_qa_runtime"])))

    out.extend([
        "",
        f"## 4. V3 포즈 DB 현황 (총 {p_stats['total_keys']}키 = 활성 {p_stats['active_keys']} / deprecated {p_stats['deprecated_keys']})",
        "- 섹션별 구성: " + ", ".join(p_stats["sections"]),
        "- `pose_sets.json`: " + ", ".join(p_stats["pose_sets"]),
    ])
    return "\n".join(out) + "\n"
