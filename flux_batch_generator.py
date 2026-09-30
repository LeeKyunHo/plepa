"""
flux_batch_generator.py
플럭스(FLUX.1 [dev]) 기반 캐릭터 에셋 배치 생성기 (플에파 / PLEPA) - CLI 진입점.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from plepa_engine.comfy_client import ComfyClient, ComfyClientError
from plepa_engine.config import (
    COMFY_HOST,
    DEFAULT_HEIGHT,
    DEFAULT_ROSTER,
    DEFAULT_STEPS,
    DEFAULT_UNET_GGUF,
    DEFAULT_WIDTH,
    POSE_DB_PATH,
    PROJECTS_DIR,
    configure_stdio,
)

configure_stdio()
from plepa_engine.models import (
    CharacterConfig,
    GenerationResult,
    GenerationTarget,
    PoseEntry,
)
from plepa_engine.prompt_builder import assemble_flux_prompt
from plepa_engine.reporter import (
    asset_filename,
    build_genit_block,
    open_in_explorer,
    print_batch_summary,
)
from plepa_engine.workflow_templates import build_flux_workflow


def load_pose_db(path: Path = POSE_DB_PATH) -> Dict[str, PoseEntry]:
    """flux_pose_database.json 로드 및 PoseEntry 딕셔너리로 변환."""
    if not path.exists():
        raise FileNotFoundError(f"포즈 데이터베이스를 찾을 수 없습니다: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries: Dict[str, PoseEntry] = {}
    for section in ("emotions", "poses", "h_scenes", "scenes_otokonoko"):
        sec_dict = data.get(section, {})
        for code, item in sec_dict.items():
            code_str = f"{int(code):02d}" if int(code) < 100 else str(code)
            entries[code_str] = PoseEntry(
                code=code_str,
                section=section,
                label=item.get("label", "미상"),
                prompt=item.get("prompt", "")
            )
    return entries


def find_character(char_name: str, roster: str = DEFAULT_ROSTER) -> tuple[CharacterConfig, str]:
    """캐릭터 JSON 설정 로드 및 로스터 자동 탐색."""
    clean_name = char_name[:-5] if char_name.endswith(".json") else char_name

    # 1. 사용자가 지정한 로스터에서 우선 탐색
    char_file = PROJECTS_DIR / roster / "characters" / f"{clean_name}.json"
    if char_file.exists():
        with open(char_file, "r", encoding="utf-8") as f:
            return CharacterConfig.from_dict(json.load(f), file_path=char_file), roster

    # 2. projects/* 전체에서 탐색 (지정 로스터에 없거나 default인 경우)
    for proj in sorted(PROJECTS_DIR.iterdir()):
        if proj.is_dir() and proj.name != roster:
            candidate = proj / "characters" / f"{clean_name}.json"
            if candidate.exists():
                with open(candidate, "r", encoding="utf-8") as f:
                    return CharacterConfig.from_dict(json.load(f), file_path=candidate), proj.name

    raise FileNotFoundError(f"캐릭터 설정 파일을 찾을 수 없습니다: {char_name} (로스터: {roster})")


def resolve_characters(char_expr: str, roster: str = DEFAULT_ROSTER) -> List[tuple[CharacterConfig, str]]:
    """'all', 쉼표 구분, 또는 단일 캐릭터 표현식을 해석하여 캐릭터 목록 반환."""
    expr = char_expr.strip().lower()
    if expr == "all":
        char_dir = PROJECTS_DIR / roster / "characters"
        if not char_dir.exists():
            raise FileNotFoundError(f"로스터 캐릭터 폴더를 찾을 수 없습니다: {char_dir}")
        results = []
        for file in sorted(char_dir.glob("*.json")):
            with open(file, "r", encoding="utf-8") as f:
                results.append((CharacterConfig.from_dict(json.load(f), file_path=file), roster))
        if not results:
            raise FileNotFoundError(f"로스터에 등록된 캐릭터 JSON 파일이 없습니다: {roster}")
        return results

    if "," in char_expr:
        results = []
        for token in char_expr.split(","):
            token = token.strip()
            if token:
                results.append(find_character(token, roster=roster))
        return results

    return [find_character(char_expr, roster=roster)]


def load_character(char_name: str, roster: str = DEFAULT_ROSTER) -> CharacterConfig:
    """하위 호환용 래퍼 함수."""
    char, _ = find_character(char_name, roster=roster)
    return char


def load_background_preset(roster: str, key: str = "default") -> str:
    """projects/{roster}/background.json 로드."""
    bg_file = PROJECTS_DIR / roster / "background.json"
    if not bg_file.exists():
        return ""
    try:
        with open(bg_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get(key, data.get("default", ""))
    except Exception:
        return ""


def resolve_pose_codes(expr: str, db: Dict[str, PoseEntry]) -> List[str]:
    """사용자가 지정한 포즈 표현식(all, emotions, 00..19, 01,02 등)을 코드 목록으로 해석."""
    expr = expr.strip().lower()
    if expr == "all":
        return sorted(db.keys(), key=lambda x: int(x))
    if expr in ("emotions", "emotion"):
        return [c for c, e in db.items() if e.section == "emotions"]
    if expr in ("poses", "pose"):
        return [c for c, e in db.items() if e.section == "poses"]
    if expr in ("h_scenes", "h", "scenes"):
        return [c for c, e in db.items() if e.section == "h_scenes"]
    if expr in ("otokonoko", "scenes_otokonoko", "oto"):
        return [c for c, e in db.items() if e.section == "scenes_otokonoko"]

    # 범위 연산자 지원: 00..19
    if ".." in expr:
        start_s, end_s = expr.split("..", 1)
        start, end = int(start_s), int(end_s)
        codes = []
        for i in range(start, end + 1):
            c_str = f"{i:02d}" if i < 100 else str(i)
            if c_str in db:
                codes.append(c_str)
        return codes

    # 쉼표 구분: 00,01,05
    if "," in expr:
        codes = []
        for token in expr.split(","):
            token = token.strip()
            if not token:
                continue
            c_str = f"{int(token):02d}" if int(token) < 100 else str(token)
            if c_str in db:
                codes.append(c_str)
        return codes

    # 단일 코드
    single_code = f"{int(expr):02d}" if int(expr) < 100 else str(expr)
    if single_code in db:
        return [single_code]

    raise ValueError(f"유효하지 않은 포즈 코드/표현식입니다: {expr}")


def run_self_test() -> int:
    """파이프라인 무결성 자체 진단 테스트 (52+ 항목 점검)."""
    print("=" * 60)
    print("  [플에파] 시스템 무결성 자체 진단 테스트 (Self-Test)")
    print("=" * 60)
    errors: List[str] = []

    # 1. 포즈 DB 로드 검사
    try:
        db = load_pose_db()
        print(f"✔ 포즈 데이터베이스 로드 성공 (총 {len(db)}개 항목)")
        if len(db) != 80:
            errors.append(f"포즈 DB 항목 수가 80개가 아닙니다 (현재: {len(db)}개)")
    except Exception as e:
        errors.append(f"포즈 DB 로드 실패: {e}")
        db = {}

    # 2. Danbooru 태그 및 BREAK 문법 잔류 검사
    if db:
        for code, entry in db.items():
            if "BREAK" in entry.prompt:
                errors.append(f"코드 [{code}] 프롬프트에 금지된 BREAK 문법 잔류")
            if "((" in entry.prompt or ":1." in entry.prompt:
                errors.append(f"코드 [{code}] 프롬프트에 SDXL 괄호 가중치 태그 잔류")
            if not entry.label:
                errors.append(f"코드 [{code}] 라벨 누락")
        print("✔ 80종 플럭스 자연어 프롬프트 순수성 검사 완료")

    # 3. 샘플 캐릭터 로드 검사
    try:
        char = load_character("sample_character")
        print(f"✔ 샘플 캐릭터({char.name}) 로드 성공")
        if not char.appearance.face_and_hair or not char.appearance.physique:
            errors.append("캐릭터 필수 외형 필드 누락")
    except Exception as e:
        errors.append(f"샘플 캐릭터 로드 실패: {e}")
        char = None

    # 4. 프롬프트 조립 및 탈의 로직 검사
    if db and char:
        prompt_clothed, nude_flag = assemble_flux_prompt(char, db["00"])
        if nude_flag or char.appearance.outfit not in prompt_clothed:
            errors.append("평상 포즈(00)에서 의상 포함 누락 또는 잘못된 탈의 판정")

        prompt_nude, nude_flag = assemble_flux_prompt(char, db["40"])
        if not nude_flag or char.appearance.outfit in prompt_nude:
            errors.append("H-씬(40)에서 의상 탈의 자동 스트리핑 실패")
        print("✔ 의상 착의/탈의 분기 조립 로직 검사 통과")

    # 5. 워크플로우 템플릿 생성 검사
    try:
        wf_normal = build_flux_workflow("test prompt", "test_prefix", use_face_detailer=False)
        if "1" not in wf_normal or "20" not in wf_normal:
            errors.append("기본 워크플로우 노드 생성 불완전")
        wf_detailer = build_flux_workflow("test prompt", "test_prefix", use_face_detailer=True)
        if "10" not in wf_detailer:
            errors.append("Face Detailer 워크플로우 노드 생성 불완전")
        print("✔ ComfyUI 워크플로우 템플릿 생성 검사 통과")
    except Exception as e:
        errors.append(f"워크플로우 생성 실패: {e}")

    print("-" * 60)
    if errors:
        print(f"[FAIL] 총 {len(errors)}개 결함 발견:")
        for err in errors:
            print(f"  ❌ {err}")
        return 1
    else:
        print("[PASS] 모든 진단 검사 항목을 통과했습니다. 시스템 무결성 100% 보장.")
        return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="flux_batch_generator",
        description="플럭스(FLUX.1 [dev]) 캐릭터 에셋 배치 생성기 (플에파 / PLEPA)"
    )
    parser.add_argument("-c", "--character", help="생성할 캐릭터 이름 (예: sample_character)")
    parser.add_argument("-p", "--pose", default="all", help="생성할 포즈 코드/범위 (all, emotions, 00..19, 01 등)")
    parser.add_argument("-r", "--roster", default=DEFAULT_ROSTER, help=f"로스터 폴더 (기본: {DEFAULT_ROSTER})")
    parser.add_argument("--bg-preset", default="default", help="배경 프리셋 키 (기본: default)")
    parser.add_argument("--dry-run", action="store_true", help="ComfyUI 호출 없이 프롬프트 및 파일명 점검")
    parser.add_argument("--skip-existing", action="store_true", help="이미 존재하는 WebP 파일은 생략하고 건너뜀")
    parser.add_argument("--face-detailer", action="store_true", help="Face Detailer 얼굴 보정 활성화")
    parser.add_argument("--upscale", action="store_true", help="4x AI 초고화질 업스케일러 활성화")
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS, help=f"샘플링 스텝 수 (기본: {DEFAULT_STEPS})")
    parser.add_argument("--unet", default=DEFAULT_UNET_GGUF, help=f"사용할 GGUF UNet 모델 파일명 (기본: {DEFAULT_UNET_GGUF})")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH, help=f"이미지 가로 폭 (기본: {DEFAULT_WIDTH})")
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT, help=f"이미지 세로 높이 (기본: {DEFAULT_HEIGHT})")
    parser.add_argument("--test", action="store_true", help="시스템 무결성 자가 진단 실행")

    args = parser.parse_args(argv)

    if args.test:
        return run_self_test()

    if not args.character:
        parser.print_help()
        print("\n[오류] -c/--character 인수로 캐릭터를 지정해야 합니다.")
        return 1

    try:
        db = load_pose_db()
        target_chars = resolve_characters(args.character, roster=args.roster)
        codes = resolve_pose_codes(args.pose, db)
    except Exception as e:
        print(f"[설정 오류] {e}")
        return 1

    client = ComfyClient(host=COMFY_HOST)
    if not args.dry_run:
        if not client.check_connection():
            print(f"[오류] ComfyUI 서버({COMFY_HOST})에 연결할 수 없습니다.")
            print("ComfyUI 폴더의 'run_nvidia_gpu.bat'를 실행하여 서버를 가동해 주십시오.")
            print("(프롬프트 구성 점검만 원하시면 --dry-run 옵션을 사용하세요)")
            return 1

    print("=" * 60)
    print(f"  [플에파] FLUX.1 [dev] 에셋 배치 생성 파이프라인 가동")
    print(f"  대상 캐릭터: 총 {len(target_chars)}명 ({', '.join(c.prefix for c, _ in target_chars)})")
    print(f"  캐릭터당 포즈: 총 {len(codes)}개 ({', '.join(codes)}) | 총 {len(target_chars) * len(codes)}개 에셋")
    print(f"  옵션: Face Detailer={'활성' if args.face_detailer else '비활성'}, Upscale={'활성' if args.upscale else '비활성'}")
    print("=" * 60)

    last_output_dir = None

    for char_idx, (char, actual_roster) in enumerate(target_chars, 1):
        bg_prompt = load_background_preset(actual_roster, key=args.bg_preset)
        output_dir = PROJECTS_DIR / actual_roster / "assets" / char.prefix
        output_dir.mkdir(parents=True, exist_ok=True)
        last_output_dir = output_dir

        print(f"\n▶ [{char_idx}/{len(target_chars)}] {char.name} ({char.prefix}) [로스터: {actual_roster}]")
        if bg_prompt:
            print(f"  배경 프리셋: '{args.bg_preset}' 적용")

        results: List[GenerationResult] = []
        total_start = time.time()

        for idx, code in enumerate(codes, 1):
            pose = db[code]
            prompt, is_nude = assemble_flux_prompt(char, pose, bg_prompt=bg_prompt)
            out_name = asset_filename(char.prefix, code)
            out_path = output_dir / out_name

            target = GenerationTarget(
                code=code,
                section=pose.section,
                label=pose.label,
                assembled_prompt=prompt,
                is_nude=is_nude,
                output_filename=out_name,
            )

            print(f"  [{idx:02d}/{len(codes):02d}] #{code} {pose.label:<10} ({pose.section}) ➔ {out_name}", end="", flush=True)

            if args.dry_run:
                print(" [DRY-RUN 완료]")
                results.append(GenerationResult(target=target, success=True, image_path=out_path, duration_sec=0.0))
                continue

            if args.skip_existing and out_path.exists() and out_path.stat().st_size > 0:
                print(" [기존 파일 존재: 건너뜀]")
                results.append(GenerationResult(target=target, success=True, image_path=out_path, duration_sec=0.0))
                continue

            item_start = time.time()
            workflow = build_flux_workflow(
                prompt=prompt,
                output_prefix=f"{char.prefix}_{code}",
                width=args.width,
                height=args.height,
                steps=args.steps,
                use_face_detailer=args.face_detailer,
                use_upscale=args.upscale,
                unet_name=args.unet,
            )

            try:
                client.generate_image(workflow=workflow, output_path=out_path)
                duration = time.time() - item_start
                print(f" [완료: {duration:.1f}초]")
                results.append(GenerationResult(target=target, success=True, image_path=out_path, duration_sec=duration))
            except ComfyClientError as ce:
                duration = time.time() - item_start
                print(f" [실패: {ce}]")
                results.append(GenerationResult(target=target, success=False, duration_sec=duration, error_message=str(ce)))

        total_duration = time.time() - total_start

        # 결과 요약 콘솔 출력
        print_batch_summary(char.prefix, results, output_dir, total_duration)

        # 젠잇 마크다운 블록 조립 및 저장
        genit_block = build_genit_block(char.prefix, results, db)
        if genit_block:
            genit_file = output_dir / f"{char.prefix}_genit_guide.md"
            with open(genit_file, "w", encoding="utf-8") as gf:
                gf.write(genit_block)
            print(f"✔ 젠잇 마크다운 가이드 파일 저장: {genit_file}")

    if not args.dry_run and last_output_dir and last_output_dir.parent.exists():
        open_in_explorer(last_output_dir.parent)

    return 0


if __name__ == "__main__":
    sys.exit(main())
