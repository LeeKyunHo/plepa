"""
scripts/extract_censor_seg_dataset.py
8085 모바일 검수 뷰어 등에서 누적된 검열본(ground_truth)과 무검열 원본(_origin) 간의
픽셀 차분(Diff)을 계산하여, 전용 YOLO-seg 학습용 이미지·폴리곤 라벨(.txt) 데이터셋을 자동 추출합니다.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
from typing import Dict, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

IMAGE_EXTS = {".webp", ".png", ".jpg", ".jpeg"}


def _to_rgb_array(img_or_arr: Union[Image.Image, np.ndarray]) -> np.ndarray:
    """PIL Image 또는 NumPy 배열을 `(H, W, 3)` RGB uint8 배열로 정규화합니다."""
    if isinstance(img_or_arr, np.ndarray):
        if img_or_arr.ndim == 2:
            return cv2.cvtColor(img_or_arr, cv2.COLOR_GRAY2RGB)
        if img_or_arr.shape[2] == 4:
            return img_or_arr[:, :, :3]
        return img_or_arr.astype(np.uint8, copy=False)
    return np.array(img_or_arr.convert("RGB"), dtype=np.uint8)


def extract_yolo_seg_polygons_from_diff(
    origin_rgb: Union[Image.Image, np.ndarray],
    censored_rgb: Union[Image.Image, np.ndarray],
    class_id: int = 0,
    diff_thresh: int = 18,
    min_area_ratio: float = 0.0003,
) -> Tuple[np.ndarray, List[str]]:
    """
    무검열 원본(`origin_rgb`)과 검열본(`censored_rgb`) 간의 픽셀 차이로부터
    이진 검열 마스크(`uint8`, 0/255)와 정규화된 YOLO-seg 폴리곤 라인 리스트를 추출합니다.
    """
    orig_arr = _to_rgb_array(origin_rgb)
    cens_arr = _to_rgb_array(censored_rgb)
    h, w = orig_arr.shape[:2]
    if h == 0 or w == 0:
        return np.zeros((0, 0), dtype=np.uint8), []

    if cens_arr.shape[:2] != (h, w):
        cens_arr = cv2.resize(cens_arr, (w, h), interpolation=cv2.INTER_LINEAR)

    diff = np.abs(cens_arr.astype(np.int16) - orig_arr.astype(np.int16))
    max_diff = diff.max(axis=2)
    raw_mask = (max_diff > int(diff_thresh)).astype(np.uint8) * 255

    # 미세 압축 오차 제거 및 내부 구멍 메움
    k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    cleaned = cv2.morphologyEx(raw_mask, cv2.MORPH_OPEN, k_open, iterations=1)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, k_close, iterations=1)

    contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = max(24.0, float(h * w) * float(min_area_ratio))

    final_mask = np.zeros((h, w), dtype=np.uint8)
    yolo_lines: List[str] = []

    for cnt in contours:
        if cv2.contourArea(cnt) < min_area:
            continue
        eps = max(1.0, 0.004 * cv2.arcLength(cnt, True))
        approx = cv2.approxPolyDP(cnt, eps, True)
        pts = approx.reshape(-1, 2) if len(approx) >= 3 else cnt.reshape(-1, 2)
        if len(pts) < 3:
            continue

        cv2.drawContours(final_mask, [cnt], -1, 255, -1)
        coords: List[str] = []
        for x, y in pts:
            nx = min(1.0, max(0.0, float(x) / float(w)))
            ny = min(1.0, max(0.0, float(y) / float(h)))
            coords.append(f"{nx:.6f} {ny:.6f}")
        yolo_lines.append(f"{int(class_id)} " + " ".join(coords))

    return final_mask, yolo_lines


def _index_origin_files(projects_dir: Path) -> Tuple[Dict[Tuple[str, str], Path], Dict[str, Path]]:
    """`projects/{roster}/assets/{char}_origin` 하위의 무검열 원본을 `(char, filename)` 및 `filename`으로 인덱싱합니다."""
    by_char_name: Dict[Tuple[str, str], Path] = {}
    by_name: Dict[str, Path] = {}
    if not projects_dir.exists():
        return by_char_name, by_name

    for roster_dir in sorted(projects_dir.iterdir()):
        assets_dir = roster_dir / "assets"
        if not assets_dir.is_dir():
            continue
        for sub in sorted(assets_dir.iterdir()):
            if not sub.is_dir():
                continue
            if sub.name.endswith("_origin"):
                char_code = sub.name[: -len("_origin")].lower()
                search_root = sub
            elif (sub / "_origin").is_dir():
                char_code = sub.name.lower()
                search_root = sub / "_origin"
            else:
                continue

            for f in search_root.rglob("*"):
                if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
                    by_char_name.setdefault((char_code, f.name), f)
                    by_name.setdefault(f.name, f)
    return by_char_name, by_name


def _find_matching_origin(
    gt_file: Path,
    gt_dir: Path,
    by_char_name: Dict[Tuple[str, str], Path],
    by_name: Dict[str, Path],
) -> Optional[Path]:
    """ground_truth 파일에 대응하는 `_origin` 무검열 원본 파일을 탐색합니다."""
    rel_parts = gt_file.relative_to(gt_dir).parts
    char_candidates: List[str] = []
    if len(rel_parts) >= 2:
        char_candidates.append(rel_parts[0].lower())
    stem_prefix = gt_file.stem.split("_")[0].lower()
    if stem_prefix:
        char_candidates.append(stem_prefix)

    for c_code in char_candidates:
        hit = by_char_name.get((c_code, gt_file.name))
        if hit is not None:
            return hit
    return by_name.get(gt_file.name)


def build_yolo_seg_dataset(
    gt_dir: Path,
    projects_dir: Path,
    out_dir: Path,
    class_id: int = 0,
    diff_thresh: int = 18,
) -> Dict[str, int]:
    """ground_truth 검열본과 `_origin` 원본 쌍에서 YOLO-seg 학습 데이터셋을 일괄 생성합니다."""
    images_dir = out_dir / "images"
    labels_dir = out_dir / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    yaml_path = out_dir / "data.yaml"
    if not yaml_path.exists():
        yaml_path.write_text(
            f"path: {out_dir.resolve().as_posix()}\n"
            "train: images\n"
            "val: images\n"
            "names:\n"
            f"  {int(class_id)}: genital\n",
            encoding="utf-8",
        )

    if not gt_dir.exists():
        return {"total_gt": 0, "matched": 0, "processed": 0, "skipped_empty": 0}

    gt_files = sorted(
        f for f in gt_dir.rglob("*") if f.is_file() and f.suffix.lower() in IMAGE_EXTS
    )
    if not gt_files:
        return {"total_gt": 0, "matched": 0, "processed": 0, "skipped_empty": 0}

    by_char_name, by_name = _index_origin_files(projects_dir)
    matched = 0
    processed = 0
    skipped_empty = 0

    for gt_file in gt_files:
        origin_file = _find_matching_origin(gt_file, gt_dir, by_char_name, by_name)
        if origin_file is None:
            continue
        matched += 1

        with Image.open(origin_file) as orig_im, Image.open(gt_file) as cens_im:
            _, yolo_lines = extract_yolo_seg_polygons_from_diff(
                orig_im,
                cens_im,
                class_id=class_id,
                diff_thresh=diff_thresh,
            )

        if not yolo_lines:
            skipped_empty += 1
            continue

        rel_stem = "_".join(gt_file.relative_to(gt_dir).with_suffix("").parts)
        dst_img = images_dir / f"{rel_stem}{origin_file.suffix.lower()}"
        dst_lbl = labels_dir / f"{rel_stem}.txt"
        shutil.copy2(origin_file, dst_img)
        dst_lbl.write_text("\n".join(yolo_lines) + "\n", encoding="utf-8")
        processed += 1

    return {
        "total_gt": len(gt_files),
        "matched": matched,
        "processed": processed,
        "skipped_empty": skipped_empty,
    }


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="수작업/덧칠 검열본과 무검열 원본 차분(Diff) 기반 YOLO-seg 데이터셋 자동 추출기"
    )
    parser.add_argument(
        "--gt-dir",
        type=Path,
        default=ROOT / "output" / "benchmarks" / "ground_truth",
        help="정답 검열본(ground_truth) 디렉토리",
    )
    parser.add_argument(
        "--projects-dir",
        type=Path,
        default=ROOT / "projects",
        help="무검열 원본(_origin)을 탐색할 projects 루트 디렉토리",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "output" / "censor_seg_dataset",
        help="YOLO-seg 데이터셋 출력 디렉토리 (images/, labels/ 생성)",
    )
    parser.add_argument("--class-id", type=int, default=0, help="YOLO-seg 클래스 ID (기본: 0)")
    parser.add_argument("--diff-thresh", type=int, default=18, help="픽셀 차분 임계값 (기본: 18)")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = create_parser().parse_args(argv)
    stats = build_yolo_seg_dataset(
        gt_dir=args.gt_dir,
        projects_dir=args.projects_dir,
        out_dir=args.out_dir,
        class_id=args.class_id,
        diff_thresh=args.diff_thresh,
    )
    print(
        f"[YOLO-seg Extractor] {stats['processed']} pairs processed "
        f"(total_gt={stats['total_gt']}, matched={stats['matched']}, skipped_empty={stats['skipped_empty']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
