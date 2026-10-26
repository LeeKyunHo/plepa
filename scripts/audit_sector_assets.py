"""
scripts/audit_sector_assets.py
캐릭터 에셋 폴더의 6대 섹터(대역)별 전수 검수 스크립트:
- 1. 검열 정합성 (검열 필요 포즈 검열 여부, 비검열 포즈 오검열 여부, _origin 원본 보존 여부)
- 2. 파일 무결성 및 해상도 규격
- 3. 구도 및 Auto-QC 정합성 (인원수, 머리 복제, 손 증식, 상반신 밀착 구도 모브 침범 여부)
- 4. 섹터별/캐릭터별 종합 리포트 생성
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from PIL import Image

# Plepa 엔진 모듈 임포트
from plepa_engine.censor import is_pose_censor_required, get_pose_category
from plepa_engine.config import DEFAULT_ROSTER, PROJECTS_DIR
from plepa_engine.reporter import get_subfolder_for_code
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.pose_service import default_pose_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AuditSectorAssets")

SECTORS = [
    "01_emotions",
    "02_daily",
    "03_events",
    "04_romance",
    "05_h_scenes",
    "06_special_h",
]

SECTOR_NAMES = {
    "01_emotions": "01. 감정표현 (000~019)",
    "02_daily": "02. 범용 일상 (020~050)",
    "03_events": "03. 로스터 이벤트 (051~059)",
    "04_romance": "04. 로맨스 & 구강 (060~079)",
    "05_h_scenes": "05. 범용 H씬 체위 (080~129 / 150~199)",
    "06_special_h": "06. 특색 H씬 (130~139 / 200~209)",
}


def audit_character(
    roster: str,
    prefix: str,
    char_name: str,
    pose_db: Dict[str, Any],
    run_deep_qc: bool = False,
    qc_sample_limit: int = 10,
) -> Dict[str, Any]:
    """한 캐릭터의 6대 섹터 에셋 전수 검수."""
    asset_dir = PROJECTS_DIR / roster / "assets" / prefix
    origin_dir = PROJECTS_DIR / roster / "assets" / f"{prefix}_origin"

    report: Dict[str, Any] = {
        "prefix": prefix,
        "name": char_name,
        "total_files": 0,
        "sectors": {s: {
            "name": SECTOR_NAMES.get(s, s),
            "files_count": 0,
            "censored_count": 0,
            "uncensored_count": 0,
            "origin_backed_count": 0,
            "censor_anomalies": [],  # 미검열 누락 또는 오검열 목록
            "qc_anomalies": [],      # 구도/손/인원수 불량 목록
            "items": []
        } for s in SECTORS},
        "summary": {
            "censor_missing_count": 0,     # 검열 필요하나 미검열된 건수
            "over_censor_count": 0,        # 비검열인데 검열된 건수 (오검열)
            "origin_missing_count": 0,     # 원본 백업 누락 건수
            "qc_fail_count": 0,            # 구도/인원수/손 불량 건수
        }
    }

    if not asset_dir.is_dir():
        logger.warning(f"캐릭터 에셋 폴더 없음: {asset_dir}")
        return report

    # 1. 파일 스캔 (하위 폴더 및 플랫 구조 모두 지원)
    pattern = re.compile(rf"^{re.escape(prefix)}_([A-Za-z0-9]+)(?:_(.*?))?(?:_censored)?\.(webp|png)$")
    all_files = sorted(list(asset_dir.rglob("*.webp")) + list(asset_dir.rglob("*.png")))
    all_files = [f for f in all_files if "_trash" not in f.parts and f.is_file()]

    report["total_files"] = len(all_files)

    # 딥러닝 QA 검증기 임포트 (필요 시)
    qa_validator_func = None
    if run_deep_qc:
        try:
            from plepa_engine.qa_validator import validate_generated_image
            qa_validator_func = validate_generated_image
        except ImportError:
            logger.warning("QA Validator 모듈을 불러올 수 없습니다.")

    qc_checked_count = 0

    for file_path in all_files:
        m = pattern.match(file_path.name)
        if not m:
            continue

        code = m.group(1)
        raw_label = m.group(2) or ""
        is_censored_name = "_censored" in file_path.name

        # 소속 섹터 계산 (실제 폴더 기준 또는 코드 기준)
        rel_parts = file_path.relative_to(asset_dir).parts
        if len(rel_parts) > 1 and rel_parts[0] in SECTORS:
            sector = rel_parts[0]
        else:
            sector = get_subfolder_for_code(code)

        if sector not in report["sectors"]:
            sector = "02_daily"

        sec_data = report["sectors"][sector]
        sec_data["files_count"] += 1

        # 검열 규칙 대조
        should_censor = is_pose_censor_required(pose_code=code, file_path=file_path)
        
        # 원본 백업(_origin) 존재 여부
        has_origin = False
        if origin_dir.is_dir():
            cand1 = origin_dir / sector / file_path.name
            cand2 = origin_dir / file_path.name
            cand3 = list(origin_dir.rglob(f"{prefix}_{code}*"))
            if cand1.is_file() or cand2.is_file() or len(cand3) > 0:
                has_origin = True
                sec_data["origin_backed_count"] += 1
            else:
                report["summary"]["origin_missing_count"] += 1
        else:
            report["summary"]["origin_missing_count"] += 1

        # 검열 상태 정합성 검사
        censor_status = "normal"
        if should_censor:
            sec_data["censored_count"] += 1
            if not is_censored_name and not has_origin:
                # 검열 대상인데 _censored 표기도 없고 _origin도 없으면 미검열 노출 위험 의심
                censor_status = "POTENTIAL_UNPROTECTED"
                sec_data["censor_anomalies"].append({
                    "code": code,
                    "filename": file_path.name,
                    "reason": "검열 대상 포즈이나 원본 및 검열 분리가 안 되어 있음"
                })
                report["summary"]["censor_missing_count"] += 1
        else:
            sec_data["uncensored_count"] += 1
            if is_censored_name:
                # 비검열 대상인데 검열명이 붙은 경우 (오검열)
                censor_status = "OVER_CENSORED"
                sec_data["censor_anomalies"].append({
                    "code": code,
                    "filename": file_path.name,
                    "reason": "비검열 대상(감정/일상/이벤트) 포즈이나 _censored 파일로 존재함"
                })
                report["summary"]["over_censor_count"] += 1

        # 이미지 해상도 검사
        try:
            with Image.open(file_path) as im:
                img_w, img_h = im.size
                ratio_str = f"{img_w}x{img_h}"
        except Exception:
            ratio_str = "unknown"

        # Auto-QC 구도 검증 (딥러닝)
        qc_result = {"valid": True, "reason": "", "metrics": {}}
        if run_deep_qc and qa_validator_func and (qc_sample_limit == 0 or qc_checked_count < qc_sample_limit):
            # H씬 및 로맨스 위주 또는 무작위 샘플링 검사
            pose_obj = pose_db.get(code)
            is_two_person = False
            is_close_up = False
            pose_prompt = ""
            if pose_obj:
                pose_prompt = getattr(pose_obj, "sdxl_positive", "") or getattr(pose_obj, "prompt", "")
                is_two_person = any(k in pose_prompt.lower() for k in ("2girls", "1boy, 1girl", "couple", "missionary", "fellatio", "paizuri", "doggystyle", "cowgirl"))

            is_valid, reject_reason, metrics = qa_validator_func(
                image=file_path,
                is_solo_scene=not is_two_person,
                is_two_person=is_two_person,
                conf_threshold=0.55,
                prompt=pose_prompt,
                check_blur=True,
                min_blur_score=50.0,
            )
            qc_result = {"valid": is_valid, "reason": reject_reason, "metrics": metrics}
            qc_checked_count += 1

            if not is_valid:
                sec_data["qc_anomalies"].append({
                    "code": code,
                    "filename": file_path.name,
                    "reason": reject_reason,
                    "metrics": metrics
                })
                report["summary"]["qc_fail_count"] += 1

        sec_data["items"].append({
            "code": code,
            "filename": file_path.name,
            "resolution": ratio_str,
            "should_censor": should_censor,
            "is_censored_name": is_censored_name,
            "has_origin": has_origin,
            "censor_status": censor_status,
            "qc": qc_result,
        })

    return report


def main():
    parser = argparse.ArgumentParser(description="캐릭터 에셋 섹터별 전수 검수")
    parser.add_argument("--roster", default="campus", help="검수할 로스터 (기본: campus)")
    parser.add_argument("--char", default="all", help="특정 캐릭터 prefix (기본: all)")
    parser.add_argument("--deep-qc", action="store_true", help="imgutils 딥러닝 구도/손/인원수 검사 실행")
    parser.add_argument("--qc-samples", type=int, default=15, help="캐릭터당 딥러닝 QC 샘플 검사 수 (0=전수)")
    parser.add_argument("--json-out", default="", help="결과를 저장할 JSON 경로")
    args = parser.parse_args()

    roster = args.roster
    logger.info(f"=== [{roster.upper()}] 로스터 에셋 섹터별 전수 검수 시작 ===")
    start_time = time.time()

    pose_db = default_pose_service.load_pose_db(engine="sdxl", roster=roster)
    chars = default_character_service.list_characters(roster=roster)

    if args.char != "all":
        chars = [c for c in chars if c[1].prefix == args.char]

    all_reports = []

    print("\n" + "═" * 80)
    print(f"📊 [{roster.upper()}] 로스터 6대 섹터 에셋 전수 검수 리포트")
    print("═" * 80)

    total_roster_files = 0
    total_censor_missing = 0
    total_over_censor = 0
    total_origin_missing = 0
    total_qc_fails = 0

    for roster_name, char_obj, path in chars:
        prefix = char_obj.prefix
        name = char_obj.name
        rep = audit_character(
            roster=roster,
            prefix=prefix,
            char_name=name,
            pose_db=pose_db,
            run_deep_qc=args.deep_qc,
            qc_sample_limit=args.qc_samples,
        )
        all_reports.append(rep)

        summ = rep["summary"]
        total_roster_files += rep["total_files"]
        total_censor_missing += summ["censor_missing_count"]
        total_over_censor += summ["over_censor_count"]
        total_origin_missing += summ["origin_missing_count"]
        total_qc_fails += summ["qc_fail_count"]

        print(f"\n👤 [{prefix.upper()}] {name} (총 {rep['total_files']}장)")
        print("  " + "─" * 74)
        print(f"  {'섹터 (대역)':<28} | {'파일수':<6} | {'검열본':<6} | {'원본백업':<8} | {'검열이상':<6} | {'QC이상':<6}")
        print("  " + "─" * 74)

        for s in SECTORS:
            s_data = rep["sectors"][s]
            c_anom = len(s_data["censor_anomalies"])
            qc_anom = len(s_data["qc_anomalies"])
            status_flag = "✅" if c_anom == 0 and qc_anom == 0 else "⚠️"
            print(f"  {status_flag} {s_data['name']:<25} | {s_data['files_count']:<6} | {s_data['censored_count']:<6} | {s_data['origin_backed_count']:<8} | {c_anom:<6} | {qc_anom:<6}")

            # 이상 발생 시 세부 출력
            if c_anom > 0:
                for anom in s_data["censor_anomalies"]:
                    print(f"    └─ 🚨 [검열 이상] {anom['code']}: {anom['filename']} -> {anom['reason']}")
            if qc_anom > 0:
                for anom in s_data["qc_anomalies"]:
                    print(f"    └─ ⚠️ [구도/품질 이상] {anom['code']}: {anom['filename']} -> {anom['reason']}")

    elapsed = round(time.time() - start_time, 2)
    print("\n" + "═" * 80)
    print(f"🏁 종합 감사 결과 ({elapsed}초 소요)")
    print(f"  - 총 검수 이미지 수: {total_roster_files}장")
    print(f"  - 검열 누락/위험: {total_censor_missing}건")
    print(f"  - 비검열 오검열: {total_over_censor}건")
    print(f"  - _origin 원본 누락: {total_origin_missing}건")
    if args.deep_qc:
        print(f"  - 구도/인원수/손 QC 불량: {total_qc_fails}건")
    print("═" * 80 + "\n")

    if args.json_out:
        out_p = Path(args.json_out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(all_reports, f, ensure_ascii=False, indent=2)
        print(f"📄 JSON 감사 리포트 저장 완료: {out_p}")


if __name__ == "__main__":
    main()
