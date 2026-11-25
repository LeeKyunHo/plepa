"""
scripts.context_exporter.runtime_and_telemetry
런타임 상태, ADR 추출, 스킬/SSOT 문서 수집, Gen-IT 현황, 구 스냅샷 청소 및 AST 텔레메트리 유틸리티.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from plepa_engine.config import DEFAULT_SDXL_CKPT, PROJECTS_DIR, ROOT_DIR as PLEPA_ROOT

COLLECTED_FILE_BUDGETS: Dict[str, int] = {
    "00_README_FOR_AI.md": 20 * 1024,
    "10_TIER1_CONSTITUTION.md": 35 * 1024,
    "20_TIER2_CORE_LOGIC.md": 50 * 1024,
    "30_TIER3_RUNTIME.md": 25 * 1024,
    "50_REFACTORING_PLAN.md": 30 * 1024,
    "40_CORE_CODE.md": 80 * 1024,
}
DEFAULT_BASE_TOTAL_BUDGET = 160 * 1024
BASE_SNAPSHOT_FILES = (
    "00_README_FOR_AI.md",
    "10_TIER1_CONSTITUTION.md",
    "20_TIER2_CORE_LOGIC.md",
    "30_TIER3_RUNTIME.md",
    "50_REFACTORING_PLAN.md",
)


def git_info() -> Dict[str, Any]:
    """현재 Git 브랜치, HEAD SHA 및 워킹트리 변경 요약을 반환합니다."""
    def _run(args: List[str]) -> str:
        try:
            res = subprocess.run(
                ["git", *args],
                cwd=str(PLEPA_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            return res.stdout.strip() if res.returncode == 0 else ""
        except Exception:
            return ""

    branch = _run(["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
    commit = _run(["rev-parse", "--short", "HEAD"]) or "unknown"
    log_raw = _run(["log", "-n", "6", "--oneline"])
    status_raw = _run(["status", "--short"])
    return {
        "branch": branch,
        "commit": commit,
        "recent_commits": [line for line in log_raw.splitlines() if line.strip()],
        "dirty_files": [line for line in status_raw.splitlines() if line.strip()],
    }


def cleanup_stale_snapshots(snap_dir: Path, keep_files: set[str]) -> List[str]:
    """고정 스냅샷 목록(BASE_SNAPSHOT_FILES 등)에 없는 구 *.md 파일을 자동 삭제합니다."""
    removed: List[str] = []
    if not snap_dir.is_dir():
        return removed
    for p in sorted(snap_dir.glob("*.md")):
        if p.name not in keep_files:
            try:
                p.unlink()
                removed.append(p.name)
            except Exception:
                pass
    return removed


def extract_adrs(handover_path: Optional[Path] = None, max_items: int = 30) -> List[Tuple[str, str]]:
    """Active AI_HANDOVER_GUIDE.md에서 '### ADR-' 블록 요약 목록을 추출합니다."""
    target = handover_path or (PLEPA_ROOT / "docs" / "AI_HANDOVER_GUIDE.md")
    if not target.is_file():
        return []
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    blocks: List[Tuple[str, str]] = []
    cur_title: Optional[str] = None
    cur_body: List[str] = []
    for line in lines:
        if line.startswith("### ADR-"):
            if cur_title:
                blocks.append((cur_title, " ".join(cur_body).strip()))
            cur_title = line[4:].strip()
            cur_body = []
        elif line.startswith("## ") and cur_title:
            blocks.append((cur_title, " ".join(cur_body).strip()))
            cur_title = None
            cur_body = []
        elif cur_title and line.strip():
            cur_body.append(line.strip())
    if cur_title:
        blocks.append((cur_title, " ".join(cur_body).strip()))
    return blocks[-max_items:]


def collect_skills_catalog() -> List[Dict[str, str]]:
    """`.agents/skills/*/SKILL.md`의 프런트매터를 동적 파싱하여 스킬 카탈로그를 반환합니다."""
    skills_root = PLEPA_ROOT / ".agents" / "skills"
    out: List[Dict[str, str]] = []
    if not skills_root.is_dir():
        return out
    for skill_dir in sorted(skills_root.iterdir()):
        sm = skill_dir / "SKILL.md"
        if not skill_dir.is_dir() or not sm.is_file():
            continue
        text = sm.read_text(encoding="utf-8", errors="replace")
        m_name = re.search(r"(?m)^name:\s*(.+)$", text)
        m_desc = re.search(r"(?ms)^description:\s*(.+?)\n---", text)
        name = m_name.group(1).strip() if m_name else skill_dir.name
        raw_desc = m_desc.group(1).strip() if m_desc else ""
        clean_desc = " ".join(part.lstrip(">- ").strip() for part in raw_desc.splitlines()).strip()
        out.append({"name": name, "path": f".agents/skills/{skill_dir.name}/SKILL.md", "description": clean_desc})
    return out


def collect_active_ssot_docs() -> List[Dict[str, Any]]:
    """루트 및 docs/Active SSOT 문서 목록과 줄 수·역할 요약을 수집합니다."""
    doc_specs = [
        ("GEMINI.md", "최상위 에이전트 행동 헌법 (규칙 1~11)"),
        ("POSE_MAPPING.md", "V3 전체 포즈·모브·배경·deprecated 단일 SSOT"),
        ("사용법.txt", "CLI 플래그·포즈 표현식 치트시트"),
        ("README.md", "프로젝트 개요·SDXL 스택·디렉토리 요약"),
        ("docs/AI_HANDOVER_GUIDE.md", "현행 15대 불변식 + Active ADR 요약"),
        ("docs/RUNBOOK.md", "모델 설치·운영 게이트·트러블슈팅"),
        ("docs/GUI_GUIDE.md", "NiceGUI 8대 탭 + 수동 검열 에디터 안내"),
        ("docs/DOCUMENTATION_GUIDE.md", "Diataxis 문서 계층 & Push 전 5단계 게이트"),
        ("docs/플에파_기능명세.md", "엔진 아키텍처·7대 Mutator·REST API 명세"),
        ("docs/캐릭터_포즈_제작_규칙.md", "JSON·프롬프트 불변식·남캐 음영·7단계 precheck"),
        ("docs/젠잇_캐릭터채팅_제작법.md", "Gen-IT v2.2 5탭 시스템·Status/Line JSX 명세"),
        ("docs/REMOTE_INSPECTION_GUIDE.md", "8080/mobile & 8085/inspect 원격 검수 가이드"),
        ("docs/개발일지.md", "Quick Symptom Index + 최근 10회차 플레이북"),
    ]
    rows: List[Dict[str, Any]] = []
    for rel, role in doc_specs:
        p = PLEPA_ROOT / rel
        if p.is_file():
            lc = len(p.read_text(encoding="utf-8", errors="replace").splitlines())
            rows.append({"path": rel, "lines": lc, "bytes": p.stat().st_size, "role": role})
    return rows


def collect_genit_status() -> List[Dict[str, Any]]:
    """`docs/genit/*.md` 현행 상용 챗봇 문서 및 템플릿 상태를 수집합니다."""
    genit_dir = PLEPA_ROOT / "docs" / "genit"
    rows: List[Dict[str, Any]] = []
    if not genit_dir.is_dir():
        return rows
    for p in sorted(genit_dir.glob("*.md")):
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        head = "\n".join(lines[:15])
        m_st = re.search(r"(?m)^status:\s*(.+)$", head)
        m_ver = re.search(r"(?m)^version:\s*(.+)$", head)
        rows.append({
            "name": p.name,
            "lines": len(lines),
            "status": m_st.group(1).strip() if m_st else "active",
            "version": m_ver.group(1).strip() if m_ver else "-",
        })
    return rows


def build_asset_matrix() -> Tuple[str, List[List[Any]]]:
    """12개 로스터별 캐릭터 수, 설정 완비 상태 및 에셋 파일 수를 집계합니다 (이미지 내용 미열람)."""
    rows: List[List[Any]] = []
    if not PROJECTS_DIR.is_dir():
        return "| 로스터 | 캐릭터 | events | bg_map | 정규 에셋 | _origin |\n| :--- | :---: | :---: | :---: | :---: | :---: |", rows

    for rdir in sorted(PROJECTS_DIR.iterdir()):
        if not rdir.is_dir() or rdir.name.startswith("."):
            continue
        char_dir = rdir / "characters"
        chars = sorted(char_dir.glob("*.json")) if char_dir.is_dir() else []
        assets_dir = rdir / "assets"
        norm_cnt, orig_cnt = 0, 0
        if assets_dir.is_dir():
            for f in assets_dir.rglob("*.webp"):
                parts_low = [pt.lower() for pt in f.parts]
                if any(pt in parts_low for pt in ("_trash", "legacy_backups", "assets_archive_v1")):
                    continue
                if any(pt == "_origin" or pt.endswith("_origin") for pt in parts_low):
                    orig_cnt += 1
                else:
                    norm_cnt += 1
        rows.append([
            rdir.name,
            len(chars),
            "O" if (rdir / "events.json").is_file() else "-",
            "O" if (rdir / "pose_background_mapping.json").is_file() else "-",
            norm_cnt,
            orig_cnt,
        ])

    lines = [
        "| 로스터 | 캐릭터 수 | `events.json` | `bg_map` | 정규 WebP | `_origin` WebP |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
    ]
    for r in rows:
        lines.append(f"| `{r[0]}` | {r[1]}명 | {r[2]} | {r[3]} | {r[4]}장 | {r[5]}장 |")
    return "\n".join(lines), rows


def build_drift(kiro_root: Path) -> str:
    """`kiro` 레거시 브릿지 차단 상태 및 경로 존재 여부를 요약합니다."""
    exists_txt = "로컬 존재" if kiro_root.is_dir() else "미발견"
    return (
        f"- **동기화 정책**: `scripts/sync_to_kiro.py`는 `--force-unsafe` 없이 **기본 차단(`exit 2`)**됨 (구형 V2 덮어쓰기 방지).\n"
        f"- **대상 경로 (`{kiro_root.as_posix()}`)**: {exists_txt} · 현재 체크포인트 기본: `{DEFAULT_SDXL_CKPT}`"
    )


def parse_refactoring_progress(plan_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """`plepa_refactoring_analysis.md`의 Wave 0~5 체크박스를 파싱하여 진행 현황을 요약합니다."""
    target = plan_path or (PLEPA_ROOT / "plepa_refactoring_analysis.md")
    if not target.is_file():
        return []
    out: List[Dict[str, Any]] = []
    cur_wave: Optional[str] = None
    for line in target.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        m_flat = re.match(r"^-\s+\[( |x|X)\]\s+\*\*(Wave\s+\d+[^*]*)\*\*[:\s]*(.*)$", s)
        if m_flat:
            checked = m_flat.group(1).lower() == "x"
            title = m_flat.group(2).strip()
            detail = m_flat.group(3).lstrip(": ").strip()
            out.append({
                "wave": title,
                "done": 1 if checked else 0,
                "todo": 0 if checked else 1,
                "detail": detail,
            })
            cur_wave = None
            continue
        m_wave = re.match(r"^###\s+(Wave\s+\d+[^#\n]*)$", s)
        if m_wave:
            cur_wave = m_wave.group(1).strip()
            out.append({"wave": cur_wave, "done": 0, "todo": 0, "detail": ""})
            continue
        if cur_wave and re.match(r"^-\s+\[( |x|X)\]\s+", s):
            checked = s[3].lower() == "x"
            out[-1]["done" if checked else "todo"] += 1
    return out
