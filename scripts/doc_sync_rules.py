"""
scripts/doc_sync_rules.py
Active SSOT 문서·스킬·물리 가드 간 4대 드리프트 규칙, 변경 파일 매핑(--diff) 및 정형 자동 수정(--fix).
"""

from __future__ import annotations

import ast
import dataclasses
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

ACTIVE_ROOT_DOCS = ("GEMINI.md", "README.md", "사용법.txt")
_BACKTICK_PATH_RE = re.compile(r"`((?:plepa_engine|plepa_gui|scripts|docs|tests)/[^`\s\)]+)`")
_DEPRECATION_CTX_WORDS = (
    "구 ", "구버전", "은퇴", "폐지", "아카이브", "이관", "차단",
    "전환", "분해", "해체", "단일 거대 모듈", "기존 ", "대체", "금지",
    "삭제", "제외", "stale", "deprecated", "archive/",
)
_DEPRECATED_TERMS: Tuple[Tuple[str, str], ...] = (
    (":8085/inspect", "구 `:8085` 뷰어는 `scripts/archive/`로 은퇴 — `:8080/mobile`로 표기 통일"),
    ("POSE_MAPPING_V2.md", "포즈 단일 SSOT는 루트 `POSE_MAPPING.md`"),
    ("POSE_CATALOG.md", "포즈 단일 SSOT는 루트 `POSE_MAPPING.md`"),
    ("40_CORE_CODE.md", "`40_CORE_CODE.md`는 `--full-code` 임시 번들로 기본 5종에서 제외됨"),
    ("flux_pose_database.json", "SDXL 단일화로 FLUX DB 참조 금지"),
)

_DIFF_DOC_RULES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("plepa_engine/services/generation_options.py", ("사용법.txt", "docs/GUI_GUIDE.md", ".agents/skills/plepa-trinity-gui-sync/SKILL.md")),
    ("plepa_engine/services/generation/", ("docs/AI_HANDOVER_GUIDE.md", "docs/플에파_기능명세.md")),
    ("batch_generator.py", ("사용법.txt", "docs/RUNBOOK.md", ".agents/skills/plepa-trinity-gui-sync/SKILL.md")),
    ("plepa_engine/censor/", ("docs/AI_HANDOVER_GUIDE.md", "docs/플에파_기능명세.md", ".agents/skills/plepa-pipeline-qc-tuner/SKILL.md")),
    ("plepa_engine/pipeline/", ("docs/AI_HANDOVER_GUIDE.md", "docs/플에파_기능명세.md", ".agents/skills/plepa-pipeline-qc-tuner/SKILL.md")),
    ("plepa_engine/qa_", ("docs/AI_HANDOVER_GUIDE.md", ".agents/skills/plepa-pipeline-qc-tuner/SKILL.md")),
    ("plepa_gui/", ("docs/GUI_GUIDE.md", "docs/REMOTE_INSPECTION_GUIDE.md", ".agents/skills/plepa-trinity-gui-sync/SKILL.md")),
    ("data/sdxl_pose_database.json", ("POSE_MAPPING.md", ".agents/skills/plepa-pose-curator/SKILL.md")),
    ("data/themes/", ("POSE_MAPPING.md", "docs/GUI_GUIDE.md")),
    ("data/pose_sets.json", ("사용법.txt", "docs/GUI_GUIDE.md")),
    ("projects/", ("docs/캐릭터_포즈_제작_규칙.md", ".agents/skills/plepa-roster-character/SKILL.md")),
    (".agents/hooks/plepa_guard.py", ("GEMINI.md", "docs/DOCUMENTATION_GUIDE.md")),
    ("scripts/", ("scripts/README.md", "docs/RUNBOOK.md")),
    ("docs/genit/", ("docs/젠잇_캐릭터채팅_제작법.md",)),
    ("docs/novelchat/", ("docs/노벨챗_캐릭터채팅_제작법.md",)),
)


@dataclasses.dataclass
class DocDriftIssue:
    rule: str
    file_path: str
    line_no: int
    message: str
    fix_hint: str


def iter_ssot_markdown_files(root_dir: Path, include_journal: bool = True) -> List[Path]:
    """Active SSOT 문서 및 `.agents/skills/*/SKILL.md` 목록을 정렬 반환합니다."""
    files: List[Path] = []
    for rel in ACTIVE_ROOT_DOCS:
        p = root_dir / rel
        if p.is_file():
            files.append(p)
    docs_dir = root_dir / "docs"
    if docs_dir.is_dir():
        for p in sorted(docs_dir.glob("*.md")):
            if not include_journal and p.name == "개발일지.md":
                continue
            files.append(p)
    skills_dir = root_dir / ".agents" / "skills"
    if skills_dir.is_dir():
        for p in sorted(skills_dir.glob("*/SKILL.md")):
            files.append(p)
    return files


def _expand_braces(path_token: str) -> List[str]:
    """`a/{x,y}/b` 형태의 단일 중괄호 패턴을 실제 경로 목록으로 전개합니다."""
    m = re.search(r"\{([^{}]+)\}", path_token)
    if not m:
        return [path_token]
    options = [opt.strip() for opt in m.group(1).split(",") if opt.strip()]
    if not options:
        return [path_token]
    expanded: List[str] = []
    for opt in options:
        expanded.extend(_expand_braces(path_token[: m.start()] + opt + path_token[m.end() :]))
    return expanded


def _is_placeholder_or_context_exempt(raw: str, line: str) -> bool:
    if any(tok in raw for tok in ("<", ">", "...", "작품명", "skill-name", "roster", "char", "name")):
        if "{" in raw or "<" in raw:
            return True
    if "<" in raw or "..." in raw:
        return True
    if any(word in line for word in _DEPRECATION_CTX_WORDS):
        return True
    return False


def _path_exists(root_dir: Path, candidate: str) -> bool:
    clean = candidate.split("#", 1)[0].split("::", 1)[0].rstrip(".,:;*")
    if not clean:
        return True
    if "*" in clean or "?" in clean:
        return any(root_dir.glob(clean))
    return (root_dir / clean).exists()


def _extract_journal_active_slice(text: str) -> List[Tuple[int, str]]:
    """`개발일지.md`의 상단 빠른 색인표와 최신 1개 회차 라인만 추출합니다."""
    lines = text.splitlines()
    out: List[Tuple[int, str]] = []
    heading_count = 0
    for idx, line in enumerate(lines, 1):
        if line.startswith("### "):
            heading_count += 1
            if heading_count >= 2:
                break
        out.append((idx, line))
    return out


def check_path_existence(root_dir: Path) -> List[DocDriftIssue]:
    """규칙 1: Active SSOT 문서 및 스킬 내 백틱 코드 경로의 실존 여부를 검사합니다."""
    issues: List[DocDriftIssue] = []
    for doc_path in iter_ssot_markdown_files(root_dir, include_journal=True):
        rel_doc = doc_path.relative_to(root_dir).as_posix()
        text = doc_path.read_text(encoding="utf-8", errors="replace")
        line_pairs = (
            _extract_journal_active_slice(text)
            if doc_path.name == "개발일지.md"
            else list(enumerate(text.splitlines(), 1))
        )
        for line_no, line in line_pairs:
            for match in _BACKTICK_PATH_RE.finditer(line):
                raw = match.group(1)
                if _is_placeholder_or_context_exempt(raw, line):
                    continue
                for candidate in _expand_braces(raw):
                    if "{" in candidate or "}" in candidate:
                        continue
                    if not _path_exists(root_dir, candidate):
                        issues.append(DocDriftIssue(
                            rule="BROKEN_PATH",
                            file_path=rel_doc,
                            line_no=line_no,
                            message=f"존재하지 않는 참조 경로 `{candidate}`",
                            fix_hint="현행 경로로 수정하거나 은퇴/이관 맥락을 명시하세요.",
                        ))
    return issues


def check_deprecated_keywords(root_dir: Path) -> List[DocDriftIssue]:
    """규칙 2: 은퇴/폐지 항목이 폐지 안내 문맥 밖 현역 본문에 남아 있는지 검사합니다."""
    issues: List[DocDriftIssue] = []
    for doc_path in iter_ssot_markdown_files(root_dir, include_journal=False):
        rel_doc = doc_path.relative_to(root_dir).as_posix()
        for line_no, line in enumerate(doc_path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if any(word in line for word in _DEPRECATION_CTX_WORDS):
                continue
            for term, hint in _DEPRECATED_TERMS:
                if term in line:
                    issues.append(DocDriftIssue(
                        rule="DEPRECATED_TERM",
                        file_path=rel_doc,
                        line_no=line_no,
                        message=f"폐지 항목 `{term}`이(가) 현역 안내 문맥에 잔존함",
                        fix_hint=hint,
                    ))
    return issues


def _find_max_adr_number(handover_path: Path) -> int:
    if not handover_path.is_file():
        return 0
    nums = [int(m) for m in re.findall(r"ADR-(\d+)", handover_path.read_text(encoding="utf-8", errors="replace"))]
    return max(nums, default=0)


def check_inventory_and_adr_sync(root_dir: Path) -> List[DocDriftIssue]:
    """규칙 3: `docs/` 루트 활성 문서의 `DOCUMENTATION_GUIDE.md` 누락 및 ADR 범위 불일치를 검사합니다."""
    issues: List[DocDriftIssue] = []
    guide_path = root_dir / "docs" / "DOCUMENTATION_GUIDE.md"
    if not guide_path.is_file():
        return [DocDriftIssue("MISSING_GUIDE", "docs/DOCUMENTATION_GUIDE.md", 1, "문서 가이드 파일 누락", "docs/DOCUMENTATION_GUIDE.md 복원")]

    guide_text = guide_path.read_text(encoding="utf-8", errors="replace")
    docs_dir = root_dir / "docs"
    if docs_dir.is_dir():
        for doc_file in sorted(docs_dir.glob("*.md")):
            if doc_file.name not in guide_text:
                issues.append(DocDriftIssue(
                    rule="INVENTORY_GAP",
                    file_path="docs/DOCUMENTATION_GUIDE.md",
                    line_no=1,
                    message=f"활성 문서 `{doc_file.name}`이(가) 인벤토리 표에서 누락됨",
                    fix_hint=f"`docs/DOCUMENTATION_GUIDE.md` Active SSOT 표에 `{doc_file.name}`을 추가하세요.",
                ))

    max_adr = _find_max_adr_number(root_dir / "docs" / "AI_HANDOVER_GUIDE.md")
    m_range = re.search(r"ADR-80~(\d+)\+?", guide_text)
    if max_adr > 0 and m_range:
        doc_max = int(m_range.group(1))
        if max_adr > doc_max:
            line_no = guide_text[: m_range.start()].count("\n") + 1
            issues.append(DocDriftIssue(
                rule="ADR_RANGE_STALE",
                file_path="docs/DOCUMENTATION_GUIDE.md",
                line_no=line_no,
                message=f"표기된 ADR 상한(ADR-80~{doc_max})이 최신 ADR-{max_adr}보다 뒤처짐",
                fix_hint=f"`--fix` 실행 또는 `ADR-80~{max_adr}+`로 갱신하세요.",
            ))
    return issues


def _extract_guard_blocked_subtrees(guard_path: Path) -> Tuple[str, ...]:
    if not guard_path.is_file():
        return ()
    tree = ast.parse(guard_path.read_text(encoding="utf-8", errors="replace"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_BLOCKED_READ_SUBTREES":
                    val = ast.literal_eval(node.value)
                    if isinstance(val, (tuple, list)):
                        return tuple(str(x) for x in val)
    return ()


def check_guard_and_gemini_sync(root_dir: Path) -> List[DocDriftIssue]:
    """규칙 4: `.agents/hooks/plepa_guard.py` 차단 범위와 `GEMINI.md` 11장 설명 일치 여부를 검증합니다."""
    issues: List[DocDriftIssue] = []
    guard_path = root_dir / ".agents" / "hooks" / "plepa_guard.py"
    gemini_path = root_dir / "GEMINI.md"
    if not guard_path.is_file() or not gemini_path.is_file():
        return issues

    subtrees = _extract_guard_blocked_subtrees(guard_path)
    gemini_text = gemini_path.read_text(encoding="utf-8", errors="replace")
    m_sec = re.search(r"(## 11\..*)", gemini_text, re.DOTALL)
    sec11 = m_sec.group(1) if m_sec else gemini_text
    sec11_line = gemini_text[: m_sec.start()].count("\n") + 1 if m_sec else 1

    for required_prefix in ("scripts/archive/", "scripts/benchmarks/"):
        if required_prefix in subtrees and required_prefix.rstrip("/") not in sec11:
            issues.append(DocDriftIssue(
                rule="GUARD_DOC_DESYNC",
                file_path="GEMINI.md",
                line_no=sec11_line,
                message=f"plepa_guard `_BLOCKED_READ_SUBTREES`의 `{required_prefix}` 차단이 GEMINI.md 11장에 미반영됨",
                fix_hint=f"GEMINI.md 11장에 `{required_prefix}` 열람 차단을 명시하세요.",
            ))
    return issues


def run_all_doc_sync_checks(root_dir: Path) -> List[DocDriftIssue]:
    """4대 서류 드리프트 규칙을 모두 실행해 위반 목록을 반환합니다."""
    issues: List[DocDriftIssue] = []
    issues.extend(check_path_existence(root_dir))
    issues.extend(check_deprecated_keywords(root_dir))
    issues.extend(check_inventory_and_adr_sync(root_dir))
    issues.extend(check_guard_and_gemini_sync(root_dir))
    return issues


def compute_affected_docs(changed_files: Sequence[str]) -> Dict[str, List[str]]:
    """변경된 파일 목록을 기반으로 확인이 필요한 Active 서류/스킬 매핑을 반환합니다."""
    doc_to_triggers: Dict[str, List[str]] = {}
    for rel in changed_files:
        norm = rel.replace("\\", "/").strip()
        if not norm:
            continue
        for prefix, target_docs in _DIFF_DOC_RULES:
            if norm == prefix or norm.startswith(prefix):
                for doc in target_docs:
                    triggers = doc_to_triggers.setdefault(doc, [])
                    if norm not in triggers:
                        triggers.append(norm)
    return doc_to_triggers


def apply_deterministic_fixes(root_dir: Path) -> List[str]:
    """ADR 번호 범위 등 결정론적으로 안전한 정형 필드만 자동 갱신합니다 (서술 본문 무접촉)."""
    applied: List[str] = []
    guide_path = root_dir / "docs" / "DOCUMENTATION_GUIDE.md"
    max_adr = _find_max_adr_number(root_dir / "docs" / "AI_HANDOVER_GUIDE.md")
    if not guide_path.is_file() or max_adr <= 0:
        return applied

    text = guide_path.read_text(encoding="utf-8")
    new_text, count = re.subn(r"ADR-80~(\d+)\+?", f"ADR-80~{max_adr}+", text, count=1)
    if count and new_text != text:
        guide_path.write_text(new_text, encoding="utf-8")
        applied.append(f"docs/DOCUMENTATION_GUIDE.md: ADR 상한 표기 ➔ ADR-80~{max_adr}+ 자동 동기화")
    return applied
