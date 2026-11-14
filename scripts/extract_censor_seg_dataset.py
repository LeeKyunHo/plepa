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

from plepa_engine.censor import get_skin_mask

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


def _mask_to_yolo_polygons(
    mask_bin: np.ndarray,
    class_id: int = 0,
    min_area_ratio: float = 0.0003,
) -> Tuple[np.ndarray, List[str]]:
    """이진 마스크(`0/255`)에서 면적 임계값을 만족하는 외곽 폴리곤과 YOLO-seg 라벨 라인을 추출합니다."""
    if mask_bin.size == 0:
        return np.zeros((0, 0), dtype=np.uint8), []
    h, w = mask_bin.shape[:2]
    if h == 0 or w == 0:
        return np.zeros((0, 0), dtype=np.uint8), []

    contours, _ = cv2.findContours(mask_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = max(24.0, float(h * w) * float(min_area_ratio))

    final_mask = np.zeros((h, w), dtype=np.uint8)
    yolo_lines: List[str] = []

    for cnt in contours:
        if cv2.contourArea(cnt) < min_area:
            continue
        eps = max(1.0, 0.003 * cv2.arcLength(cnt, True))
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


def _inpaint_region_with_skin_tone(
    work_rgb: np.ndarray,
    region_mask: np.ndarray,
    skin_bool: np.ndarray,
    rng: np.random.Generator,
    apply_distractor_style: bool = False,
) -> np.ndarray:
    """지정된 마스크 영역을 다중 해상도 피라미드 인페인팅과 주변 피부 톤·질감 합성으로 자연스럽게 메웁니다."""
    h, w = work_rgb.shape[:2]
    ys, xs = np.nonzero(region_mask > 0)
    if len(xs) == 0:
        return work_rgb

    pad = 24
    x0 = max(0, int(xs.min()) - pad)
    y0 = max(0, int(ys.min()) - pad)
    x1 = min(w, int(xs.max()) + pad + 1)
    y1 = min(h, int(ys.max()) + pad + 1)

    roi_img = work_rgb[y0:y1, x0:x1].copy()
    roi_m = (region_mask[y0:y1, x0:x1] > 0).astype(np.uint8) * 255
    roi_skin = skin_bool[y0:y1, x0:x1]

    k_ring = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31))
    ring_zone = (cv2.dilate(roi_m, k_ring) > 0) & (roi_m == 0)
    ring_skin = ring_zone & roi_skin
    sample_pixels = roi_img[ring_skin]
    if len(sample_pixels) < 20:
        sample_pixels = roi_img[ring_zone]
    if len(sample_pixels) == 0:
        sample_pixels = np.array([[235, 195, 175]], dtype=np.uint8)

    med_rgb = np.median(sample_pixels, axis=0).astype(np.float32)
    std_rgb = np.clip(np.std(sample_pixels, axis=0), 1.5, 10.0).astype(np.float32)

    if not apply_distractor_style:
        # 검은 마스크 경계 영향을 지우기 위해 먼저 주변 피부 중앙 색상으로 초기화한 뒤 NS 인페인팅 수행
        roi_img[roi_m > 0] = np.clip(med_rgb, 0, 255).astype(np.uint8)

    rh, rw = roi_img.shape[:2]
    half_w, half_h = max(1, rw // 2), max(1, rh // 2)
    small_img = cv2.resize(roi_img, (half_w, half_h), interpolation=cv2.INTER_AREA)
    small_m = cv2.resize(roi_m, (half_w, half_h), interpolation=cv2.INTER_NEAREST)
    if np.count_nonzero(small_m) == 0:
        small_m = (cv2.resize(roi_m, (half_w, half_h), interpolation=cv2.INTER_LINEAR) > 0).astype(np.uint8) * 255

    small_bgr = cv2.cvtColor(small_img, cv2.COLOR_RGB2BGR)
    inpainted_small = cv2.inpaint(small_bgr, small_m, 5, cv2.INPAINT_NS)
    inpainted_small_rgb = cv2.cvtColor(inpainted_small, cv2.COLOR_BGR2RGB)
    inpainted_up = cv2.resize(inpainted_small_rgb, (rw, rh), interpolation=cv2.INTER_LINEAR).astype(np.float32)

    # 주변 피부 기본 톤과의 조화 보정 + 미세 피부 질감 노이즈 + 경계 소프트 블렌드
    base_layer = (
        inpainted_up
        if apply_distractor_style
        else (0.72 * inpainted_up + 0.28 * med_rgb[None, None, :])
    )
    noise = rng.normal(0.0, 1.0, size=(rh, rw, 3)).astype(np.float32) * (std_rgb[None, None, :] * 0.22)
    synth_roi = np.clip(base_layer + noise, 0.0, 255.0)

    feather = cv2.GaussianBlur(roi_m, (7, 7), 1.8).astype(np.float32) / 255.0
    alpha = np.where(roi_m > 0, np.maximum(feather, 0.85), feather * 0.5)[:, :, None]
    blended = (1.0 - alpha) * work_rgb[y0:y1, x0:x1].astype(np.float32) + alpha * synth_roi

    out = work_rgb.copy()
    out[y0:y1, x0:x1] = np.clip(blended, 0, 255).astype(np.uint8)
    return out


def extract_black_censor_mask_and_restore_skin(
    censored_rgb: Union[Image.Image, np.ndarray],
    class_id: int = 0,
    min_area_ratio: float = 0.0003,
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """
    단일 완성본 이미지에서 수작업 솔리드 블랙 실루엣 마스크와 YOLO-seg 폴리곤을 추출하고,
    Shortcut Learning을 방지하기 위해 마스크 영역을 피부 톤 인페인팅으로 역복원합니다.
    반환값: `(restored_rgb_arr, binary_mask, yolo_lines)`
    """
    orig_arr = _to_rgb_array(censored_rgb)
    h, w = orig_arr.shape[:2]
    if h == 0 or w == 0:
        return orig_arr, np.zeros((0, 0), dtype=np.uint8), []

    gray = cv2.cvtColor(orig_arr, cv2.COLOR_RGB2GRAY)
    skin_bool = get_skin_mask(orig_arr) > 0
    skin_u8 = skin_bool.astype(np.uint8)
    k_adj = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    skin_near = cv2.dilate(skin_u8, k_adj) > 0

    arr_i16 = orig_arr.astype(np.int16)
    max_diff_ch = arr_i16.max(axis=2) - arr_i16.min(axis=2)
    solid_black = (
        (orig_arr[:, :, 0] <= 10)
        & (orig_arr[:, :, 1] <= 10)
        & (orig_arr[:, :, 2] <= 10)
        & (max_diff_ch <= 3)
    ).astype(np.uint8) * 255

    k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    opened = cv2.morphologyEx(solid_black, cv2.MORPH_OPEN, k_open)
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(opened)

    max_area = int(h * w * 0.16)
    candidate_mask = np.zeros((h, w), dtype=np.uint8)

    for idx in range(1, num_labels):
        area = int(stats[idx, cv2.CC_STAT_AREA])
        if area < 500 or area > max_area:
            continue
        bx, by, bw, bh, _ = [int(v) for v in stats[idx]]
        cx, cy = float(centroids[idx][0]), float(centroids[idx][1])
        if by <= 4 or cy < h * 0.22:
            continue

        x0, y0 = max(0, bx - 6), max(0, by - 6)
        x1, y1 = min(w, bx + bw + 6), min(h, by + bh + 6)
        comp_crop = (labels[y0:y1, x0:x1] == idx).astype(np.uint8)
        core_crop = cv2.erode(comp_crop, k_open) > 0
        if int(np.count_nonzero(core_crop)) < 80:
            continue
        if float(gray[y0:y1, x0:x1][core_crop].std()) > 2.2:
            continue

        ring_crop = (cv2.dilate(comp_crop, k_adj) > 0) & (comp_crop == 0)
        ring_cnt = int(np.count_nonzero(ring_crop))
        if ring_cnt == 0:
            continue
        skin_touch = float(np.count_nonzero(ring_crop & skin_near[y0:y1, x0:x1])) / float(ring_cnt)
        if skin_touch >= 0.42:
            candidate_mask[labels == idx] = 255

    if np.count_nonzero(candidate_mask) == 0:
        return orig_arr.copy(), np.zeros((h, w), dtype=np.uint8), []

    final_mask, yolo_lines = _mask_to_yolo_polygons(
        candidate_mask,
        class_id=class_id,
        min_area_ratio=min_area_ratio,
    )
    if not yolo_lines:
        return orig_arr.copy(), np.zeros((h, w), dtype=np.uint8), []

    # 1) 타겟 블랙 마스크 2회 팽창 후 다중 해상도 피부 톤 인페인팅 역복원
    inpaint_mask = cv2.dilate(final_mask, k_open, iterations=2)
    rng = np.random.default_rng(int(h * 10007 + w * 131 + int(np.count_nonzero(final_mask))))
    restored = _inpaint_region_with_skin_tone(
        orig_arr,
        inpaint_mask,
        skin_bool,
        rng,
        apply_distractor_style=False,
    )

    # 2) Anti-Shortcut 대조군 패치: 비타겟 일반 피부 영역에도 동일 질감의 인페인팅 패치 1~2곳 주입
    non_target_skin = (skin_u8 > 0) & (inpaint_mask == 0)
    if int(np.count_nonzero(non_target_skin)) >= 600:
        k_inner = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (29, 29))
        inner_skin = cv2.erode(non_target_skin.astype(np.uint8), k_inner) > 0
        # 타겟 영역 근처(36px)는 배제해 라벨 인접 경계 훼손 방지
        near_target = cv2.dilate(inpaint_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (37, 37))) > 0
        safe_skin = inner_skin & (~near_target)
        dys, dxs = np.nonzero(safe_skin)
        if len(dxs) > 0:
            n_patches = 2 if len(dxs) > 2500 else 1
            for _ in range(n_patches):
                pick = int(rng.integers(0, len(dxs)))
                px, py = int(dxs[pick]), int(dys[pick])
                rx = int(rng.integers(12, 26))
                ry = int(rng.integers(12, 26))
                distractor_m = np.zeros((h, w), dtype=np.uint8)
                cv2.ellipse(distractor_m, (px, py), (rx, ry), float(rng.integers(0, 180)), 0, 360, 255, -1)
                restored = _inpaint_region_with_skin_tone(
                    restored,
                    distractor_m,
                    skin_bool,
                    rng,
                    apply_distractor_style=True,
                )

    return restored, final_mask, yolo_lines


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

    return _mask_to_yolo_polygons(
        cleaned,
        class_id=class_id,
        min_area_ratio=min_area_ratio,
    )


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


def _is_kiro_h_pose(file_path: Path) -> bool:
    """kiro 에셋 파일명에서 H-씬 대역(`포즈 번호 >= 35`) 여부를 판정합니다."""
    return any(tok.isdigit() and int(tok) >= 35 for tok in file_path.stem.split("_"))


def build_yolo_seg_dataset(
    gt_dir: Path,
    projects_dir: Path,
    out_dir: Path,
    class_id: int = 0,
    diff_thresh: int = 18,
    gt_oversample: int = 1,
    kiro_projects_dir: Optional[Path] = None,
    kiro_rosters: Sequence[str] = ("don", "hey", "man"),
) -> Dict[str, int]:
    """
    ground_truth 검열본 + `_origin` 차분 쌍과 `kiro` 수작업 블랙 실루엣(피부 역복원 포함)을
    통합하여 YOLO-seg 학습 데이터셋을 일괄 생성합니다.
    """
    images_dir = out_dir / "images"
    labels_dir = out_dir / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    yaml_path = out_dir / "data.yaml"
    yaml_path.write_text(
        f"path: {out_dir.resolve().as_posix()}\n"
        "train: images\n"
        "val: images\n"
        "names:\n"
        f"  {int(class_id)}: genital\n",
        encoding="utf-8",
    )

    gt_files = (
        sorted(f for f in gt_dir.rglob("*") if f.is_file() and f.suffix.lower() in IMAGE_EXTS)
        if gt_dir.exists()
        else []
    )

    matched = 0
    processed = 0
    skipped_empty = 0
    gt_written = 0

    if gt_files:
        by_char_name, by_name = _index_origin_files(projects_dir)
        oversample = max(1, int(gt_oversample))

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

            rel_stem = "_".join(gt_file.relative_to(gt_dir).with_suffix("").parts).replace(" ", "_")
            label_payload = "\n".join(yolo_lines) + "\n"
            for copy_idx in range(oversample):
                eff_stem = rel_stem if copy_idx == 0 else f"{rel_stem}_os{copy_idx}"
                dst_img = images_dir / f"{eff_stem}{origin_file.suffix.lower()}"
                dst_lbl = labels_dir / f"{eff_stem}.txt"
                shutil.copy2(origin_file, dst_img)
                dst_lbl.write_text(label_payload, encoding="utf-8")
                gt_written += 1
            processed += 1

    kiro_scanned = 0
    kiro_processed = 0
    if kiro_projects_dir is not None and Path(kiro_projects_dir).exists():
        kiro_root = Path(kiro_projects_dir)
        for roster in kiro_rosters:
            roster_assets = kiro_root / str(roster).strip() / "assets"
            if not roster_assets.is_dir():
                continue
            files = sorted(
                f for f in roster_assets.rglob("*")
                if f.is_file() and f.suffix.lower() in IMAGE_EXTS and _is_kiro_h_pose(f)
            )
            for k_file in files:
                kiro_scanned += 1
                with Image.open(k_file) as opened:
                    restored_arr, _, yolo_lines = extract_black_censor_mask_and_restore_skin(
                        opened,
                        class_id=class_id,
                    )
                if not yolo_lines:
                    continue

                rel_stem = "_".join(k_file.relative_to(roster_assets).with_suffix("").parts).replace(" ", "_")
                out_stem = f"kiro_{roster}_{rel_stem}"
                dst_img = images_dir / f"{out_stem}.webp"
                dst_lbl = labels_dir / f"{out_stem}.txt"
                Image.fromarray(restored_arr).save(dst_img, "WEBP", quality=95)
                dst_lbl.write_text("\n".join(yolo_lines) + "\n", encoding="utf-8")
                kiro_processed += 1
                processed += 1

    return {
        "total_gt": len(gt_files),
        "matched": matched,
        "processed": processed,
        "gt_written": gt_written,
        "skipped_empty": skipped_empty,
        "kiro_scanned": kiro_scanned,
        "kiro_processed": kiro_processed,
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
    parser.add_argument("--gt-oversample", type=int, default=1, help="ground_truth 쌍 오버샘플링 배수 (기본: 1)")
    parser.add_argument(
        "--kiro-projects-dir",
        type=Path,
        default=None,
        help="수작업 블랙 실루엣을 추출할 kiro/projects 루트 디렉토리 (읽기 전용)",
    )
    parser.add_argument(
        "--kiro-rosters",
        type=str,
        default="don,hey,man",
        help="kiro에서 스캔할 쉼표 구분 로스터 목록 (기본: don,hey,man)",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = create_parser().parse_args(argv)
    rosters = tuple(r.strip() for r in str(args.kiro_rosters).split(",") if r.strip())
    stats = build_yolo_seg_dataset(
        gt_dir=args.gt_dir,
        projects_dir=args.projects_dir,
        out_dir=args.out_dir,
        class_id=args.class_id,
        diff_thresh=args.diff_thresh,
        gt_oversample=args.gt_oversample,
        kiro_projects_dir=args.kiro_projects_dir,
        kiro_rosters=rosters,
    )
    print(
        f"[YOLO-seg Extractor] {stats['processed']} items processed "
        f"(total_gt={stats['total_gt']}, matched={stats['matched']}, gt_written={stats['gt_written']}, "
        f"skipped_empty={stats['skipped_empty']}, kiro_scanned={stats['kiro_scanned']}, "
        f"kiro_processed={stats['kiro_processed']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
