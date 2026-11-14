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
from typing import Any, Dict, List, Optional, Sequence

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


def train_censor_seg(
    gt_dir: Path,
    projects_dir: Path,
    dataset_dir: Path,
    out_weights: Path,
    base_model: str = "yolov8n-seg.pt",
    epochs: int = 100,
    imgsz: int = 640,
    batch: int = 8,
    device: Optional[str] = None,
    diff_thresh: int = 18,
    run_project_dir: Optional[Path] = None,
    run_name: str = "censor_seg_train",
    dry_run: bool = False,
) -> int:
    """데이터셋 동기화 후 전용 YOLO-seg 모델을 학습하고 최종 가중치를 배포합니다."""
    summary: Dict[str, int] = build_yolo_seg_dataset(
        gt_dir=gt_dir,
        projects_dir=projects_dir,
        out_dir=dataset_dir,
        diff_thresh=diff_thresh,
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
        f"processed={summary.get('processed', 0)}, "
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

    from ultralytics import YOLO

    eff_run_dir.mkdir(parents=True, exist_ok=True)
    model = YOLO(base_model)

    train_kwargs: Dict[str, Any] = {
        "data": str(data_yaml),
        "epochs": int(epochs),
        "imgsz": int(imgsz),
        "batch": int(batch),
        "project": str(eff_run_dir),
        "name": str(run_name),
        "exist_ok": True,
        "degrees": 25.0,
        "scale": 0.4,
        "fliplr": 0.5,
        "hsv_h": 0.015,
        "hsv_s": 0.5,
        "hsv_v": 0.3,
    }
    if device:
        train_kwargs["device"] = device

    results = model.train(**train_kwargs)
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
        default=ROOT_DIR / "output" / "projects",
        help="원본 프로젝트 루트 디렉터리",
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=ROOT_DIR / "output" / "censor_seg_dataset",
        help="추출된 YOLO-seg 데이터셋 저장 경로",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="yolov8n-seg.pt",
        help="기반 Ultralytics 세그멘테이션 체크포인트",
    )
    parser.add_argument("--epochs", type=int, default=100, help="학습 에포크 수")
    parser.add_argument("--imgsz", type=int, default=640, help="입력 해상도")
    parser.add_argument("--batch", type=int, default=8, help="배치 크기")
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
        run_project_dir=args.run_dir,
        run_name=args.run_name,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
