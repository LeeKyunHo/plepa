#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
전용 검열 YOLO-seg 모델 원클릭 파인튜닝 스크립트 (`scripts/train_censor_seg.py`).

8085 모바일 검수 뷰어의 1초 리터치로 축적된 정답(Ground Truth) 페어로부터
YOLO-seg 폴리곤 데이터셋을 자동 동기화한 뒤 Ultralytics YOLO-seg 모델을 학습하고,
최적 가중치(`best.pt`)를 `models/censor_seg.pt`로 배치합니다.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.extract_censor_seg_dataset import build_yolo_seg_dataset


def _resolve_trained_weights(
    results: Any,
    run_project_dir: Path,
    run_name: str,
) -> Optional[Path]:
    """Ultralytics 학습 결과 객체 또는 실행 폴더에서 best.pt(또는 last.pt) 경로를 탐색합니다."""
    candidate_dirs: List[Path] = []
    save_dir = getattr(results, "save_dir", None)
    if save_dir:
        candidate_dirs.append(Path(str(save_dir)) / "weights")
    candidate_dirs.append(run_project_dir / run_name / "weights")

    for weights_dir in candidate_dirs:
        for fname in ("best.pt", "last.pt"):
            cand = weights_dir / fname
            if cand.is_file():
                return cand
    return None


def _normalize_kiro_rosters(kiro_rosters: Any) -> Tuple[str, ...]:
    if isinstance(kiro_rosters, str):
        return tuple(r.strip() for r in kiro_rosters.split(",") if r.strip())
    return tuple(str(r).strip() for r in kiro_rosters if str(r).strip())


def _load_yolo_base_with_fallback(base_model: str) -> Tuple[Any, str]:
    """요청한 YOLO-seg 체크포인트 로딩 실패 시 대체 체크포인트(yolov8s-seg -> 로컬 yolov8n-seg)로 폴백합니다."""
    from ultralytics import YOLO

    candidates: List[str] = [base_model]
    for fb in ("yolov8s-seg.pt", str(ROOT_DIR / "yolov8n-seg.pt"), "yolov8n-seg.pt"):
        if fb not in candidates:
            candidates.append(fb)

    last_err: Optional[Exception] = None
    for cand in candidates:
        try:
            return YOLO(cand), cand
        except Exception as err:
            last_err = err
            print(f"[Warn] 체크포인트 로딩 실패({cand}): {err} -> 다음 후보 시도")
    if last_err is not None:
        raise last_err
    raise RuntimeError(f"사용 가능한 YOLO-seg 체크포인트를 찾지 못했습니다: {base_model}")


def train_censor_seg(
    gt_dir: Path,
    projects_dir: Path,
    dataset_dir: Path,
    out_weights: Path,
    base_model: str = "yolo11s-seg.pt",
    epochs: int = 65,
    imgsz: int = 1024,
    batch: int = 4,
    device: Optional[str] = None,
    diff_thresh: int = 18,
    gt_oversample: int = 4,
    kiro_projects_dir: Optional[Path] = None,
    kiro_rosters: Any = ("don", "hey", "man"),
    include_kiro_inpaint: bool = False,
    clean_spy_dir: Optional[Path] = None,
    spy_holdout_per_char: int = 4,
    hard_neg_limit: int = 120,
    inscene_neg_limit: int = 55,
    extreme_pose_oversample: int = 3,
    mask_ratio: int = 2,
    run_project_dir: Optional[Path] = None,
    run_name: str = "censor_seg_train",
    dry_run: bool = False,
) -> int:
    """클린 데이터셋 동기화 후 전용 YOLO-seg 모델을 학습하고 최종 가중치를 배포합니다."""
    default_spy_dir = ROOT_DIR.parent / "kiro" / "projects" / "spy" / "assets"
    is_default_projects = projects_dir.resolve() in {
        (ROOT_DIR / "projects").resolve(),
        (ROOT_DIR / "output" / "projects").resolve(),
    }
    if clean_spy_dir is None and is_default_projects and default_spy_dir.is_dir():
        eff_spy_dir: Optional[Path] = default_spy_dir
    else:
        eff_spy_dir = clean_spy_dir

    eff_projects_dir = (
        ROOT_DIR / "projects"
        if is_default_projects and not projects_dir.exists() and (ROOT_DIR / "projects").exists()
        else projects_dir
    )

    summary: Dict[str, int] = build_yolo_seg_dataset(
        gt_dir=gt_dir,
        projects_dir=eff_projects_dir,
        out_dir=dataset_dir,
        diff_thresh=diff_thresh,
        gt_oversample=gt_oversample,
        kiro_projects_dir=kiro_projects_dir,
        kiro_rosters=_normalize_kiro_rosters(kiro_rosters),
        include_kiro_inpaint=include_kiro_inpaint,
        clean_spy_dir=eff_spy_dir,
        spy_holdout_per_char=spy_holdout_per_char,
        hard_neg_limit=hard_neg_limit,
        inscene_neg_limit=inscene_neg_limit,
        extreme_pose_oversample=extreme_pose_oversample,
    )
    images_dir = dataset_dir / "images"
    data_yaml = dataset_dir / "data.yaml"
    image_count = (
        len([p for p in images_dir.iterdir() if p.is_file()])
        if images_dir.exists()
        else 0
    )

    print(
        f"[Dataset] total_gt={summary.get('total_gt', 0)}, "
        f"matched={summary.get('matched', 0)}, "
        f"gt_written={summary.get('gt_written', 0)}, "
        f"spy_train={summary.get('spy_train_written', 0)}, "
        f"spy_holdout_excluded={summary.get('spy_holdout_excluded', 0)}, "
        f"hard_neg={summary.get('hard_neg_written', 0)}, "
        f"inscene_neg={summary.get('inscene_neg_written', 0)}, "
        f"train={summary.get('train_split_count', 0)}, "
        f"val={summary.get('val_split_count', 0)}, "
        f"kiro_processed={summary.get('kiro_processed', 0)}, "
        f"skipped_empty={summary.get('skipped_empty', 0)}, "
        f"ready_images={image_count}"
    )

    eff_run_dir = run_project_dir or (ROOT_DIR / "output" / "censor_seg_runs")

    if dry_run:
        print(
            f"[Dry-Run] data={data_yaml}, model={base_model}, epochs={epochs}, "
            f"imgsz={imgsz}, batch={batch}, device={device or 'auto'}, out={out_weights}"
        )
        return 0

    if not data_yaml.exists() or image_count == 0:
        print(
            f"[Error] 학습 가능한 YOLO-seg 이미지가 없습니다 (data.yaml={data_yaml}, count={image_count}).",
            file=sys.stderr,
        )
        return 1

    eff_run_dir.mkdir(parents=True, exist_ok=True)
    model, resolved_base = _load_yolo_base_with_fallback(base_model)
    print(
        f"[Train] base_model={resolved_base}, imgsz={imgsz}, batch={batch}, "
        f"epochs={epochs}, mask_ratio={max(1, int(mask_ratio))}"
    )

    train_kwargs: Dict[str, Any] = {
        "data": str(data_yaml),
        "epochs": int(epochs),
        "imgsz": int(imgsz),
        "batch": int(batch),
        "project": str(eff_run_dir),
        "name": str(run_name),
        "exist_ok": True,
        "patience": 20,
        "mask_ratio": max(1, int(mask_ratio)),
        "overlap_mask": False,
        "mosaic": 0.5,
        "close_mosaic": 15,
        "degrees": 30.0,
        "scale": 0.5,
        "fliplr": 0.5,
        "hsv_h": 0.015,
        "hsv_s": 0.5,
        "hsv_v": 0.3,
    }
    if device:
        train_kwargs["device"] = device

    try:
        results = model.train(**train_kwargs)
    except RuntimeError as oom_err:
        if "out of memory" in str(oom_err).lower() and (int(imgsz) > 832 or int(batch) > 2):
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            if int(batch) > 2:
                print(
                    f"[Warn] CUDA OOM at imgsz={imgsz}, batch={batch} -> imgsz={imgsz}, batch=2로 자동 재시도합니다."
                )
                train_kwargs["batch"] = 2
                try:
                    model, resolved_base = _load_yolo_base_with_fallback(base_model)
                    results = model.train(**train_kwargs)
                except RuntimeError as oom_err2:
                    if "out of memory" in str(oom_err2).lower() and int(imgsz) > 832:
                        print("[Warn] CUDA OOM at batch=2 -> imgsz=832, batch=2로 최종 폴백 재시도합니다.")
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                        train_kwargs["imgsz"] = 832
                        train_kwargs["batch"] = 2
                        model, resolved_base = _load_yolo_base_with_fallback(base_model)
                        results = model.train(**train_kwargs)
                    else:
                        raise
            else:
                print(f"[Warn] CUDA OOM at imgsz={imgsz}, batch={batch} -> imgsz=832, batch=2로 자동 재시도합니다.")
                train_kwargs["imgsz"] = 832
                train_kwargs["batch"] = min(2, int(batch))
                model, resolved_base = _load_yolo_base_with_fallback(base_model)
                results = model.train(**train_kwargs)
        else:
            raise
    best_weight = _resolve_trained_weights(results, eff_run_dir, run_name)
    if best_weight is None or not best_weight.is_file():
        print(
            f"[Error] 학습된 가중치(best.pt/last.pt)를 찾을 수 없습니다: {eff_run_dir / run_name}",
            file=sys.stderr,
        )
        return 1

    out_weights.parent.mkdir(parents=True, exist_ok=True)
    tmp_dst = out_weights.with_suffix(".pt.tmp")
    shutil.copy2(best_weight, tmp_dst)
    os.replace(tmp_dst, out_weights)
    print(f"[Done] 전용 세그멘테이션 가중치 배포 완료: {best_weight} -> {out_weights}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="전용 검열 YOLO-seg 모델 학습 및 가중치 배포")
    parser.add_argument(
        "--gt-dir",
        type=Path,
        default=ROOT_DIR / "output" / "benchmarks" / "ground_truth",
        help="리터치 정답 이미지 디렉터리",
    )
    parser.add_argument(
        "--projects-dir",
        type=Path,
        default=ROOT_DIR / "projects",
        help="원본 프로젝트 루트 디렉터리",
    )
    parser.add_argument(
        "--clean-spy-dir",
        type=Path,
        default=None,
        help="1:1 클린 화이트 정답 쌍을 추출할 spy/assets 디렉터리 (미지정 시 기본 경로 자동 탐색)",
    )
    parser.add_argument(
        "--spy-holdout-per-char",
        type=int,
        default=4,
        help="캐릭터별 학습 제외(Hold-out) 정답 쌍 개수 (기본: 4)",
    )
    parser.add_argument(
        "--hard-neg-limit",
        type=int,
        default=120,
        help="비노출 일상 포즈(<=034) 하드 네거티브 샘플 수 (기본: 120)",
    )
    parser.add_argument(
        "--inscene-neg-limit",
        type=int,
        default=55,
        help="성인 씬 내부 비타겟(하단 체액·복부) 부분 네거티브 크롭 수 (기본: 55)",
    )
    parser.add_argument(
        "--extreme-pose-oversample",
        type=int,
        default=3,
        help="구강·후면 등 극단 구도 포즈 최소 오버샘플링 배수 (기본: 3)",
    )
    parser.add_argument(
        "--kiro-projects-dir",
        type=Path,
        default=None,
        help="수작업 블랙 실루엣(인페인트) 추출용 kiro/projects 루트 디렉터리",
    )
    parser.add_argument(
        "--kiro-rosters",
        type=str,
        default="don,hey,man",
        help="kiro에서 스캔할 쉼표 구분 로스터 목록 (기본: don,hey,man)",
    )
    parser.add_argument(
        "--include-kiro-inpaint",
        action="store_true",
        help="레거시 인페인트 합성본(don/hey/man)을 데이터셋에 포함 (기본 비활성화)",
    )
    parser.add_argument(
        "--gt-oversample",
        type=int,
        default=4,
        help="ground_truth 원본 쌍 오버샘플링 배수 (기본: 4)",
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=ROOT_DIR / "output" / "censor_seg_dataset",
        help="추출된 YOLO-seg 데이터셋 저장 경로",
    )
    parser.add_argument(
        "--model",
        "--base-model",
        dest="model",
        type=str,
        default="yolo11s-seg.pt",
        help="기반 Ultralytics 세그멘테이션 체크포인트 (기본: yolo11s-seg.pt)",
    )
    parser.add_argument("--epochs", type=int, default=65, help="학습 에포크 수 (기본: 65)")
    parser.add_argument("--imgsz", type=int, default=1024, help="입력 해상도 (기본: 1024)")
    parser.add_argument("--batch", type=int, default=4, help="배치 크기 (기본: 4)")
    parser.add_argument("--mask-ratio", type=int, default=2, help="YOLO-seg 마스크 다운샘플 비율 (기본: 2, 낮을수록 고정밀)")
    parser.add_argument("--device", type=str, default=None, help="학습 디바이스 (예: 0, cpu)")
    parser.add_argument("--diff-thresh", type=int, default=18, help="Diff 이진화 임계값")
    parser.add_argument(
        "--out-weights",
        type=Path,
        default=ROOT_DIR / "models" / "censor_seg.pt",
        help="최종 배포 가중치 경로",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=ROOT_DIR / "output" / "censor_seg_runs",
        help="학습 로그 및 체크포인트 작업 디렉터리",
    )
    parser.add_argument("--run-name", type=str, default="censor_seg_train", help="실행 이름")
    parser.add_argument("--dry-run", action="store_true", help="데이터셋 동기화 및 설정 검증만 수행")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return train_censor_seg(
        gt_dir=args.gt_dir,
        projects_dir=args.projects_dir,
        dataset_dir=args.dataset_dir,
        out_weights=args.out_weights,
        base_model=args.model,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        diff_thresh=args.diff_thresh,
        gt_oversample=args.gt_oversample,
        kiro_projects_dir=args.kiro_projects_dir,
        kiro_rosters=args.kiro_rosters,
        include_kiro_inpaint=args.include_kiro_inpaint,
        clean_spy_dir=args.clean_spy_dir,
        spy_holdout_per_char=args.spy_holdout_per_char,
        hard_neg_limit=args.hard_neg_limit,
        inscene_neg_limit=args.inscene_neg_limit,
        extreme_pose_oversample=args.extreme_pose_oversample,
        mask_ratio=args.mask_ratio,
        run_project_dir=args.run_dir,
        run_name=args.run_name,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
