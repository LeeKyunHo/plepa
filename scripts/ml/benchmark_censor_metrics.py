"""
scripts/benchmark_censor_metrics.py
Phase P0 / P4 정량 벤치마크 평가기:
1. Ground Truth 쌍(`02_h_scenes` 및 `kiro/spy` Hold-out) 대비 Mask IoU / Boundary IoU 실측
2. `output/test_batch_c4` 20장 기준 미탐(FN), 다중/하단 오탐(FP), 장당 평균 처리 시간(sec/img) 실측
3. 옵션 지정 시 `white_p0` 비교 에셋 저장 및 이전 JSON 베이스라인과 A/B 비교표 출력
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import plepa_engine.censor as censor
from scripts.ml.extract_censor_seg_dataset import (
    _find_matching_origin,
    _index_origin_files,
    collect_spy_white_pairs,
)


IMAGE_EXTS = {".webp", ".png", ".jpg", ".jpeg"}


@dataclass
class PairEvalItem:
    """단일 원본-정답 쌍 평가 결과."""

    name: str
    detected_count: int
    mask_iou: float
    boundary_iou: float
    elapsed_sec: float


def compute_mask_iou(pred_mask: np.ndarray, gt_mask: np.ndarray) -> float:
    """두 이진 마스크(`> 0`) 간의 IoU를 계산합니다."""
    pred_b = pred_mask > 0
    gt_b = gt_mask > 0
    inter = int(np.count_nonzero(pred_b & gt_b))
    union = int(np.count_nonzero(pred_b | gt_b))
    if union == 0:
        return 1.0 if not np.any(pred_b) and not np.any(gt_b) else 0.0
    return float(inter) / float(union)


def _extract_boundary_band(mask_bool: np.ndarray, band_px: int) -> np.ndarray:
    """마스크 외곽선으로부터 내측 `band_px` 두께의 경계 띠를 추출합니다."""
    if not np.any(mask_bool):
        return mask_bool
    h, w = mask_bool.shape[:2]
    pad = band_px + 1
    padded = np.pad(mask_bool.astype(np.uint8), ((pad, pad), (pad, pad)), mode="constant", constant_values=0)
    k = 2 * band_px + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    eroded = cv2.erode(padded, kernel, iterations=1)
    eroded_crop = eroded[pad : pad + h, pad : pad + w] > 0
    return mask_bool & (~eroded_crop)


def compute_boundary_iou(
    pred_mask: np.ndarray,
    gt_mask: np.ndarray,
    dilation_ratio: float = 0.005,
) -> float:
    """Cheng et al. 정의 기반 Boundary IoU를 계산합니다 (대각선 비례 2~8px 경계 띠)."""
    h, w = gt_mask.shape[:2]
    if h == 0 or w == 0:
        return 0.0
    band_px = max(2, min(8, int(round(math.hypot(h, w) * dilation_ratio))))
    pred_band = _extract_boundary_band(pred_mask > 0, band_px)
    gt_band = _extract_boundary_band(gt_mask > 0, band_px)
    inter = int(np.count_nonzero(pred_band & gt_band))
    union = int(np.count_nonzero(pred_band | gt_band))
    if union == 0:
        return 1.0 if not np.any(pred_band) and not np.any(gt_band) else 0.0
    return float(inter) / float(union)


def extract_diff_mask(
    origin_img: Image.Image,
    modified_img: Image.Image,
    diff_thresh: int = 20,
) -> np.ndarray:
    """원본과 수정본의 RGB 픽셀 차분에서 정제된 이진 마스크(`0/255`)를 추출합니다."""
    orig_arr = np.array(origin_img.convert("RGB"), dtype=np.int16)
    mod_arr = np.array(modified_img.convert("RGB"), dtype=np.int16)
    if orig_arr.shape != mod_arr.shape:
        mod_arr = np.array(modified_img.convert("RGB").resize(origin_img.size, Image.Resampling.BILINEAR), dtype=np.int16)

    h, w = orig_arr.shape[:2]
    max_diff = np.abs(mod_arr - orig_arr).max(axis=2)
    raw = (max_diff > int(diff_thresh)).astype(np.uint8) * 255
    k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    cleaned = cv2.morphologyEx(raw, cv2.MORPH_OPEN, k_open, iterations=1)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, k_close, iterations=1)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(cleaned, connectivity=8)
    min_area = max(24.0, float(h * w) * 0.00025)
    out = np.zeros((h, w), dtype=np.uint8)
    for idx in range(1, num_labels):
        if stats[idx, cv2.CC_STAT_AREA] >= min_area:
            out[labels == idx] = 255
    return out


def collect_02_h_pairs(gt_dir: Path, projects_dir: Path) -> List[Tuple[Path, Path]]:
    """`output/benchmarks/ground_truth` 정답셋과 일치하는 `_origin` 원본 쌍 목록을 수집합니다."""
    if not gt_dir.exists():
        return []
    by_char, by_name = _index_origin_files(projects_dir)
    pairs: List[Tuple[Path, Path]] = []
    gt_files = sorted(
        f for f in gt_dir.rglob("*") if f.is_file() and f.suffix.lower() in IMAGE_EXTS
    )
    for gt_file in gt_files:
        orig_file = _find_matching_origin(gt_file, gt_dir, by_char, by_name)
        if orig_file is not None and orig_file.is_file():
            pairs.append((orig_file, gt_file))
    return pairs


def collect_spy_holdout_white_pairs(
    spy_assets_dir: Path,
    per_char_limit: int = 4,
) -> List[Tuple[Path, Path]]:
    """`kiro/projects/spy/assets`에서 캐릭터별 흰색 실루엣 Hold-out 정답 쌍(뒤쪽 N개)을 결정론적으로 추출합니다."""
    if not spy_assets_dir.exists() or per_char_limit <= 0:
        return []
    _, holdout_pairs = collect_spy_white_pairs(spy_assets_dir, holdout_per_char=per_char_limit)
    return holdout_pairs


def _parse_pose_and_roster(path: Path, default_roster: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    parts = path.stem.split("_")
    pose_code = parts[1] if len(parts) > 1 and parts[1].isdigit() else None
    roster = default_roster
    for part in reversed(path.parts):
        if part in ("campus", "oto", "spy", "school", "maid", "don", "hey", "man"):
            roster = part
            break
    return pose_code, roster


def evaluate_pairs(
    pairs: Sequence[Tuple[Path, Path]],
    style: str = "white_silhouette",
) -> Dict[str, Any]:
    """(원본, 정답) 쌍 목록에 대해 Mask IoU, Boundary IoU, 탐지율 및 속도를 측정합니다."""
    items: List[PairEvalItem] = []
    for orig_path, gt_path in pairs:
        with Image.open(orig_path) as im_o, Image.open(gt_path) as im_g:
            orig_rgb = im_o.convert("RGB")
            gt_rgb = im_g.convert("RGB")
            gt_mask = extract_diff_mask(orig_rgb, gt_rgb, diff_thresh=20)
            if int(np.count_nonzero(gt_mask)) == 0:
                continue

            pose_code, roster = _parse_pose_and_roster(orig_path)
            t0 = time.perf_counter()
            pred_img, det_count = censor.censor_image(
                orig_rgb,
                style=style,
                targets=("penis",),
                pose_code=pose_code,
                roster=roster,
                enable_anchor_fallback=False,
            )
            elapsed = time.perf_counter() - t0
            pred_mask = extract_diff_mask(orig_rgb, pred_img, diff_thresh=18)

            items.append(
                PairEvalItem(
                    name=gt_path.name,
                    detected_count=int(det_count),
                    mask_iou=round(compute_mask_iou(pred_mask, gt_mask), 4),
                    boundary_iou=round(compute_boundary_iou(pred_mask, gt_mask), 4),
                    elapsed_sec=round(elapsed, 3),
                )
            )

    n = len(items)
    if n == 0:
        return {"count": 0, "mean_mask_iou": 0.0, "mean_boundary_iou": 0.0, "recall_nonzero": 0, "avg_sec": 0.0, "items": []}
    return {
        "count": n,
        "mean_mask_iou": round(sum(x.mask_iou for x in items) / n, 4),
        "mean_boundary_iou": round(sum(x.boundary_iou for x in items) / n, 4),
        "recall_nonzero": sum(1 for x in items if x.detected_count > 0),
        "avg_sec": round(sum(x.elapsed_sec for x in items) / n, 3),
        "items": [asdict(x) for x in items],
    }


def evaluate_test_c4(
    test_c4_dir: Path,
    style: str = "white_silhouette",
    output_suffix: Optional[str] = None,
) -> Dict[str, Any]:
    """`output/test_batch_c4` 20장의 미탐(FN), 다중/하단 오탐(FP), 처리 속도를 측정하고 선택적으로 출력을 저장합니다."""
    origin_files = sorted(test_c4_dir.rglob("*_origin/02_h_scenes/*.webp"))
    records: List[Dict[str, Any]] = []

    for orig_path in origin_files:
        rel_char_dir = orig_path.parent.parent.name  # e.g., kei_origin
        char_code = rel_char_dir[: -len("_origin")]
        roster_dir = orig_path.parent.parent.parent
        roster = roster_dir.name
        pose_code, _ = _parse_pose_and_roster(orig_path, default_roster=roster)
        pose_cat = censor.get_pose_category(pose_code, roster=roster) if pose_code else None

        with Image.open(orig_path) as im_o:
            orig_rgb = im_o.convert("RGB")
            skin_np = censor.get_skin_mask(np.array(orig_rgb))
            t0 = time.perf_counter()
            cands, custom_seg_mask, fallback_boxes, yolo_prior_masks, context_boxes = censor._resolve_hybrid_targets_with_priors(
                orig_rgb,
                targets=("penis",),
                min_confidence=0.16,
                pose_code=pose_code,
                roster=roster,
                skin_np=skin_np,
                pose_cat=pose_cat,
            )
            if cands:
                cens_rgb = censor._render_censored_style(
                    orig_rgb,
                    cands,
                    style=style,
                    skin_np=skin_np,
                    pose_cat=pose_cat,
                    custom_seg_mask=custom_seg_mask,
                    fallback_boxes=fallback_boxes,
                    yolo_prior_masks=yolo_prior_masks,
                    context_boxes=context_boxes,
                )
            else:
                cens_rgb = orig_rgb
            elapsed = time.perf_counter() - t0

            if output_suffix:
                out_path = roster_dir / f"{char_code}_{output_suffix}" / "02_h_scenes" / orig_path.name
                out_path.parent.mkdir(parents=True, exist_ok=True)
                cens_rgb.save(out_path, "WEBP", quality=92)

            h = orig_rgb.height
            boxes_info = [
                {
                    "box": [int(v) for v in b],
                    "score": round(float(s), 3),
                    "y2_ratio": round(float(b[3]) / float(max(1, h)), 3),
                }
                for b, _, s in cands
            ]
            has_bottom_secondary = len(cands) >= 2 and any(b[3] >= h * 0.85 for b, _, _ in cands)
            records.append(
                {
                    "file": orig_path.name,
                    "roster": roster,
                    "char": char_code,
                    "detected_count": len(cands),
                    "has_bottom_secondary": has_bottom_secondary,
                    "elapsed_sec": round(elapsed, 3),
                    "boxes": boxes_info,
                }
            )

    n = len(records)
    fn_files = [r["file"] for r in records if r["detected_count"] == 0]
    multi_files = [r["file"] for r in records if r["detected_count"] >= 2]
    bottom_fp_files = [r["file"] for r in records if r["has_bottom_secondary"]]
    return {
        "count": n,
        "fn_count": len(fn_files),
        "fn_files": fn_files,
        "multi_box_count": len(multi_files),
        "multi_box_files": multi_files,
        "bottom_secondary_count": len(bottom_fp_files),
        "bottom_secondary_files": bottom_fp_files,
        "avg_sec": round(sum(r["elapsed_sec"] for r in records) / max(1, n), 3),
        "records": records,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PLEPA 검열 엔진 정량 벤치마크 평가기")
    parser.add_argument("--label", default="run", help="결과 식별 라벨 (예: C7, P0)")
    parser.add_argument("--gt-dir", type=Path, default=ROOT / "output" / "benchmarks" / "ground_truth")
    parser.add_argument("--projects-dir", type=Path, default=ROOT / "projects")
    parser.add_argument("--spy-assets-dir", type=Path, default=ROOT.parent / "kiro" / "projects" / "spy" / "assets")
    parser.add_argument("--spy-per-char", type=int, default=4, help="캐릭터당 spy Hold-out 쌍 개수")
    parser.add_argument("--test-c4-dir", type=Path, default=ROOT / "output" / "test_batch_c4")
    parser.add_argument("--save-c4-suffix", default="", help="지정 시 test_c4/<char>_<suffix>/02_h_scenes에 출력 저장")
    parser.add_argument("--out-json", type=Path, default=None, help="측정 결과 JSON 저장 경로")
    parser.add_argument("--compare-json", type=Path, default=None, help="비교할 이전 기준 JSON 경로")
    return parser.parse_args(argv)


def _print_summary(report: Dict[str, Any], baseline: Optional[Dict[str, Any]] = None) -> None:
    label = report["label"]
    print(f"\n=== Quantitative Censor Benchmark [{label}] ===")
    for sec in ("02_h_scenes", "spy_holdout"):
        cur = report.get(sec, {})
        base = baseline.get(sec, {}) if baseline else None
        if cur.get("count", 0) == 0:
            continue
        iou_diff = f" ({cur['mean_mask_iou'] - base['mean_mask_iou']:+.4f})" if base else ""
        biou_diff = f" ({cur['mean_boundary_iou'] - base['mean_boundary_iou']:+.4f})" if base else ""
        print(
            f"  [{sec}] N={cur['count']}, recall={cur['recall_nonzero']}/{cur['count']}, "
            f"Mask IoU={cur['mean_mask_iou']:.4f}{iou_diff}, "
            f"Boundary IoU={cur['mean_boundary_iou']:.4f}{biou_diff}, "
            f"avg_sec={cur['avg_sec']:.3f}s"
        )
    c4 = report.get("test_c4", {})
    base_c4 = baseline.get("test_c4", {}) if baseline else None
    if c4.get("count", 0) > 0:
        fn_d = f" ({c4['fn_count'] - base_c4['fn_count']:+d})" if base_c4 else ""
        mb_d = f" ({c4['multi_box_count'] - base_c4['multi_box_count']:+d})" if base_c4 else ""
        bfp_d = f" ({c4['bottom_secondary_count'] - base_c4['bottom_secondary_count']:+d})" if base_c4 else ""
        print(
            f"  [test_c4] N={c4['count']}, FN={c4['fn_count']}{fn_d} {c4['fn_files']}, "
            f"MultiBox={c4['multi_box_count']}{mb_d} {c4['multi_box_files']}, "
            f"BottomFP={c4['bottom_secondary_count']}{bfp_d} {c4['bottom_secondary_files']}, "
            f"avg_sec={c4['avg_sec']:.3f}s"
        )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    pairs_02 = collect_02_h_pairs(args.gt_dir, args.projects_dir)
    pairs_spy = collect_spy_holdout_white_pairs(args.spy_assets_dir, per_char_limit=args.spy_per_char)

    report: Dict[str, Any] = {
        "label": args.label,
        "02_h_scenes": evaluate_pairs(pairs_02),
        "spy_holdout": evaluate_pairs(pairs_spy),
        "test_c4": evaluate_test_c4(
            args.test_c4_dir,
            output_suffix=(args.save_c4_suffix.strip() or None),
        ),
    }

    if args.out_json is not None:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    baseline = None
    if args.compare_json is not None and args.compare_json.is_file():
        baseline = json.loads(args.compare_json.read_text(encoding="utf-8"))

    _print_summary(report, baseline=baseline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
