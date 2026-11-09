"""
scripts/benchmark_pose_convergence.py
PLEPA 통계적 포즈 구도 수렴 및 검열 정합성 벤치마크 도구 (Statistical Pose Benchmark)

[핵심 목적]:
1. 단일 시드 착시(Stochastic Coincidence)를 배제하고 다중 캐릭터(N>=3) × 다중 시드(N>=3) 총 N=9개 표본으로
   포즈의 물리적 구도 일관성(BBox 중심점 분산 σ)과 검열 정합성을 통계적으로 엄밀하게 검증.
2. 모델 실제 객체 탐지(YOLO Detection)와 안전 앵커 폴백(Anchor Fallback)을 분리 집계하여 허위/과장 보고를 원천 차단 (GEMINI.md Rule 8).
3. 9개 표본을 3x3 그리드로 결합한 A4 규격 컨택트 시트(Contact Sheet) 단일 이미지를 자동 렌더링하여
   개발자가 3초 만에 시각적 수렴 여부 및 미러링 발생을 육안 검수(Visual QA)할 수 있도록 지원.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw, ImageFont

from plepa_engine.censor import detect_genitals, get_pose_anchor_box
from plepa_engine.config import PROJECTS_DIR
from plepa_engine.services.generation_service import GenerationParams, default_generation_service
from plepa_engine.services.pose_service import default_pose_service


@dataclass
class SampleMeasurement:
    """단일 표본의 측정 데이터."""
    character: str
    seed: int
    image_path: Path
    width: int
    height: int
    is_detected: bool
    is_fallback: bool
    confidence: float
    bbox: Optional[Tuple[int, int, int, int]]  # (x1, y1, x2, y2)
    center_x: float  # 0.0 ~ 1.0 정규화
    center_y: float  # 0.0 ~ 1.0 정규화
    area_ratio: float  # 0.0 ~ 100.0 %


@dataclass
class BenchmarkSummary:
    """벤치마크 종합 통계 결과."""
    pose_code: str
    pose_label: str
    total_samples: int
    detection_count: int
    fallback_count: int
    unmasked_count: int
    detection_rate: float
    fallback_rate: float
    mean_center_x: float
    std_center_x: float
    mean_center_y: float
    std_center_y: float
    mean_area_ratio: float
    contact_sheet_path: Optional[str] = None


def get_font(size: int = 18) -> ImageFont.ImageFont:
    """한글/영문 지원 폰트를 안전하게 로드합니다."""
    candidates = [
        "C:/Windows/Fonts/malgunbd.ttf",
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def measure_single_image(image_path: Path, pose_code: str) -> SampleMeasurement:
    """단일 이미지에서 YOLO 실제 객체 탐지 및 앵커 폴백을 분리 측정합니다."""
    with Image.open(image_path) as img:
        w, h = img.size

    # 1. 모델 실제 객체 탐지 (YOLO)
    detections = detect_genitals(image_path, targets=("penis",), min_confidence=0.22)

    if detections:
        # 실제 모델 탐지 성공
        best_box, label, score = detections[0]
        x1, y1, x2, y2 = best_box
        cx = ((x1 + x2) / 2.0) / w
        cy = ((y1 + y2) / 2.0) / h
        area = ((x2 - x1) * (y2 - y1)) / (w * h) * 100.0
        return SampleMeasurement(
            character="",
            seed=0,
            image_path=image_path,
            width=w,
            height=h,
            is_detected=True,
            is_fallback=False,
            confidence=score,
            bbox=best_box,
            center_x=cx,
            center_y=cy,
            area_ratio=area,
        )

    # 2. 모델 미탐지 시 안전 앵커 폴백 확인
    fallback_box = get_pose_anchor_box(pose_code, w, h)
    if fallback_box:
        x1, y1, x2, y2 = fallback_box
        cx = ((x1 + x2) / 2.0) / w
        cy = ((y1 + y2) / 2.0) / h
        area = ((x2 - x1) * (y2 - y1)) / (w * h) * 100.0
        return SampleMeasurement(
            character="",
            seed=0,
            image_path=image_path,
            width=w,
            height=h,
            is_detected=False,
            is_fallback=True,
            confidence=0.0,
            bbox=fallback_box,
            center_x=cx,
            center_y=cy,
            area_ratio=area,
        )

    # 3. 미검열 노출 위험 (탐지 실패 및 앵커 부재)
    return SampleMeasurement(
        character="",
        seed=0,
        image_path=image_path,
        width=w,
        height=h,
        is_detected=False,
        is_fallback=False,
        confidence=0.0,
        bbox=None,
        center_x=0.5,
        center_y=0.5,
        area_ratio=0.0,
    )


def compute_statistics(measurements: List[SampleMeasurement], pose_code: str, pose_label: str) -> BenchmarkSummary:
    """측정치 리스트로부터 통계적 평균, 표준편차 및 탐지율을 산출합니다."""
    n = len(measurements)
    if n == 0:
        return BenchmarkSummary(
            pose_code=pose_code,
            pose_label=pose_label,
            total_samples=0,
            detection_count=0,
            fallback_count=0,
            unmasked_count=0,
            detection_rate=0.0,
            fallback_rate=0.0,
            mean_center_x=0.0,
            std_center_x=0.0,
            mean_center_y=0.0,
            std_center_y=0.0,
            mean_area_ratio=0.0,
        )

    det_cnt = sum(1 for m in measurements if m.is_detected)
    fall_cnt = sum(1 for m in measurements if m.is_fallback)
    unmasked_cnt = sum(1 for m in measurements if not m.is_detected and not m.is_fallback)

    xs = [m.center_x for m in measurements]
    ys = [m.center_y for m in measurements]
    areas = [m.area_ratio for m in measurements]

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    mean_area = sum(areas) / n

    std_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs) / n) if n > 1 else 0.0
    std_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys) / n) if n > 1 else 0.0

    return BenchmarkSummary(
        pose_code=pose_code,
        pose_label=pose_label,
        total_samples=n,
        detection_count=det_cnt,
        fallback_count=fall_cnt,
        unmasked_count=unmasked_cnt,
        detection_rate=(det_cnt / n) * 100.0,
        fallback_rate=(fall_cnt / n) * 100.0,
        mean_center_x=mean_x,
        std_center_x=std_x,
        mean_center_y=mean_y,
        std_center_y=std_y,
        mean_area_ratio=mean_area,
    )


def render_contact_sheet(
    measurements: List[SampleMeasurement],
    summary: BenchmarkSummary,
    output_path: Path,
    cols: int = 3,
) -> Path:
    """
    9개 표본을 3x3 그리드로 결합한 A4 규격 컨택트 시트를 생성합니다.
    각 타일 상단에 검출 상태 뱃지와 BBox 시각화를 오버레이합니다.
    """
    n = len(measurements)
    rows = math.ceil(n / cols)

    tile_w = 480
    tile_h = int(tile_w * (1216 / 832))  # 종횡비 유지 (약 701px)
    header_h = 44
    padding = 16
    footer_h = 130

    total_w = cols * tile_w + (cols + 1) * padding
    total_h = rows * (tile_h + header_h) + (rows + 1) * padding + footer_h

    sheet = Image.new("RGB", (total_w, total_h), color=(18, 22, 34))
    draw = ImageDraw.Draw(sheet)

    font_title = get_font(22)
    font_badge = get_font(14)
    font_footer = get_font(16)
    font_bold = get_font(18)

    # 1. 개별 타일 렌더링
    for idx, m in enumerate(measurements):
        r = idx // cols
        c = idx % cols

        x_offset = padding + c * (tile_w + padding)
        y_offset = padding + r * (tile_h + header_h + padding)

        # 1-1. 헤더 배경 바
        draw.rectangle(
            [x_offset, y_offset, x_offset + tile_w, y_offset + header_h],
            fill=(28, 34, 52),
            outline=(45, 55, 80),
        )

        # 캐릭터 & 시드 라벨
        char_text = f"{m.character.upper()} | Seed: {m.seed}"
        draw.text((x_offset + 10, y_offset + 12), char_text, fill=(240, 240, 240), font=font_bold)

        # 상태 뱃지
        if m.is_detected:
            badge_text = f"YOLO DETECT: {m.confidence:.2f}"
            badge_bg = (34, 139, 34)  # ForestGreen
        elif m.is_fallback:
            badge_text = "ANCHOR FALLBACK"
            badge_bg = (218, 112, 214)  # Orchid / Amber
        else:
            badge_text = "UNMASKED RISK"
            badge_bg = (220, 20, 60)  # Crimson

        badge_w = int(draw.textlength(badge_text, font=font_badge)) + 16
        badge_x = x_offset + tile_w - badge_w - 8
        draw.rounded_rectangle(
            [badge_x, y_offset + 8, badge_x + badge_w, y_offset + header_h - 8],
            radius=6,
            fill=badge_bg,
        )
        draw.text((badge_x + 8, y_offset + 12), badge_text, fill=(255, 255, 255), font=font_badge)

        # 1-2. 타일 이미지 리사이즈 및 붙여넣기
        img_y = y_offset + header_h
        try:
            with Image.open(m.image_path) as orig_img:
                tile_img = orig_img.convert("RGB").resize((tile_w, tile_h), Image.Resampling.LANCZOS)
        except Exception:
            tile_img = Image.new("RGB", (tile_w, tile_h), color=(40, 40, 40))

        # 1-3. 타일 위에 BBox 및 중심점 오버레이
        tile_draw = ImageDraw.Draw(tile_img)
        scale_x = tile_w / m.width if m.width > 0 else 1.0
        scale_y = tile_h / m.height if m.height > 0 else 1.0

        if m.bbox:
            bx1, by1, bx2, by2 = m.bbox
            tx1 = int(bx1 * scale_x)
            ty1 = int(by1 * scale_y)
            tx2 = int(bx2 * scale_x)
            ty2 = int(by2 * scale_y)

            box_color = (50, 255, 50) if m.is_detected else (255, 165, 0)
            tile_draw.rectangle([tx1, ty1, tx2, ty2], outline=box_color, width=3)

            # 중심점 십자선
            tcx = int((tx1 + tx2) / 2)
            tcy = int((ty1 + ty2) / 2)
            cross_r = 10
            tile_draw.line([tcx - cross_r, tcy, tcx + cross_r, tcy], fill=(255, 50, 50), width=2)
            tile_draw.line([tcx, tcy - cross_r, tcx, tcy + cross_r], fill=(255, 50, 50), width=2)

            # 좌표 태그
            coord_str = f"Xc:{m.center_x:.3f} Yc:{m.center_y:.3f} ({m.area_ratio:.1f}%)"
            tile_draw.rectangle([tx1, ty2 + 4, tx1 + 170, ty2 + 24], fill=(0, 0, 0, 180))
            tile_draw.text((tx1 + 4, ty2 + 6), coord_str, fill=(255, 255, 255), font=font_badge)

        sheet.paste(tile_img, (x_offset, img_y))
        draw.rectangle([x_offset, img_y, x_offset + tile_w, img_y + tile_h], outline=(55, 65, 95), width=1)

    # 2. 마스터 풋터 패널 렌더링
    footer_y = total_h - footer_h + padding // 2
    draw.rounded_rectangle(
        [padding, footer_y, total_w - padding, total_h - padding],
        radius=10,
        fill=(24, 30, 46),
        outline=(50, 60, 90),
    )

    title_text = f"📊 포즈 #{summary.pose_code} [{summary.pose_label}] 통계적 구도 수렴 및 검열 정합성 보고서"
    draw.text((padding + 20, footer_y + 14), title_text, fill=(255, 215, 0), font=font_title)

    stat_line1 = (
        f"총 표본수: {summary.total_samples}장 (3 캐릭터 × 3 시드)   |   "
        f"실제 모델 탐지율: {summary.detection_rate:.1f}% ({summary.detection_count}건)   |   "
        f"안전 앵커 폴백: {summary.fallback_rate:.1f}% ({summary.fallback_count}건)   |   "
        f"미검열 위험: {summary.unmasked_count}건"
    )
    draw.text((padding + 20, footer_y + 52), stat_line1, fill=(220, 225, 240), font=font_footer)

    stat_line2 = (
        f"물리적 BBox 중심점 X축: μ = {summary.mean_center_x:.4f} (σ_X = {summary.std_center_x:.4f})   |   "
        f"Y축: μ = {summary.mean_center_y:.4f} (σ_Y = {summary.std_center_y:.4f})   |   "
        f"평균 마스크 면적 비율: {summary.mean_area_ratio:.2f}%"
    )
    draw.text((padding + 20, footer_y + 80), stat_line2, fill=(160, 180, 215), font=font_footer)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, "WEBP", quality=92)
    return output_path


def run_benchmark(
    pose_code: str,
    characters: List[str],
    seeds: List[int],
    roster: str = "school",
    output_dir: Optional[Path] = None,
    mock: bool = False,
    dry_run: bool = False,
    only_contact_sheet: bool = False,
) -> Tuple[BenchmarkSummary, List[SampleMeasurement]]:
    """지정된 포즈에 대해 다중 캐릭터 × 다중 시드 벤치마크를 실행합니다."""
    pose_dict = default_pose_service.get_pose_details(pose_code)
    pose_label = pose_dict.get("label", f"포즈_{pose_code}") if pose_dict else f"포즈_{pose_code}"

    if output_dir is None:
        output_dir = Path("output/benchmarks") / f"pose_{pose_code}"
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(f"  [BENCHMARK] 포즈 #{pose_code} [{pose_label}] 통계적 구도 수렴 및 검열 벤치마크")
    print("=" * 70)
    print(f"  대상 로스터: {roster}")
    print(f"  대상 캐릭터 ({len(characters)}명): {', '.join(characters)}")
    print(f"  고정 시드 ({len(seeds)}개): {', '.join(str(s) for s in seeds)}")
    print(f"  총 표본 크기: {len(characters) * len(seeds)}장 (N = {len(characters) * len(seeds)})")
    print(f"  저장 폴더: {output_dir}")
    print(f"  모드: {'[MOCK 시뮬레이션]' if mock else '[DRY-RUN]' if dry_run else '[실제 ComfyUI 생성]'}")
    print("=" * 70)

    measurements: List[SampleMeasurement] = []

    # 1. 이미지 생성 및 측정 루프
    total_tasks = len(characters) * len(seeds)
    task_idx = 0

    for char in characters:
        for seed in seeds:
            task_idx += 1
            sample_filename = f"{char}_{pose_code}_seed{seed}.webp"
            sample_path = raw_dir / sample_filename

            print(f"\n▶ [{task_idx}/{total_tasks}] {char.upper()} × Seed {seed} (포즈 {pose_code})")

            if only_contact_sheet and sample_path.exists():
                print(f"   - 기존 파일 재사용: {sample_path.name}")
            else:
                params = GenerationParams(
                    character_expr=char,
                    pose_expr=pose_code,
                    roster=roster,
                    seed=seed,
                    overwrite=True,
                    engine="sdxl",
                    censor=False,  # 객관적 YOLO 원시 탐지 측정을 위해 무검열 원본 생성
                    mock=mock,
                    dry_run=dry_run,
                    no_ref=True,  # 순수 포즈 프롬프트 영향력 실측을 위해 IP-Adapter 비활성화
                )

                if mock:
                    # Mock 더미 이미지 생성 (BBox 영역에 임의 색상 사각형 주입)
                    from PIL import ImageDraw
                    dummy = Image.new("RGB", (832, 1216), color=(200, 180, 160))
                    d_draw = ImageDraw.Draw(dummy)
                    # 모의 결합 부위
                    d_draw.rectangle([350, 700, 480, 850], fill=(255, 255, 255))
                    dummy.save(sample_path, "WEBP", quality=80)
                    print(f"   ✓ Mock 이미지 생성 완료: {sample_path.name}")
                elif dry_run:
                    print(f"   - Dry-Run 완료 (프롬프트 점검)")
                    continue
                else:
                    res = default_generation_service.run_batch(params, quiet=True)
                    if res and res[0].success:
                        gen_path = res[0].image_path
                        if gen_path and Path(gen_path).exists():
                            shutil.copy2(gen_path, sample_path)
                            print(f"   ✓ 생성 완료: {sample_path.name}")
                        else:
                            print(f"   ❌ 생성 파일 누락: {gen_path}")
                            continue
                    else:
                        err = res[0].error_message if res else "Unknown Error"
                        print(f"   ❌ 생성 실패: {err}")
                        continue

            # 측정 수행
            if sample_path.exists():
                m = measure_single_image(sample_path, pose_code)
                m.character = char
                m.seed = seed
                measurements.append(m)

                stat_type = "DETECT" if m.is_detected else "FALLBACK" if m.is_fallback else "UNMASKED"
                print(f"     측정: [{stat_type}] Conf={m.confidence:.2f} | BBox={m.bbox} | Center=({m.center_x:.3f}, {m.center_y:.3f}) | 면적={m.area_ratio:.1f}%")

    # 2. 통계 산출
    summary = compute_statistics(measurements, pose_code, pose_label)

    # 3. 컨택트 시트 렌더링
    contact_sheet_path = output_dir / f"contact_sheet_pose_{pose_code}.webp"
    if measurements:
        render_contact_sheet(measurements, summary, contact_sheet_path, cols=len(seeds))
        summary.contact_sheet_path = str(contact_sheet_path)
        print(f"\n📸 [컨택트 시트 렌더링 완료]: {contact_sheet_path}")

    # 4. 마크다운 리포트 생성
    report_path = output_dir / "benchmark_report.md"
    report_content = f"""# 📊 포즈 #{summary.pose_code} [{summary.pose_label}] 통계적 벤치마크 결과 보고서

- **실행 일시**: {time.strftime('%Y-%m-%d %H:%M:%S')}
- **대상 로스터**: `{roster}`
- **표본 구성**: {len(characters)}개 캐릭터 (`{', '.join(characters)}`) × {len(seeds)}개 시드 (`{', '.join(str(s) for s in seeds)}`)
- **총 표본 수 ($N$)**: {summary.total_samples}

---

## 1. 정량적 검열 및 탐지 지표 (Rule 8 준수: 모델 탐지와 폴백 분리)

| 지표명 | 측정 수치 | 비고 |
| :--- | :---: | :--- |
| **총 표본 수 ($N$)** | **{summary.total_samples}** | $N \\ge 9$ 다중 표본 |
| **실제 모델 객체 탐지율** | **{summary.detection_rate:.1f}%** ({summary.detection_count} / {summary.total_samples}) | YOLO 원시 검출 성공률 |
| **안전 앵커 폴백 마스킹율** | **{summary.fallback_rate:.1f}%** ({summary.fallback_count} / {summary.total_samples}) | 미탐지 시 기하학 앵커 방어 |
| **미검열 노출 위험 건수** | **{summary.unmasked_count} 건** | 반드시 0건이어야 합격 |
| **평균 BBox 중심점 $X$ ($\mu_X \pm \sigma_X$)** | **{summary.mean_center_x:.4f} $\\pm$ {summary.std_center_x:.4f}** | 정규화 수평 중심 및 표준편차 |
| **평균 BBox 중심점 $Y$ ($\mu_Y \pm \sigma_Y$)** | **{summary.mean_center_y:.4f} $\\pm$ {summary.std_center_y:.4f}** | 정규화 수직 중심 및 표준편차 |
| **평균 마스크 면적 비율** | **{summary.mean_area_ratio:.2f}%** | 캔버스 대비 검열 면적 |

---

## 2. 개별 표본 세부 측정 데이터

| 번호 | 캐릭터 | 시드 | 탐지 상태 | 신뢰도 | BBox 좌표 $(x_1, y_1, x_2, y_2)$ | 중심점 $(X_c, Y_c)$ | 면적 비율 |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
"""
    for idx, m in enumerate(measurements, 1):
        status_str = "🟢 YOLO DETECT" if m.is_detected else "🟠 FALLBACK" if m.is_fallback else "🔴 RISK"
        bbox_str = f"`{m.bbox}`" if m.bbox else "None"
        report_content += (
            f"| {idx} | `{m.character}` | `{m.seed}` | {status_str} | {m.confidence:.2f} | "
            f"{bbox_str} | ({m.center_x:.3f}, {m.center_y:.3f}) | {m.area_ratio:.1f}% |\n"
        )

    report_content += f"""
---

## 3. 종합 컨택트 시트 (Visual QA)
![Contact Sheet]({contact_sheet_path.name})
"""

    report_path.write_text(report_content, encoding="utf-8")
    print(f"📝 [보고서 저장 완료]: {report_path}")

    # 콘솔 요약 출력
    print("\n" + "=" * 70)
    print("  [BENCHMARK RESULT SUMMARY]")
    print("=" * 70)
    print(f"  포즈: #{summary.pose_code} [{summary.pose_label}]")
    print(f"  총 표본: N = {summary.total_samples}")
    print(f"  실제 모델 탐지율: {summary.detection_rate:.1f}% ({summary.detection_count}건)")
    print(f"  안전 앵커 폴백율: {summary.fallback_rate:.1f}% ({summary.fallback_count}건)")
    print(f"  미검열 노출 위험: {summary.unmasked_count}건 (목표: 0건)")
    print(f"  수평 중심 X: μ = {summary.mean_center_x:.4f} (σ_X = {summary.std_center_x:.4f})")
    print(f"  수직 중심 Y: μ = {summary.mean_center_y:.4f} (σ_Y = {summary.std_center_y:.4f})")
    print(f"  평균 마스크 면적: {summary.mean_area_ratio:.2f}%")
    print("=" * 70 + "\n")

    return summary, measurements


def main():
    parser = argparse.ArgumentParser(description="PLEPA 통계적 포즈 구도 수렴 및 검열 정합성 벤치마크 러너")
    parser.add_argument("--pose", "-p", default="088", help="대상 포즈 번호 (기본: 088)")
    parser.add_argument("--chars", "-c", default="dan,ena,ria", help="대상 캐릭터 목록 (쉼표 구분, 기본: dan,ena,ria)")
    parser.add_argument("--seeds", "-s", default="1001,1002,1003", help="고정 시드 목록 (쉼표 구분, 기본: 1001,1002,1003)")
    parser.add_argument("--roster", "-r", default="school", help="대상 로스터 (기본: school)")
    parser.add_argument("--output-dir", "-o", default=None, help="결과 저장 폴더")
    parser.add_argument("--mock", action="store_true", help="ComfyUI 호출 없이 0.01초 파이프라인 무결성 시뮬레이션")
    parser.add_argument("--dry-run", action="store_true", help="프롬프트 검사만 수행")
    parser.add_argument("--only-contact-sheet", action="store_true", help="이미 생성된 이미지를 바탕으로 컨택트 시트 및 통계만 갱신")

    args = parser.parse_args()

    chars = [c.strip() for c in args.chars.split(",") if c.strip()]
    seeds = [int(s.strip()) for s in args.seeds.split(",") if s.strip()]
    out_dir = Path(args.output_dir) if args.output_dir else None

    run_benchmark(
        pose_code=args.pose,
        characters=chars,
        seeds=seeds,
        roster=args.roster,
        output_dir=out_dir,
        mock=args.mock,
        dry_run=args.dry_run,
        only_contact_sheet=args.only_contact_sheet,
    )


if __name__ == "__main__":
    main()
