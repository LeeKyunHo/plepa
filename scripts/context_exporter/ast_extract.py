"""
scripts.context_exporter.ast_extract
AST 기반 모듈 파싱, 상수·시그니처·데이터클래스 추출 및 래칫 텔레메트리 유틸리티.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from plepa_engine.config import ROOT_DIR as PLEPA_ROOT


def sha(target: Union[Path, str]) -> str:
    """파일(Path) 또는 UTF-8 문자열의 8자리 SHA-256 다이제스트를 반환합니다."""
    if isinstance(target, Path):
        data = target.read_bytes()
    else:
        data = str(target).encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:8]


@dataclass
class ModuleSummary:
    """단일 파이썬 파일의 AST 구조 및 크기 요약."""

    rel_path: str
    line_count: int
    docstring: str
    classes: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    constants: List[str] = field(default_factory=list)
    over_module_limit: bool = False
    oversized_functions: List[str] = field(default_factory=list)


def _format_arg(arg: ast.arg) -> str:
    ann = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
    return f"{arg.arg}{ann}"


def _format_fn_sig(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    parts = [_format_arg(a) for a in node.args.args]
    if node.args.vararg:
        parts.append("*" + node.args.vararg.arg)
    if node.args.kwarg:
        parts.append("**" + node.args.kwarg.arg)
    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
    return f"{prefix}def {node.name}({', '.join(parts)}){ret}"


def parse_module(path: Path) -> Optional[ast.Module]:
    """파이썬 파일을 AST 파싱해 `ast.Module`을 반환합니다."""
    try:
        src = path.read_text(encoding="utf-8")
        return ast.parse(src, filename=str(path))
    except Exception:
        return None


def summarize_module(path: Path) -> Optional[ModuleSummary]:
    """파이썬 파일의 요약 정보(줄수, 독스트링, 클래스/함수/상수/래칫)를 반환합니다."""
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
    except Exception:
        return None

    rel = path.resolve().relative_to(PLEPA_ROOT.resolve()).as_posix()
    lines = len(src.splitlines())
    raw_doc = ast.get_docstring(tree) or ""
    doc = raw_doc.strip().splitlines()[0] if raw_doc.strip() else ""

    classes: List[str] = []
    functions: List[str] = []
    constants: List[str] = []
    oversized_fns: List[str] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and hasattr(item, "end_lineno"):
                    fn_len = (item.end_lineno or item.lineno) - item.lineno + 1
                    if fn_len > 120:
                        oversized_fns.append(f"{node.name}.{item.name} ({fn_len}L)")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(_format_fn_sig(node))
            if hasattr(node, "end_lineno"):
                fn_len = (node.end_lineno or node.lineno) - node.lineno + 1
                if fn_len > 120:
                    oversized_fns.append(f"{node.name} ({fn_len}L)")
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id.isupper() and not tgt.id.startswith("_"):
                    constants.append(tgt.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id.isupper() and not node.target.id.startswith("_"):
                constants.append(node.target.id)

    return ModuleSummary(
        rel_path=rel,
        line_count=lines,
        docstring=doc,
        classes=classes,
        functions=functions,
        constants=constants,
        over_module_limit=(lines > 350),
        oversized_functions=oversized_fns,
    )


def _to_ast(target: Union[ast.Module, Path]) -> Optional[ast.Module]:
    return parse_module(target) if isinstance(target, Path) else target


def extract_constants(target: Union[ast.Module, Path], names: Optional[List[str]] = None) -> List[Tuple[str, str]]:
    """AST 모듈 또는 파일에서 최상위 대문자 상수 `(이름, 표현식)` 쌍 목록을 추출합니다."""
    tree = _to_ast(target)
    if tree is None:
        return []
    wanted = set(names) if names else None
    out: List[Tuple[str, str]] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and node.value is not None:
            val_s = ast.unparse(node.value)
            for t in node.targets:
                if isinstance(t, ast.Name) and (t.id.isupper() or (wanted and t.id in wanted)):
                    if wanted is None or t.id in wanted:
                        out.append((t.id, val_s))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            name = node.target.id
            if (name.isupper() or (wanted and name in wanted)) and (wanted is None or name in wanted):
                out.append((name, ast.unparse(node.value)))
    return out


def format_constants_snippet(path: Path, names: List[str]) -> str:
    """파일에서 지정된 상수 정의의 원문 소스 조각을 Markdown 코드블록용으로 추출합니다."""
    if not path.is_file():
        return ""
    src = path.read_text(encoding="utf-8")
    tree = parse_module(path)
    if tree is None:
        return ""
    wanted = set(names)
    chunks: List[str] = []
    for node in tree.body:
        hit = False
        if isinstance(node, ast.Assign):
            hit = any(isinstance(t, ast.Name) and t.id in wanted for t in node.targets)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            hit = node.target.id in wanted
        if hit:
            seg = ast.get_source_segment(src, node)
            if seg:
                chunks.append(seg if len(seg) <= 1500 else seg[:1500] + "\n# ... (truncated)")
    return "\n\n".join(chunks)


def extract_signatures(target: Union[ast.Module, Path], symbols: Optional[List[str]] = None) -> List[str]:
    """AST 모듈 또는 파일의 공개 클래스/함수 시그니처를 추출합니다."""
    tree = _to_ast(target)
    if tree is None:
        return []
    filter_set = set(symbols) if symbols else None
    out: List[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if filter_set and node.name not in filter_set:
                continue
            out.append(f"class {node.name}:")
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and not sub.name.startswith("_"):
                    out.append("    " + _format_fn_sig(sub))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if filter_set and node.name not in filter_set:
                continue
            if not node.name.startswith("_") or (filter_set and node.name in filter_set):
                out.append(_format_fn_sig(node))
    return out


def extract_dataclass_fields(target: Union[ast.Module, Path], class_name: str) -> List[Tuple[str, str, str]]:
    """AST 모듈 또는 파일에서 dataclass 필드의 `(이름, 타입, 기본값)` 튜플 목록을 추출합니다."""
    tree = _to_ast(target)
    if tree is None:
        return []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            fields_out: List[Tuple[str, str, str]] = []
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    ann = ast.unparse(item.annotation)
                    default = ast.unparse(item.value) if item.value is not None else ""
                    fields_out.append((item.target.id, ann, default))
            return fields_out
    return []


def collect_active_modules() -> List[ModuleSummary]:
    """plepa_engine/, plepa_gui/, scripts/, batch_generator.py의 활성 모듈 요약을 수집합니다."""
    candidates: List[Path] = []
    root_cli = PLEPA_ROOT / "batch_generator.py"
    if root_cli.is_file():
        candidates.append(root_cli)
    for folder in ("plepa_engine", "plepa_gui", "scripts"):
        base = PLEPA_ROOT / folder
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.py")):
            if any(skip in p.parts for skip in ("legacy", "archive", "__pycache__")):
                continue
            candidates.append(p)

    summaries: List[ModuleSummary] = []
    for p in candidates:
        s = summarize_module(p)
        if s is not None:
            summaries.append(s)
    return summaries


def ast_telemetry(summaries: Optional[List[ModuleSummary]] = None) -> Dict[str, Any]:
    """비대 모듈(>350L) 및 비대 함수(>120L) 실시간 텔레메트리를 계산합니다."""
    items = summaries if summaries is not None else collect_active_modules()
    over_mods = sorted([m for m in items if m.over_module_limit], key=lambda x: x.line_count, reverse=True)
    over_fns: List[Dict[str, Any]] = []
    for m in items:
        for fn in m.oversized_functions:
            over_fns.append({"module": m.rel_path, "func": fn})
    return {
        "total_modules": len(items),
        "total_lines": sum(m.line_count for m in items),
        "oversized_modules": over_mods,
        "oversized_functions": over_fns,
    }
