"""
tests/snapshot_prompts.py
프롬프트 조립 결과 스냅샷 생성/비교 도구 (리팩터링 회귀 방지용).

전체 로스터 x 전체 캐릭터 x 전체 포즈 x (SDXL, FLUX) 조합의 최종 프롬프트를 수집하여
gzip JSON 스냅샷으로 저장하고, 이후 코드 변경 시 한 글자라도 달라지면 차이를 보고합니다.

사용법:
    python tests/snapshot_prompts.py --update   # 기준 스냅샷 갱신
    python tests/snapshot_prompts.py            # 현재 결과와 기준 스냅샷 비교
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flux_batch_generator import load_background_preset, load_pose_db  # noqa: E402
from plepa_engine.config import PROJECTS_DIR  # noqa: E402
from plepa_engine.models import CharacterConfig  # noqa: E402
from plepa_engine.prompt_builder import assemble_flux_prompt, assemble_sdxl_prompt  # noqa: E402

SNAPSHOT_PATH = ROOT / "tests" / "snapshots" / "prompt_snapshot.json.gz"


def iter_characters() -> List[Tuple[str, CharacterConfig]]:
    """projects/*/characters/*.json 전체를 (roster, CharacterConfig) 목록으로 반환."""
    chars: List[Tuple[str, CharacterConfig]] = []
    for roster_dir in sorted(p for p in PROJECTS_DIR.iterdir() if p.is_dir()):
        char_dir = roster_dir / "characters"
        if not char_dir.is_dir():
            continue
        for path in sorted(char_dir.glob("*.json")):
            with open(path, "r", encoding="utf-8") as f:
                chars.append((roster_dir.name, CharacterConfig.from_dict(json.load(f), file_path=path)))
    return chars


def build_snapshot() -> Dict[str, Dict[str, object]]:
    """현재 코드 기준 전체 프롬프트 조립 결과 수집."""
    sdxl_db = load_pose_db(engine="sdxl")
    flux_db = load_pose_db(engine="flux")
    snapshot: Dict[str, Dict[str, object]] = {}

    for roster, char in iter_characters():
        bg = load_background_preset(roster, key="default")
        for code in sorted(sdxl_db.keys()):
            pos, neg, nude = assemble_sdxl_prompt(char, sdxl_db[code], bg_prompt=bg)
            snapshot[f"{roster}/{char.prefix}/sdxl/{code}"] = {"pos": pos, "neg": neg, "nude": nude}
        for code in sorted(flux_db.keys()):
            prompt, nude = assemble_flux_prompt(char, flux_db[code], bg_prompt=bg)
            snapshot[f"{roster}/{char.prefix}/flux/{code}"] = {"pos": prompt, "nude": nude}
    return snapshot


def save_snapshot(data: Dict[str, Dict[str, object]], path: Path = SNAPSHOT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, sort_keys=True)


def load_snapshot(path: Path = SNAPSHOT_PATH) -> Dict[str, Dict[str, object]]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def diff_snapshots(
    baseline: Dict[str, Dict[str, object]], current: Dict[str, Dict[str, object]]
) -> List[str]:
    """기준 대비 변경/추가/삭제 항목을 사람이 읽을 수 있는 문자열 목록으로 반환."""
    problems: List[str] = []
    for key in sorted(set(baseline) - set(current)):
        problems.append(f"[삭제됨] {key}")
    for key in sorted(set(current) - set(baseline)):
        problems.append(f"[추가됨] {key}")
    for key in sorted(set(baseline) & set(current)):
        if baseline[key] != current[key]:
            for field in sorted(set(baseline[key]) | set(current[key])):
                b, c = baseline[key].get(field), current[key].get(field)
                if b != c:
                    problems.append(f"[변경됨] {key} :: {field}\n    기준: {b}\n    현재: {c}")
    return problems


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="플에파 프롬프트 스냅샷 생성/비교")
    parser.add_argument("--update", action="store_true", help="현재 결과로 기준 스냅샷 갱신")
    args = parser.parse_args(argv)

    current = build_snapshot()
    if args.update or not SNAPSHOT_PATH.exists():
        save_snapshot(current)
        print(f"[스냅샷 저장] {len(current)}개 항목 → {SNAPSHOT_PATH}")
        return 0

    problems = diff_snapshots(load_snapshot(), current)
    if problems:
        print(f"[FAIL] 프롬프트 스냅샷 불일치 {len(problems)}건")
        for p in problems[:30]:
            print("  " + p)
        return 1
    print(f"[PASS] 프롬프트 스냅샷 {len(current)}개 항목 완전 일치")
    return 0


if __name__ == "__main__":
    sys.exit(main())
