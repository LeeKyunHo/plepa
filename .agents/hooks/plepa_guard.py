"""
.agents/hooks/plepa_guard.py
Antigravity PreToolUse 물리 가드레일:
1. 생성 에셋 불가침: projects/*/assets/ 및 *_origin/ 직접 읽기·수정·삭제 차단 (단, pytest/precheck/export_context/audit 등 검증 스크립트는 오탐 없이 허용)
2. 토큰 세이빙: data/legacy/, plepa_engine/legacy/, flux_batch_generator.py, 워크플로우 JSON, 대용량 미디어, 무범위 sdxl_pose_database.json 전문 열람 차단
3. 위험 스크립트: scripts/sync_to_kiro.py 일반 실행 차단 (--force-unsafe 명시 시 제외)
4. 깃 커밋 가이드라인: 민감 어휘 포함 커밋 메시지 차단
"""

from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# 민감 어휘 검사는 파일 평문 오염 방지를 위해 base64 인코딩 목록을 런타임 디코딩하여 사용합니다.
_SENSITIVE_COMMIT_B64 = [
    "7IS57Iqk",  # explicit Korean term
    "67O07KeA",
    "7J6Q7JyE",
    "7Jyg67Cp",
    "7JqU64+E",
    "6rWQ67Cw",
    "7YyM7J207KaI66as",
    "7Y6Y65287LmY7Jik",
    "c2V4",
    "cGVuaXM=",
    "cHVzc3k=",
    "dmFnaW5h",
    "cGFpenVyaQ==",
    "ZmVsbGF0aW8=",
    "Ymxvd2pvYg==",
    "ZG9nZ3lzdHlsZQ==",
    "bWlzc2lvbmFyeQ==",
    "Y3VubmlsaW5ndXM=",
    "bnVkZQ==",
    "bmlwcGxl",
]
_SENSITIVE_TERMS = tuple(base64.b64decode(item).decode("utf-8") for item in _SENSITIVE_COMMIT_B64)

_MEDIA_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".mp4", ".avi"}
_LEGACY_PATH_PREFIXES = ("data/legacy/", "plepa_engine/legacy/", "flux_batch_generator.py")
_BLOCKED_READ_SUBTREES = ("output/", "temp/", "models/", "benchmarks/", "docs/archive/assets/", "docs/archive/benchmarks/")
_FILE_READ_TOOLS = {"read_file", "view_file"}
_FILE_WRITE_TOOLS = {"write_file", "edit_file", "write_to_file", "replace_file_content", "multi_replace_file_content"}

_DESTRUCTIVE_SHELL_RE = re.compile(
    r"(?i)(?:^|\s)(?:remove-item|rm|del|erase|rmdir|rd|move-item|mv|rename-item|ren|copy-item|cp|set-content|out-file)\b"
    r"|(?:\.unlink\s*\(|\.rename\s*\(|\.replace\s*\(|\.write_bytes\s*\(|\.write_text\s*\(|\.read_bytes\s*\()"
    r"|(?:shutil\.(?:rmtree|move|copy2?)|os\.(?:remove|unlink|rename|replace)|Image\.open|cv2\.(?:imread|imwrite))\b"
)
_SAFE_READONLY_TOOL_RE = re.compile(
    r"(?i)(?:\bpytest\b|-m\s+pytest\b|-m\s+plepa_engine\.precheck\b"
    r"|scripts[/\\](?:export_context|validate_genit_work|audit_asset_alignment|audit_sector_assets|benchmark_censor_metrics)\.py"
    r"|^\s*git\s+(?:status|diff|log|show|branch)\b)"
)
_ASSETS_OR_ORIGIN_RE = re.compile(r"(?i)(?:projects[/\\][^/\\;\s\"']+[/\\]assets\b|[^/\\;\s\"']*_origin\b)")


def _repo_roots(payload: Dict[str, Any]) -> List[Path]:
    roots: List[Path] = [Path(__file__).resolve().parents[2]]
    for wp in payload.get("workspacePaths") or []:
        if isinstance(wp, str) and wp.strip():
            roots.append(Path(wp))
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        roots.append(Path(cwd))
    dedup: List[Path] = []
    seen = set()
    for r in roots:
        try:
            res = str(r.resolve()).lower()
        except OSError:
            res = str(r).lower()
        if res not in seen:
            seen.add(res)
            dedup.append(r)
    return dedup


def _to_rel_posix(raw_path: str, roots: Iterable[Path]) -> Tuple[Optional[str], bool]:
    p_str = raw_path.strip().replace("\\", "/")
    if not p_str:
        return None, False
    try:
        candidate = Path(raw_path)
    except Exception:
        return p_str.lower(), False

    if not candidate.is_absolute():
        return p_str.lstrip("./").lower(), True

    try:
        cand_res = candidate.resolve()
    except OSError:
        cand_res = candidate

    for root in roots:
        try:
            rel = cand_res.relative_to(root.resolve())
            return rel.as_posix().lower(), True
        except Exception:
            try:
                root_norm = str(root).replace("\\", "/").rstrip("/").lower()
                cand_norm = str(cand_res).replace("\\", "/").lower()
                if cand_norm.startswith(root_norm + "/"):
                    return cand_norm[len(root_norm) + 1 :], True
            except Exception:
                pass
    return p_str.lower(), False


def _is_protected_asset_path(rel_lower: str) -> bool:
    parts = [p for p in rel_lower.split("/") if p]
    if len(parts) >= 3 and parts[0] == "projects" and parts[2] == "assets":
        return True
    if any(part.endswith("_origin") for part in parts):
        return True
    return False


def _extract_path_arg(args: Dict[str, Any]) -> str:
    for key in ("Path", "TargetFile", "AbsolutePath", "path", "target_file", "file_path"):
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _extract_command_arg(args: Dict[str, Any]) -> str:
    for key in ("CommandLine", "command", "cmd"):
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _allow() -> Dict[str, str]:
    return {"decision": "allow"}


def _deny(reason: str) -> Dict[str, str]:
    return {"decision": "deny", "reason": reason}


def _check_file_tool(tool_name: str, args: Dict[str, Any], roots: List[Path]) -> Dict[str, str]:
    raw_path = _extract_path_arg(args)
    if not raw_path:
        return _allow()

    rel_lower, in_workspace = _to_rel_posix(raw_path, roots)
    if not rel_lower or not in_workspace:
        # 워크스페이스 외부 경로(예: 사용자의 채팅 첨부 이미지)는 허용
        return _allow()

    if _is_protected_asset_path(rel_lower):
        return _deny(
            f"[PLEPA Guard] 생성 에셋 보호 구역({rel_lower})에 대한 직접 읽기·수정·삭제는 금지되어 있습니다. "
            "상태 확인은 precheck 또는 audit_asset_alignment.py를 사용하세요."
        )

    if any(rel_lower == pref or rel_lower.startswith(pref) for pref in _LEGACY_PATH_PREFIXES):
        return _deny(
            f"[PLEPA Guard] 은퇴한 FLUX 레거시 경로({rel_lower})는 열람 및 수정이 금지되어 있습니다 (GEMINI.md 3·10조)."
        )

    if tool_name in _FILE_READ_TOOLS:
        ext = Path(rel_lower).suffix.lower()
        if ext in _MEDIA_EXTS:
            return _deny(f"[PLEPA Guard] 워크스페이스 미디어 파일({rel_lower}) 직접 열람은 토큰 절약 규칙상 금지되어 있습니다.")
        if any(rel_lower.startswith(sub) for sub in _BLOCKED_READ_SUBTREES):
            return _deny(f"[PLEPA Guard] 대용량 산출물/모델/아카이브 미디어 경로({rel_lower}) 열람은 금지되어 있습니다.")
        if ext == ".json" and "workflow" in Path(rel_lower).name:
            return _deny("[PLEPA Guard] ComfyUI 워크플로우 JSON 전문 열람은 금지되어 있습니다. workflow_templates.py를 참조하세요.")
        if rel_lower == "data/sdxl_pose_database.json":
            try:
                start = int(args.get("StartLine"))
                end = int(args.get("EndLine"))
                valid_range = end >= start and (end - start) <= 250
            except (TypeError, ValueError):
                valid_range = False
            if not valid_range:
                return _deny(
                    "[PLEPA Guard] data/sdxl_pose_database.json 전체 열람은 금지되어 있습니다. "
                    "250줄 이하 StartLine/EndLine 범위 지정 또는 Python 키 조회를 사용하세요."
                )

    return _allow()


def _extract_commit_message(segment: str) -> str:
    matches = re.findall(r"""(?:-m|--message)(?:=|\s+)(?:"([^"]*)"|'([^']*)'|(\S+))""", segment)
    return " ".join(a or b or c for a, b, c in matches)


def _check_run_command(args: Dict[str, Any]) -> Dict[str, str]:
    cmd = _extract_command_arg(args)
    if not cmd:
        return _allow()

    segments = [seg.strip() for seg in re.split(r"[;\r\n]+|&&|\|\|", cmd) if seg.strip()]
    for seg in segments:
        seg_low = seg.lower()

        if "sync_to_kiro" in seg_low and "--force-unsafe" not in seg_low:
            return _deny(
                "[PLEPA Guard] scripts/sync_to_kiro.py 실행은 최신 Kiro(Wave 0~4) 파손 방지를 위해 차단되었습니다. "
                "단위 기능별 어댑팅 이식을 사용하세요."
            )

        if re.search(r"\bgit\s+commit\b", seg_low):
            msg = _extract_commit_message(seg)
            msg_low = msg.lower()
            for term in _SENSITIVE_TERMS:
                if term.isascii():
                    hit = bool(re.search(rf"\b{re.escape(term)}\b", msg_low))
                else:
                    hit = term in msg_low
                if hit:
                    return _deny(
                        "[PLEPA Guard] GEMINI.md 2조 위반: 커밋 메시지에 민감 어휘가 포함되어 있습니다. "
                        "사무적이고 기술적인 표현으로 수정하세요."
                    )

        # 안전한 읽기 전용 검증·감사 스크립트 및 git 조회 명령은 오탐 방지
        if _SAFE_READONLY_TOOL_RE.search(seg):
            continue

        if _ASSETS_OR_ORIGIN_RE.search(seg) and _DESTRUCTIVE_SHELL_RE.search(seg):
            return _deny(
                "[PLEPA Guard] 쉘 명령으로 projects/*/assets/ 또는 *_origin/ 파일을 직접 삭제·이동·변경할 수 없습니다."
            )

        if any(p.rstrip("/") in seg_low for p in _LEGACY_PATH_PREFIXES) and re.search(
            r"(?i)\b(?:get-content|cat|type|sed|head|tail|more|less|open\(|read_text|write_text|rm|del|remove-item)\b",
            seg_low,
        ):
            return _deny("[PLEPA Guard] 쉘 명령으로 FLUX 레거시 파일을 직접 열람하거나 수정할 수 없습니다.")

    return _allow()


def evaluate_hook(payload: Dict[str, Any]) -> Dict[str, str]:
    """PreToolUse payload를 평가하여 allow 또는 deny 응답을 반환합니다."""
    if not isinstance(payload, dict):
        return _allow()
    tool_call = payload.get("toolCall") or {}
    tool_name = str(tool_call.get("name") or "").strip().lower()
    args = tool_call.get("args") or {}
    if not isinstance(args, dict):
        return _allow()

    roots = _repo_roots(payload)
    if tool_name in _FILE_READ_TOOLS or tool_name in _FILE_WRITE_TOOLS:
        return _check_file_tool(tool_name, args, roots)
    if tool_name == "run_command":
        return _check_run_command(args)
    return _allow()


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        result = evaluate_hook(payload)
    except Exception:
        result = _allow()
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
