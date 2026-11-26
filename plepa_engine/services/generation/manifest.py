"""
plepa_engine.services.generation.manifest
배치 실행 매니페스트(`_batch_manifest.json`) 시드/QC 상태 로드 및 원자적 증분 저장 헬퍼.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from plepa_engine.models import CharacterConfig, GenerationResult

logger = logging.getLogger(__name__)


def load_manifest_state(output_dir: Path) -> Tuple[Dict[str, Any], Set[str]]:
    """기존 `_batch_manifest.json`에서 포즈 코드별 골든 시드와 QC 실패 이력 집합을 로드합니다."""
    existing_manifest_seeds: Dict[str, Any] = {}
    existing_manifest_qc_failed: Set[str] = set()
    manifest_file = output_dir / "_batch_manifest.json"
    if not manifest_file.exists():
        return existing_manifest_seeds, existing_manifest_qc_failed

    try:
        with open(manifest_file, "r", encoding="utf-8") as mf:
            m_data = json.load(mf)
        for itm in m_data.get("items", []):
            c_str = str(itm.get("code", "")).strip()
            if not c_str:
                continue
            if itm.get("seed") is not None:
                existing_manifest_seeds[c_str] = itm["seed"]
            if itm.get("qc_passed") is False:
                existing_manifest_qc_failed.add(c_str)
    except Exception:
        pass
    return existing_manifest_seeds, existing_manifest_qc_failed


def save_batch_manifest_atomic(
    output_dir: Path,
    char: CharacterConfig,
    roster: str,
    params: Any,
    results: List[GenerationResult],
) -> None:
    """배치 실행 기록을 `_batch_manifest.json`에 원자적으로 병합·저장합니다."""
    if not results or getattr(params, "dry_run", False):
        return

    manifest_path = output_dir / "_batch_manifest.json"
    temp_path = output_dir / f"_batch_manifest_{uuid.uuid4().hex[:6]}.tmp.json"

    existing_items: Dict[str, Dict[str, Any]] = {}
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                old_data = json.load(f)
            for item in old_data.get("items", []):
                if "code" in item:
                    existing_items[str(item["code"]).strip()] = item
        except Exception as exc:
            logger.warning("기존 배치 매니페스트 로드 실패 (%s): %s", manifest_path, exc)

    for r in results:
        t = r.target
        code_key = str(t.code).strip()
        existing_items[code_key] = {
            "code": t.code,
            "label": t.label,
            "section": t.section,
            "output_filename": getattr(t, "output_filename", ""),
            "success": r.success,
            "skipped": getattr(r, "skipped", False),
            "duration_sec": round(r.duration_sec, 2),
            "error_message": r.error_message,
            "assembled_prompt": getattr(t, "assembled_prompt", ""),
            "seed": getattr(t, "seed", None),
            "qc_passed": getattr(r, "qc_passed", True),
            "qc_reason": getattr(r, "qc_reason", None),
            "retries": getattr(r, "retries", 0),
        }

    def _sort_key(k: str) -> Tuple[int, int, str]:
        try:
            return (0, int(k), "")
        except ValueError:
            return (1, 0, k)

    items = [existing_items[c] for c in sorted(existing_items.keys(), key=_sort_key)]
    data = {
        "prefix": char.prefix,
        "character_name": char.name,
        "roster": roster,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "engine": params.engine,
        "checkpoint": getattr(params, "ckpt", None) or getattr(params, "sdxl_ckpt", None) or "default",
        "total_count": len(items),
        "success_count": sum(1 for item in items if item.get("success")),
        "failed_count": sum(1 for item in items if not item.get("success")),
        "qc_defect_count": sum(1 for item in items if not item.get("qc_passed", True)),
        "items": items,
    }

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        temp_path.replace(manifest_path)
    except Exception as e:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        print(f"  [경고] 배치 매니페스트 저장 실패: {e}")
