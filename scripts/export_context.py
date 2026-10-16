"""
scripts/export_context.py
외부 AI(Gemini Notebook 등) 코드 리뷰용 plepa · kiro 컨텍스트 스냅샷 생성기.

모든 정보는 사람이 요약하지 않고 코드/JSON/git 상태에서 직접 추출하며,
고정 파일명으로 context_snapshot/ 에 덮어써서 외부 AI가 과거 정보(Stale Context)를 참조하지 않도록 합니다.

출력:
  00_README_FOR_AI.md       읽기 규칙, snapshot_id, 폐지 목록(Deprecation Ledger), 직전 대비 변경분
  10_TIER1_CONSTITUTION.md  불변 원칙, 포즈 번호 대역, 에이전트 규칙, ADR 목록
  20_TIER2_CORE_LOGIC.md    Mutator 체인, 상수, 함수 시그니처, 생성 옵션, QC/검열 파라미터, 포즈 DB 요약
  30_TIER3_RUNTIME.md       에셋 매트릭스, QC 결함, plepa↔kiro Drift, (선택) 테스트/precheck 결과
  40_CORE_CODE.md           (--full-code) Tier 2 핵심 모듈 원문

사용법:
  python scripts/export_context.py
  python scripts/export_context.py --run-tests --full-code
  python scripts/export_context.py --include-prompts      # 포즈 프롬프트 원문 포함
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PLEPA_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KIRO_ROOT = Path(r"C:\Users\rbsgh\kiro")
OUT_DIR_NAME = "context_snapshot"
HASH_STATE_FILE = ".hashes.json"

# 폐지 목록: 외부 AI가 과거 대화/업로드에서 본 번호·체계를 다시 쓰지 않도록 명시합니다.
# 새 폐지 결정이 생기면 이 목록에 한 줄 추가합니다.
DEPRECATION_LEDGER: List[Tuple[str, str, str]] = [
    ("오토코노코 특수 슬롯 200번", "133~135 (special_otokonoko, 130~132와 +3 대칭)", "ADR 50"),
    ("130번 라벨 '스릴만점밀회' / '빈강의실교탁후배위'", "'빈강의실 섹스' 등 [장소]+[액션] 라벨", "ADR 50"),
    ("80종 포즈 체계 (00~59 / 140~159, 오토코노코 +100)", "V2 대역 (000~197, 오토코노코 +70)", "ADR 45"),
    ("FLUX 파이프라인 / flux_pose_database.json", "SDXL 단일 파이프라인 (FLUX는 legacy/ 격리, 참조 금지)", "GEMINI.md"),
    ("캐릭터 JSON의 long slender limbs", "balanced body proportions", "제작규칙 1.1"),
    ("긍정 가중치 1.15 초과 / 중첩 괄호 ((...))", "clamp_sdxl_weights() 자동 클램핑 (긍정 1.15, 부정 1.25)", "제작규칙 2.2"),
]

# Tier 2 상수/시그니처 추출 대상 모듈
CORE_MODULES = [
    "plepa_engine/config.py",
    "plepa_engine/prompt_builder.py",
    "plepa_engine/prompt_pipeline.py",
    "plepa_engine/qa_validator.py",
    "plepa_engine/censor.py",
    "plepa_engine/precheck.py",
    "plepa_engine/workflow_templates.py",
    "plepa_engine/services/generation_service.py",
    "plepa_engine/services/pose_service.py",
]

# 변경분(Delta) 추적 대상 (plepa 기준 상대경로)
TRACKED_GLOBS = [
    "plepa_engine/**/*.py",
    "data/*.json",
    "data/themes/*.json",
    "projects/*/pose_overrides.json",
    "projects/*/background.json",
    "projects/*/characters/*.json",
    "docs/캐릭터_포즈_제작_규칙.md",
    "GEMINI.md",
]

# plepa ↔ kiro 공유 파일 (plepa 경로, kiro 경로)
SHARED_FILES = [
    ("plepa_engine/censor.py", "generator/censor.py"),
    ("plepa_engine/qa_validator.py", "generator/qa_validator.py"),
]


# ──────────────────────────────────────────────────────────────────────────────
# 공통 유틸
# ──────────────────────────────────────────────────────────────────────────────

def sha(path: Path, n: int = 8) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:n]
    except OSError:
        return "missing"


def line_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return 0


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def git_info(root: Path) -> Dict[str, Any]:
    def run(*args: str) -> str:
        try:
            return subprocess.run(
                ["git", "-C", str(root), *args],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
            ).stdout.strip()
        except Exception:
            return ""

    if not (root / ".git").exists():
        return {"sha": "no-git", "branch": "-", "dirty": 0, "dirty_files": []}
    porcelain = [l for l in run("status", "--porcelain").splitlines() if l.strip()]
    return {
        "sha": run("rev-parse", "--short", "HEAD") or "unknown",
        "branch": run("rev-parse", "--abbrev-ref", "HEAD") or "-",
        "dirty": len(porcelain),
        "dirty_files": porcelain[:30],
    }


def header(title: str, snap: Dict[str, Any]) -> str:
    return (
        f"# {title}\n\n"
        f"> snapshot_id: `{snap['snapshot_id']}`  \n"
        f"> generated_at: {snap['generated_at']}  \n"
        f"> 이 파일은 `scripts/export_context.py`가 코드에서 자동 생성했습니다. "
        f"snapshot_id가 다른 정보는 모두 폐기하고 이 내용을 기준으로 판단하세요.\n\n"
    )


def md_table(headers: List[str], rows: List[List[Any]]) -> str:
    def cell(v: Any) -> str:
        return str(v).replace("|", "\\|").replace("\n", " ")
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(":---" for _ in headers) + " |"]
    out += ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def short(value: Any, limit: int = 120) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


# ──────────────────────────────────────────────────────────────────────────────
# AST 추출
# ──────────────────────────────────────────────────────────────────────────────

def parse_module(path: Path) -> Optional[ast.Module]:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def extract_constants(tree: ast.Module) -> List[Tuple[str, str]]:
    """모듈 최상위 UPPER_CASE 상수와 리터럴 값을 추출합니다."""
    result = []
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
            value = node.value
        else:
            continue
        for t in targets:
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,}", t.id) or value is None:
                continue
            try:
                lit = ast.literal_eval(value)
                if isinstance(lit, (dict, list, tuple, set, frozenset)) and len(lit) > 8:
                    shown = f"{type(lit).__name__}[{len(lit)}] " + short(lit, 100)
                else:
                    shown = short(lit)
            except Exception:
                shown = "(expr) " + short(ast.unparse(value), 100)
            result.append((t.id, shown))
    return result


def extract_signatures(tree: ast.Module) -> List[Tuple[str, str, str]]:
    """공개 함수/클래스(메서드 포함)의 시그니처와 docstring 첫 줄을 추출합니다."""
    rows = []

    def first_doc(n: ast.AST) -> str:
        doc = ast.get_docstring(n) or ""
        return doc.strip().splitlines()[0] if doc.strip() else ""

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            rows.append((f"def {node.name}({ast.unparse(node.args)})", "", first_doc(node)))
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            bases = ", ".join(ast.unparse(b) for b in node.bases)
            rows.append((f"class {node.name}({bases})", "", first_doc(node)))
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                    not sub.name.startswith("_") or sub.name == "__call__"
                ):
                    rows.append((f"  .{sub.name}()", node.name, first_doc(sub)))
    return rows


def extract_dataclass_fields(tree: ast.Module, class_name: str) -> List[Tuple[str, str, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            fields = []
            for sub in node.body:
                if isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name):
                    default = ast.unparse(sub.value) if sub.value is not None else "(required)"
                    fields.append((sub.target.id, ast.unparse(sub.annotation), short(default, 60)))
            return fields
    return []


def extract_pipeline_order(tree: ast.Module) -> List[str]:
    """SDXLPromptPipeline 내부에서 인스턴스화되는 Mutator 순서를 추출합니다."""
    order = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "SDXLPromptPipeline":
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id.endswith("Mutator"):
                    order.append(call.func.id)
    return order


def extract_class_docs(tree: ast.Module, suffix: str) -> Dict[str, str]:
    docs = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name.endswith(suffix):
            doc = ast.get_docstring(node) or ""
            docs[node.name] = " ".join(doc.split())[:220]
    return docs


# ──────────────────────────────────────────────────────────────────────────────
# Tier 1
# ──────────────────────────────────────────────────────────────────────────────

def build_tier1(snap: Dict[str, Any]) -> str:
    out = [header("TIER 1 · 불변 원칙 및 규격 (Constitution)", snap)]

    pose_db = load_json(PLEPA_ROOT / "data" / "sdxl_pose_database.json") or {}
    structure = pose_db.get("_structure", {})
    out.append("## 1. V2 포즈 번호 대역 (`data/sdxl_pose_database.json` `_structure`)\n\n")
    if structure:
        out.append(md_table(["섹션", "정의"], [[k, short(v, 160)] for k, v in structure.items()]))
    out.append(
        "\n- 오토코노코 성인 코드 = 여성 성인 코드 + 70 (080↔150 … 127↔197)\n"
        "- 로스터 전용 슬롯: 048~052 일상 5종, 130~132 여성 특수, 133~135 오토코노코 특수 (130~132 +3)\n"
        "- 특수 슬롯 라벨은 AI 챗봇 트리거 매칭용 `[장소] + [핵심 액션]` 형식\n\n"
    )

    rules = PLEPA_ROOT / "GEMINI.md"
    if rules.exists():
        out.append("## 2. 에이전트 규칙 원문 (`GEMINI.md`)\n\n")
        out.append(rules.read_text(encoding="utf-8").strip() + "\n\n")

    handover = PLEPA_ROOT / "docs" / "AI_HANDOVER_GUIDE.md"
    if handover.exists():
        titles = re.findall(r"^\s*(\d+)\.\s+\*\*(.+?)\*\*", handover.read_text(encoding="utf-8"), re.M)
        out.append(f"## 3. ADR 목록 (`docs/AI_HANDOVER_GUIDE.md`, 총 {len(titles)}건)\n\n")
        out.append(md_table(["#", "결정"], [[n, t] for n, t in titles]))

    out.append(
        "\n## 4. 고정 아키텍처 사실\n\n"
        "- plepa: ComfyUI 로컬 API, SDXL 단일 (`unholyDesireMixSinister_v90`), RTX 4060 Ti 8GB + RAM 48GB 최적화\n"
        "- kiro: Stable Diffusion WebUI (Forge/A1111) API, `generator/` 패키지\n"
        "- plepa가 상위 원천(Upstream). `scripts/sync_to_kiro.py`로 포즈 DB, 오버라이드, 배경 매핑, censor, qa_validator를 kiro에 전파\n"
        "- 프롬프트 데이터는 `data/`·`projects/`, 파이프라인 로직은 `plepa_engine/`에 격리\n"
        "- 생성 옵션 추가 시 Trinity Sync: `GenerationParams` → `batch_generator.py` → `plepa_gui` → `tests/test_cli_gui_sync.py`\n"
    )
    return "".join(out)


# ──────────────────────────────────────────────────────────────────────────────
# Tier 2
# ──────────────────────────────────────────────────────────────────────────────

def summarize_pose_db(include_prompts: bool) -> str:
    out = []
    db = load_json(PLEPA_ROOT / "data" / "sdxl_pose_database.json") or {}
    rows = []
    for section, entries in db.items():
        if section.startswith("_") or not isinstance(entries, dict):
            continue
        codes = sorted(entries.keys())
        rng = f"{codes[0]}~{codes[-1]}" if codes else "-"
        outfits: Dict[str, int] = {}
        for e in entries.values():
            if isinstance(e, dict):
                key = e.get("required_outfit", "default")
                outfits[key] = outfits.get(key, 0) + 1
        rows.append([section, len(entries), rng, ", ".join(f"{k}:{v}" for k, v in outfits.items())])
    out.append("### 섹션 요약\n\n" + md_table(["섹션", "포즈 수", "코드 범위", "required_outfit 분포"], rows))

    out.append("\n### 전체 포즈 라벨\n\n")
    for section, entries in db.items():
        if section.startswith("_") or not isinstance(entries, dict) or not entries:
            continue
        out.append(f"**{section}**\n\n")
        lines = []
        for code in sorted(entries):
            e = entries[code] if isinstance(entries[code], dict) else {}
            flags = []
            if e.get("prompt_otokonoko"):
                flags.append("otoko분기")
            if e.get("required_outfit", "default") != "default":
                flags.append(e.get("required_outfit"))
            item = f"- `{code}` {e.get('label', '?')}" + (f" ({', '.join(flags)})" if flags else "")
            if include_prompts and e.get("prompt"):
                item += f"\n  - prompt: `{e['prompt']}`"
            lines.append(item)
        out.append("\n".join(lines) + "\n\n")

    out.append("### 로스터 오버라이드 (`projects/*/pose_overrides.json`)\n\n")
    ov_rows = []
    for path in sorted((PLEPA_ROOT / "projects").glob("*/pose_overrides.json")):
        data = load_json(path) or {}
        for section, entries in data.items():
            if section.startswith("_") or not isinstance(entries, dict):
                continue
            labels = ", ".join(f"{c} {v.get('label', '?')}" for c, v in sorted(entries.items()) if isinstance(v, dict))
            ov_rows.append([path.parent.name, section, len(entries), labels])
    out.append(md_table(["로스터", "섹션", "수", "코드/라벨"], ov_rows) if ov_rows else "(없음)\n")

    themes = sorted((PLEPA_ROOT / "data" / "themes").glob("*.json"))
    if themes:
        t_rows = []
        for p in themes:
            d = load_json(p)
            n = sum(len(v) for v in d.values() if isinstance(v, dict)) if isinstance(d, dict) else 0
            t_rows.append([p.name, n, sha(p)])
        out.append("\n### 테마 액션 DB (`data/themes/`)\n\n" + md_table(["파일", "항목 수", "sha"], t_rows))
    return "".join(out)


def extract_qc_parameters() -> List[List[str]]:
    path = PLEPA_ROOT / "plepa_engine" / "qa_validator.py"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    rows = []
    m = re.search(r"conf_threshold:\s*float\s*=\s*([\d.]+)", text)
    if m:
        rows.append(["person/head 기본 임계값 (conf_threshold)", m.group(1)])
    for name, var in (("hand", "raw_hands"), ("face", "raw_faces")):
        m = re.search(rf"{var}.*?>=\s*([\d.]+)", text, re.S)
        if m:
            rows.append([f"{name} 임계값", m.group(1)])
    for m in re.finditer(r'metrics\["(\w+)"\]\s*>\s*(\d+)', text):
        rows.append([f"판정 상한: {m.group(1)} >", m.group(2)])
    m = re.search(r"max_faces\s*=\s*(.+)", text)
    if m:
        rows.append(["2인 씬 얼굴 상한식", m.group(1).strip()])
    m = re.search(r"usable_threads\s*=\s*(.+)", text)
    if m:
        rows.append(["CPU 스레드 계산식", m.group(1).strip()])
    if "BELOW_NORMAL_PRIORITY_CLASS" in text:
        rows.append(["프로세스 우선순위", "BELOW_NORMAL_PRIORITY_CLASS"])
    return rows


def build_tier2(snap: Dict[str, Any], include_prompts: bool) -> str:
    out = [header("TIER 2 · 코어 로직 (수시 변경)", snap)]

    # 1. Mutator 체인
    pp = PLEPA_ROOT / "plepa_engine" / "prompt_pipeline.py"
    tree = parse_module(pp)
    if tree:
        order = extract_pipeline_order(tree)
        docs = extract_class_docs(tree, "Mutator")
        out.append(f"## 1. SDXL 프롬프트 파이프라인 (`prompt_pipeline.py` · sha {sha(pp)} · {line_count(pp)}줄)\n\n")
        out.append(md_table(["순서", "Mutator", "역할 (docstring)"], [[i + 1, n, docs.get(n, "")] for i, n in enumerate(order)]))

    # 2. 생성 옵션
    gs = PLEPA_ROOT / "plepa_engine" / "services" / "generation_service.py"
    gtree = parse_module(gs)
    if gtree:
        fields = extract_dataclass_fields(gtree, "GenerationParams")
        out.append(f"\n## 2. 생성 옵션 SSOT `GenerationParams` (총 {len(fields)}개)\n\n")
        out.append(md_table(["필드", "타입", "기본값"], [list(f) for f in fields]))

    # 3. 데이터 모델
    mp = PLEPA_ROOT / "plepa_engine" / "models.py"
    mtree = parse_module(mp)
    if mtree:
        out.append(f"\n## 3. 결과 데이터 모델 (`models.py` · sha {sha(mp)})\n\n")
        for cls in ("PoseEntry", "GenerationTarget", "GenerationResult"):
            f = extract_dataclass_fields(mtree, cls)
            if f:
                out.append(f"**{cls}**\n\n" + md_table(["필드", "타입", "기본값"], [list(x) for x in f]) + "\n")

    # 4. Auto-QC
    out.append("\n## 4. Auto-QC 파라미터 (`qa_validator.py`)\n\n")
    out.append(md_table(["항목", "값"], extract_qc_parameters()))

    # 5. 모듈별 상수 및 시그니처
    out.append("\n## 5. 핵심 모듈 상수 및 공개 API\n\n")
    for rel in CORE_MODULES:
        path = PLEPA_ROOT / rel
        t = parse_module(path)
        if not t:
            continue
        out.append(f"### `{rel}` · sha {sha(path)} · {line_count(path)}줄\n\n")
        consts = extract_constants(t)
        if consts:
            out.append(md_table(["상수", "값"], [list(c) for c in consts]) + "\n")
        sigs = extract_signatures(t)
        if sigs:
            out.append(md_table(["시그니처", "소속", "설명"], [list(s) for s in sigs]) + "\n")

    # 6. 체크포인트 프로필
    cp = load_json(PLEPA_ROOT / "plepa_engine" / "checkpoint_profiles.json")
    if cp is not None:
        out.append("## 6. 체크포인트 프로필 (`checkpoint_profiles.json`)\n\n```json\n")
        out.append(json.dumps(cp, ensure_ascii=False, indent=2)[:6000] + "\n```\n\n")

    # 7. 포즈 DB
    out.append("## 7. 포즈 DB 현황\n\n" + summarize_pose_db(include_prompts))
    return "".join(out)


# ──────────────────────────────────────────────────────────────────────────────
# Tier 3
# ──────────────────────────────────────────────────────────────────────────────

def build_asset_matrix() -> Tuple[str, List[List[Any]]]:
    sys.path.insert(0, str(PLEPA_ROOT))
    out, qc_rows = [], []
    try:
        from plepa_engine.services.asset_service import default_asset_service
    except Exception as e:
        return f"(asset_service 로드 실패: {e})\n", qc_rows

    for roster_dir in sorted((PLEPA_ROOT / "projects").iterdir()):
        if not (roster_dir / "characters").is_dir():
            continue
        try:
            reports = default_asset_service.audit_roster_assets(roster_dir.name)
        except Exception as e:
            out.append(f"### {roster_dir.name}\n\n(감사 실패: {e})\n\n")
            continue
        if not reports:
            continue
        rows = []
        for r in reports:
            missing = r.get("missing_codes") or []
            miss_txt = ", ".join(missing[:12]) + (f" 외 {len(missing) - 12}" if len(missing) > 12 else "")
            rows.append([
                r.get("prefix"), r.get("gender"),
                f"{r.get('present_count')}/{r.get('expected_count')}",
                f"{r.get('completion_rate')}%", r.get("origin_count"),
                r.get("outdated_labels"), miss_txt or "-",
            ])
        out.append(f"### {roster_dir.name} ({len(reports)}명)\n\n")
        out.append(md_table(["char", "성별", "완비", "달성률", "_origin", "구라벨", "누락 코드"], rows) + "\n")

        for manifest in (roster_dir / "assets").glob("*/_batch_manifest.json"):
            data = load_json(manifest) or {}
            for item in data.get("items", []):
                if item.get("qc_passed") is False:
                    qc_rows.append([roster_dir.name, data.get("prefix"), item.get("code"),
                                    item.get("label"), item.get("qc_reason"), item.get("retries")])
    return "".join(out), qc_rows


def build_drift(kiro_root: Path) -> str:
    out = []
    if not kiro_root.exists():
        return f"(kiro 경로 없음: {kiro_root})\n"
    rows = []
    for p_rel, k_rel in SHARED_FILES:
        p, k = PLEPA_ROOT / p_rel, kiro_root / k_rel
        hp, hk = sha(p), sha(k)
        rows.append([p_rel, f"{hp} ({line_count(p)}L)", f"{hk} ({line_count(k)}L)", "✅ 동일" if hp == hk else "❌ 분기"])

    def section_counts(path: Path) -> Dict[str, int]:
        d = load_json(path) or {}
        return {s: len(v) for s, v in d.items() if isinstance(v, dict) and not s.startswith("_")}

    pc = section_counts(PLEPA_ROOT / "data" / "sdxl_pose_database.json")
    kc = section_counts(kiro_root / "pose_database.json")
    for s in sorted(set(pc) | set(kc)):
        a, b = pc.get(s, "-"), kc.get(s, "-")
        rows.append([f"pose DB · {s}", a, b, "✅ 동일" if a == b else "❌ 차이"])

    for ov in sorted((PLEPA_ROOT / "projects").glob("*/pose_overrides.json")):
        k = kiro_root / "projects" / ov.parent.name / "pose_overrides.json"
        if k.exists():
            hp, hk = sha(ov), sha(k)
            rows.append([f"overrides · {ov.parent.name}", hp, hk, "✅ 동일" if hp == hk else "❌ 분기"])

    out.append(md_table(["대상", "plepa", "kiro", "상태"], rows))

    p_rosters = {d.name for d in (PLEPA_ROOT / "projects").iterdir() if d.is_dir()}
    k_rosters = {d.name for d in (kiro_root / "projects").iterdir() if d.is_dir()} if (kiro_root / "projects").exists() else set()
    out.append(
        f"\n- 공통 로스터: {', '.join(sorted(p_rosters & k_rosters)) or '-'}\n"
        f"- plepa 전용: {', '.join(sorted(p_rosters - k_rosters)) or '-'}\n"
        f"- kiro 전용: {', '.join(sorted(k_rosters - p_rosters)) or '-'}\n"
    )
    return "".join(out)


def run_checks() -> str:
    out = []
    py = sys.executable
    env_cmd = {"cwd": str(PLEPA_ROOT), "capture_output": True, "text": True,
               "encoding": "utf-8", "errors": "replace", "timeout": 900}
    import os
    env = dict(os.environ, PYTHONPATH=str(PLEPA_ROOT), PYTHONIOENCODING="utf-8")
    try:
        r = subprocess.run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider"], env=env, **env_cmd)
        tail = [l for l in r.stdout.splitlines() if re.search(r"passed|failed|error", l)]
        out.append(f"- pytest: `{tail[-1].strip('= ') if tail else 'no summary'}` (exit {r.returncode})\n")
        fails = [l for l in r.stdout.splitlines() if l.startswith(("FAILED", "ERROR"))]
        out += [f"  - {l}\n" for l in fails[:20]]
    except Exception as e:
        out.append(f"- pytest 실행 실패: {e}\n")
    for roster in ("campus", "spy"):
        try:
            r = subprocess.run([py, "-m", "plepa_engine.precheck", "-r", roster], env=env, **env_cmd)
            verdict = next((l.strip() for l in r.stdout.splitlines() if "PASS" in l or "FAIL" in l or "위반" in l), "no verdict")
            out.append(f"- precheck {roster}: {verdict} (exit {r.returncode})\n")
        except Exception as e:
            out.append(f"- precheck {roster} 실행 실패: {e}\n")
    return "".join(out)


def build_tier3(snap: Dict[str, Any], kiro_root: Path, run_tests: bool, delta: List[str]) -> str:
    out = [header("TIER 3 · 런타임 및 에셋 지표 (실시간)", snap)]

    out.append("## 1. 직전 스냅샷 대비 변경분\n\n")
    out.append("\n".join(delta) + "\n\n" if delta else "변경 없음 (또는 첫 스냅샷)\n\n")

    out.append("## 2. Git 상태\n\n")
    out.append(md_table(["레포", "branch", "HEAD", "미커밋 파일 수"], [
        ["plepa", snap["plepa"]["branch"], snap["plepa"]["sha"], snap["plepa"]["dirty"]],
        ["kiro", snap["kiro"]["branch"], snap["kiro"]["sha"], snap["kiro"]["dirty"]],
    ]))
    for name in ("plepa", "kiro"):
        if snap[name]["dirty_files"]:
            out.append(f"\n<details><summary>{name} 미커밋 파일</summary>\n\n```\n" + "\n".join(snap[name]["dirty_files"]) + "\n```\n</details>\n")

    out.append("\n## 3. plepa ↔ kiro Drift\n\n" + build_drift(kiro_root))

    matrix, qc_rows = build_asset_matrix()
    out.append("\n## 4. Auto-QC 결함 이력 (`_batch_manifest.json`, qc_passed=False)\n\n")
    out.append(md_table(["로스터", "char", "코드", "라벨", "사유", "리롤"], qc_rows) if qc_rows else "기록된 결함 없음\n")

    out.append("\n## 5. 로스터별 에셋 달성률 (`audit_roster_assets`)\n\n" + matrix)

    out.append("\n## 6. 테스트 / 사전점검\n\n")
    out.append(run_checks() if run_tests else "실행 안 함 (`--run-tests`로 포함)\n")
    return "".join(out)


# ──────────────────────────────────────────────────────────────────────────────
# Delta / README / 코드 번들
# ──────────────────────────────────────────────────────────────────────────────

def collect_hashes(kiro_root: Path) -> Dict[str, str]:
    hashes = {}
    for pattern in TRACKED_GLOBS:
        for p in PLEPA_ROOT.glob(pattern):
            if p.is_file() and "legacy" not in p.parts and "__pycache__" not in p.parts:
                hashes[p.relative_to(PLEPA_ROOT).as_posix()] = sha(p, 16)
    for _, k_rel in SHARED_FILES:
        k = kiro_root / k_rel
        if k.exists():
            hashes[f"kiro/{k_rel}"] = sha(k, 16)
    k_db = kiro_root / "pose_database.json"
    if k_db.exists():
        hashes["kiro/pose_database.json"] = sha(k_db, 16)
    return hashes


def compute_delta(prev: Dict[str, str], cur: Dict[str, str]) -> List[str]:
    if not prev:
        return []
    lines = []
    for k in sorted(set(prev) | set(cur)):
        if k not in prev:
            lines.append(f"- A `{k}`")
        elif k not in cur:
            lines.append(f"- D `{k}`")
        elif prev[k] != cur[k]:
            lines.append(f"- M `{k}`")
    return lines


def build_readme(snap: Dict[str, Any], delta: List[str], prev_id: Optional[str], files: List[str]) -> str:
    out = [header("PLEPA / KIRO CONTEXT SNAPSHOT · 읽기 규칙", snap)]
    out.append(
        "## 외부 AI 읽기 규칙\n\n"
        "1. 이 스냅샷의 `snapshot_id`와 다른 정보(이전 업로드, 이전 대화 기억)는 모두 **폐기**하세요.\n"
        "2. 포즈 번호, 라벨, 상수, 임계값을 언급할 때는 반드시 이 스냅샷 파일에서 확인한 값만 쓰세요. 확인되지 않으면 \"스냅샷에 없음\"이라고 답하세요.\n"
        "3. 아래 폐지 목록에 있는 번호나 체계는 사용하지 마세요.\n"
        "4. `legacy/` 경로(FLUX)는 리뷰 대상이 아닙니다.\n"
        "5. 코드 리뷰 제안에는 대상 파일의 sha를 함께 적어 주세요 (예: `censor.py@4df18f2e`). 사용자가 최신본인지 바로 대조할 수 있습니다.\n\n"
    )
    out.append("## 파일 구성\n\n" + "\n".join(f"- `{f}`" for f in files) + "\n\n")
    out.append(f"## 직전 스냅샷 대비 변경분\n\n직전 snapshot_id: `{prev_id or '없음'}`\n\n")
    out.append("\n".join(delta) + "\n\n" if delta else "변경 없음 (또는 첫 스냅샷)\n\n")
    out.append("## 폐지 목록 (Deprecation Ledger)\n\n")
    out.append(md_table(["폐지 항목", "현재 기준", "근거"], [list(r) for r in DEPRECATION_LEDGER]))
    return "".join(out)


def build_code_bundle(snap: Dict[str, Any]) -> str:
    out = [header("CORE CODE · Tier 2 핵심 모듈 원문", snap)]
    for rel in CORE_MODULES + ["plepa_engine/models.py", "plepa_engine/reporter.py"]:
        p = PLEPA_ROOT / rel
        if p.exists():
            out.append(f"## `{rel}` · sha {sha(p)}\n\n```python\n{p.read_text(encoding='utf-8')}\n```\n\n")
    return "".join(out)


# ──────────────────────────────────────────────────────────────────────────────
# main
# ──────────────────────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="외부 AI 리뷰용 plepa/kiro 컨텍스트 스냅샷 생성")
    parser.add_argument("--kiro-root", default=str(DEFAULT_KIRO_ROOT), help="kiro 레포 경로")
    parser.add_argument("--out", default=str(PLEPA_ROOT / OUT_DIR_NAME), help="출력 폴더")
    parser.add_argument("--run-tests", action="store_true", help="pytest 및 precheck 결과 포함 (수 분 소요)")
    parser.add_argument("--full-code", action="store_true", help="Tier 2 핵심 모듈 원문(40_CORE_CODE.md) 포함")
    parser.add_argument("--include-prompts", action="store_true", help="포즈 프롬프트 원문 포함")
    args = parser.parse_args(argv)

    kiro_root = Path(args.kiro_root)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    plepa_git, kiro_git = git_info(PLEPA_ROOT), git_info(kiro_root)

    def tag(g: Dict[str, Any]) -> str:
        return g["sha"] + ("+dirty" if g["dirty"] else "")

    snap = {
        "snapshot_id": f"{time.strftime('%Y%m%d-%H%M')}-plepa@{tag(plepa_git)}-kiro@{tag(kiro_git)}",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "plepa": plepa_git,
        "kiro": kiro_git,
    }

    state_path = out_dir / HASH_STATE_FILE
    prev_state = load_json(state_path) or {}
    cur_hashes = collect_hashes(kiro_root)
    delta = compute_delta(prev_state.get("hashes", {}), cur_hashes)

    files = {
        "10_TIER1_CONSTITUTION.md": build_tier1(snap),
        "20_TIER2_CORE_LOGIC.md": build_tier2(snap, args.include_prompts),
        "30_TIER3_RUNTIME.md": build_tier3(snap, kiro_root, args.run_tests, delta),
    }
    if args.full_code:
        files["40_CORE_CODE.md"] = build_code_bundle(snap)
    else:
        stale = out_dir / "40_CORE_CODE.md"
        if stale.exists():
            stale.unlink()  # 이전 실행의 코드 번들이 남아 과거 정보로 쓰이지 않도록 제거
    files = {"00_README_FOR_AI.md": build_readme(snap, delta, prev_state.get("snapshot_id"), ["00_README_FOR_AI.md", *files]), **files}

    for name, content in files.items():
        (out_dir / name).write_text(content, encoding="utf-8")
    state_path.write_text(json.dumps({"snapshot_id": snap["snapshot_id"], "hashes": cur_hashes},
                                     ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[export_context] snapshot_id: {snap['snapshot_id']}")
    for name in files:
        p = out_dir / name
        print(f"  - {p.relative_to(out_dir.parent) if out_dir.parent in p.parents else p}  ({p.stat().st_size // 1024} KB)")
    print(f"  변경분: {len(delta)}건" if prev_state else "  첫 스냅샷 (변경분 기준선 저장)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
