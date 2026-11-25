"""
plepa_engine.services.novelchat_exporter
노벨챗(NovelChat) 에셋 자동 호출어 태깅, 500장 예산 트리밍, 5MB 방어 패키징 서비스.
원본 에셋(projects/{roster}/assets/)은 절대 수정하지 않고 dist/novelchat/{roster}/로 내보낸다.
"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image

from plepa_engine.config import DATA_DIR, PROJECTS_DIR, ROOT_DIR

NOVELCHAT_LIMITS: Dict[str, int] = {
    "MAX_TOTAL_ASSETS": 500,
    "MAX_FILE_BYTES": 5 * 1024 * 1024,
    "ASSET_TRIGGER_MAX_LEN": 30,  # UNVERIFIED: 개별 호출어 최대 길이 방어 경고선
}

DEFAULT_POOL_CONFIG = DATA_DIR / "novelchat_pose_pools.json"


@dataclass
class AssetCandidate:
    """패키징 대상 단일 에셋 메타데이터."""

    src_path: Path
    prefix: str
    code: str
    orig_label: str
    pool: str
    priority: int
    is_adult: bool
    future_tier: str
    size_bytes: int
    is_default_rec: bool = False

    @property
    def target_filename(self) -> str:
        return f"{self.pool}_{self.code}.webp"


def load_pose_pools(pool_config: Optional[Path] = None) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, int]]:
    """novelchat_pose_pools.json에서 코드별 호출어 풀 및 우선순위 맵을 로드한다."""
    cfg_path = pool_config or DEFAULT_POOL_CONFIG
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    pools = raw.get("pools", {})
    overrides = {str(k): int(v) for k, v in raw.get("code_priority_overrides", {}).items()}

    code_map: Dict[str, Dict[str, Any]] = {}
    for pool_name, info in pools.items():
        if "_" in pool_name:
            raise ValueError(f"호출어 풀 이름에 언더스코어('_')를 사용할 수 없습니다: {pool_name}")
        for code in info.get("codes", []):
            code_s = str(code).strip()
            code_map[code_s] = {
                "pool": pool_name,
                "priority": overrides.get(code_s, int(info.get("priority", 2))),
                "is_adult": bool(info.get("is_adult", False)),
                "future_tier": str(info.get("future_tier", "Bronze")),
            }
    return code_map, overrides


def parse_asset_filename(filename: str) -> Optional[Tuple[str, str, str]]:
    """원본 에셋 파일명({prefix}_{code}_{label}.webp)을 파싱한다."""
    stem = Path(filename).stem
    parts = stem.split("_", 2)
    if len(parts) < 3:
        return None
    prefix, code, label = parts[0], parts[1], parts[2]
    if not (re.match(r"^\d{3}$", code) or re.match(r"^[A-Za-z]\d{2,3}$", code)):
        return None
    return prefix, code.upper(), label


def _copy_with_size_guard(src_file: Path, dest_file: Path, max_bytes: int) -> Tuple[int, bool]:
    """원본 무접촉으로 복사하되 5MB 초과 시에만 WebP 품질을 단계 하향한다."""
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    temp_dest = dest_file.parent / f".{dest_file.name}.{uuid.uuid4().hex[:8]}.tmp"
    optimized = False
    try:
        if src_file.stat().st_size <= max_bytes:
            shutil.copy2(src_file, temp_dest)
        else:
            with Image.open(src_file) as im:
                rgb_im = im.convert("RGB")
                for quality in (85, 80, 75, 68, 60):
                    rgb_im.save(temp_dest, format="WEBP", quality=quality, method=4)
                    optimized = True
                    if temp_dest.stat().st_size <= max_bytes:
                        break
        final_size = temp_dest.stat().st_size
        os.replace(temp_dest, dest_file)
        return final_size, optimized
    finally:
        if temp_dest.exists():
            temp_dest.unlink(missing_ok=True)


class NovelchatExporter:
    """노벨챗 6탭 에셋 태깅 및 500장 예산 패키징 서비스."""

    def __init__(self, projects_dir: Optional[Path] = None, root_dir: Optional[Path] = None):
        self.projects_dir = projects_dir or PROJECTS_DIR
        self.root_dir = root_dir or ROOT_DIR

    def collect_candidates(
        self,
        roster: str,
        chars: Optional[Sequence[str]] = None,
        include_adult: bool = False,
        pool_config: Optional[Path] = None,
    ) -> Tuple[List[AssetCandidate], List[str]]:
        """로스터 에셋 디렉토리에서 유효한 패키징 후보를 수집한다."""
        code_map, _ = load_pose_pools(pool_config)
        assets_root = self.projects_dir / roster / "assets"
        if not assets_root.is_dir():
            raise FileNotFoundError(f"로스터 에셋 폴더를 찾을 수 없습니다: {assets_root}")

        char_filter = {c.strip() for c in chars if c.strip()} if chars else None
        candidates: List[AssetCandidate] = []
        warnings: List[str] = []

        for char_dir in sorted(p for p in assets_root.iterdir() if p.is_dir()):
            prefix = char_dir.name
            if (
                prefix.startswith(".")
                or prefix.endswith(("_origin", "_trash", "_censor"))
                or prefix in ("legacy_backups", "censor_backup")
                or (char_filter and prefix not in char_filter)
            ):
                continue
            for webp_file in sorted(char_dir.rglob("*.webp")):
                if any(s in webp_file.parts for s in ("_origin", "_trash", "legacy_backups")) or webp_file.name.startswith("."):
                    continue
                parsed = parse_asset_filename(webp_file.name)
                if not parsed:
                    continue
                _, code, label = parsed
                meta = code_map.get(code)
                if not meta:
                    warnings.append(f"미매핑 코드 스킵: {webp_file.name} (code={code})")
                    continue
                if meta["is_adult"] and not include_adult:
                    continue
                pool = meta["pool"]
                if "_" in pool:
                    raise ValueError(f"호출어에 '_' 포함 불가: {pool}")
                if len(pool) > NOVELCHAT_LIMITS["ASSET_TRIGGER_MAX_LEN"]:
                    warnings.append(f"호출어 길이 경고({len(pool)}자): {pool}")
                candidates.append(
                    AssetCandidate(
                        src_path=webp_file,
                        prefix=prefix,
                        code=code,
                        orig_label=label,
                        pool=pool,
                        priority=meta["priority"],
                        is_adult=meta["is_adult"],
                        future_tier=meta["future_tier"],
                        size_bytes=webp_file.stat().st_size,
                        is_default_rec=(code == "000"),
                    )
                )
        return candidates, warnings

    @staticmethod
    def apply_budget_trim(
        candidates: List[AssetCandidate],
        max_total: int = NOVELCHAT_LIMITS["MAX_TOTAL_ASSETS"],
    ) -> Tuple[List[AssetCandidate], List[AssetCandidate]]:
        """500장 상한 초과 시 캐릭터 균등 + priority 순 + 풀 중복 상한 축소로 트리밍한다."""
        if len(candidates) <= max_total:
            return list(candidates), []

        by_char: Dict[str, List[AssetCandidate]] = {}
        for item in candidates:
            by_char.setdefault(item.prefix, []).append(item)

        num_chars = max(len(by_char), 1)
        per_char_cap = max_total // num_chars
        remainder = max_total % num_chars

        selected: List[AssetCandidate] = []
        excluded: List[AssetCandidate] = []

        for idx, prefix in enumerate(sorted(by_char.keys())):
            items = by_char[prefix]
            # 1차 정렬: priority 오름차순 -> 기본 추천(000) 우선 -> 풀 내 1번째 다양성 우선 -> 코드순
            pool_seen: Dict[str, int] = {}
            ranked: List[Tuple[int, int, int, str, AssetCandidate]] = []
            for it in sorted(items, key=lambda x: (x.priority, not x.is_default_rec, x.code)):
                occ = pool_seen.get(it.pool, 0)
                pool_seen[it.pool] = occ + 1
                ranked.append((it.priority, 0 if it.is_default_rec else 1, occ, it.code, it))

            ranked.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
            quota = per_char_cap + (1 if idx < remainder else 0)
            chosen = [t[4] for t in ranked[:quota]]
            dropped = [t[4] for t in ranked[quota:]]
            selected.extend(chosen)
            excluded.extend(dropped)

        return selected, excluded

    def export_roster(
        self,
        roster: str,
        chars: Optional[Sequence[str]] = None,
        out_dir: Optional[Path] = None,
        include_adult: bool = False,
        max_total: int = NOVELCHAT_LIMITS["MAX_TOTAL_ASSETS"],
        trim_to_limit: bool = False,
        pool_config: Optional[Path] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """로스터 에셋을 노벨챗 규격으로 패키징하고 manifest/csv를 생성한다."""
        candidates, warnings = self.collect_candidates(
            roster=roster, chars=chars, include_adult=include_adult, pool_config=pool_config
        )
        total_found = len(candidates)
        excluded: List[AssetCandidate] = []

        if total_found > max_total:
            if not trim_to_limit:
                raise ValueError(
                    f"에셋 총량({total_found}장)이 노벨챗 상한({max_total}장)을 초과합니다. --trim-to-limit 옵션을 사용하세요."
                )
            selected, excluded = self.apply_budget_trim(candidates, max_total=max_total)
        else:
            selected = candidates

        target_root = out_dir or (self.root_dir / "dist" / "novelchat" / roster)
        pool_counts: Dict[str, Dict[str, int]] = {}
        char_defaults: Dict[str, Optional[str]] = {}
        for item in selected:
            pool_counts.setdefault(item.prefix, {})
            pool_counts[item.prefix][item.pool] = pool_counts[item.prefix].get(item.pool, 0) + 1
            if item.prefix not in char_defaults and item.is_default_rec:
                char_defaults[item.prefix] = item.target_filename
        for prefix in pool_counts:
            if prefix not in char_defaults:
                first = next((x.target_filename for x in selected if x.prefix == prefix and not x.is_adult), None)
                char_defaults[prefix] = first

        optimized_count = 0
        csv_rows: List[Dict[str, Any]] = []
        for item in selected:
            dest_file = target_root / item.prefix / item.target_filename
            final_size = item.size_bytes
            if not dry_run:
                final_size, was_opt = _copy_with_size_guard(
                    item.src_path, dest_file, NOVELCHAT_LIMITS["MAX_FILE_BYTES"]
                )
                if was_opt:
                    optimized_count += 1
            csv_rows.append(
                {
                    "char_prefix": item.prefix,
                    "original_name": item.src_path.name,
                    "upload_name": item.target_filename,
                    "trigger_pool": item.pool,
                    "pool_size": pool_counts[item.prefix][item.pool],
                    "size_kb": round(final_size / 1024, 1),
                    "upload_tier": "Bronze",
                    "future_tier": item.future_tier,
                    "default_recommended": "★" if char_defaults.get(item.prefix) == item.target_filename else "",
                }
            )

        manifest = {
            "roster": roster,
            "total_found": total_found,
            "exported_count": len(selected),
            "excluded_count": len(excluded),
            "max_total": max_total,
            "include_adult": include_adult,
            "characters": {
                prefix: {
                    "default_image": char_defaults.get(prefix),
                    "pools": pools,
                    "total": sum(pools.values()),
                }
                for prefix, pools in sorted(pool_counts.items())
            },
            "excluded_files": [f"{e.prefix}/{e.src_path.name}" for e in excluded],
        }

        if not dry_run:
            target_root.mkdir(parents=True, exist_ok=True)
            (target_root / "upload_manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            with open(target_root / "upload_checklist.csv", "w", encoding="utf-8-sig", newline="") as f:
                fieldnames = [
                    "char_prefix", "original_name", "upload_name", "trigger_pool",
                    "pool_size", "size_kb", "upload_tier", "future_tier", "default_recommended",
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(csv_rows)

        return {
            "manifest": manifest,
            "out_dir": str(target_root),
            "optimized_count": optimized_count,
            "warnings": warnings,
            "dry_run": dry_run,
        }
