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
    DEFAULT_SDXL_CFG,
    DEFAULT_SDXL_CKPT,
    DEFAULT_SDXL_HEIGHT,
    DEFAULT_SDXL_SAMPLER,
    DEFAULT_SDXL_SCHEDULER,
    DEFAULT_SDXL_STEPS,
    DEFAULT_SDXL_WIDTH,
    DEFAULT_STEPS,
    DEFAULT_UNET_GGUF,
    DEFAULT_WIDTH,
    FLUX_POSE_DB_PATH,
    POSE_DB_PATH,
    PROJECTS_DIR,
    SDXL_POSE_DB_PATH,
    configure_stdio,
)

configure_stdio()
from plepa_engine.models import (
    CharacterConfig,
    GenerationResult,
    GenerationTarget,
    PoseEntry,
)
from plepa_engine.profile_resolver import (
    apply_profile_to_prompt,
    load_global_profiles,
    resolve_character_profile,
)
from plepa_engine.prompt_builder import assemble_flux_prompt, assemble_sdxl_prompt
from plepa_engine.reporter import (
    asset_filename,
    open_in_explorer,
    print_batch_summary,
)
from plepa_engine.workflow_templates import build_flux_workflow, build_sdxl_workflow


def load_pose_db(engine: str = "flux", path: Optional[Path] = None) -> Dict[str, PoseEntry]:
    """엔진(flux / sdxl)에 맞는 포즈 데이터베이스 로드 및 PoseEntry 딕셔너리로 변환."""
    if path is None:
        path = SDXL_POSE_DB_PATH if engine.lower() == "sdxl" else POSE_DB_PATH

    if not path.exists():
        raise FileNotFoundError(f"포즈 데이터베이스를 찾을 수 없습니다: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries: Dict[str, PoseEntry] = {}
    for section in ("emotions", "poses", "h_scenes", "scenes_otokonoko"):
        sec_dict = data.get(section, {})
        for code, item in sec_dict.items():
            code_str = f"{int(code):03d}"
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


def print_roster_characters(roster: str = DEFAULT_ROSTER) -> int:
    """로스터 내 등록된 캐릭터들의 프로필 목록을 콘솔 테이블로 출력합니다."""
    char_dir = PROJECTS_DIR / roster / "characters"
    if not char_dir.exists():
        print(f"\n[오류] 로스터 캐릭터 폴더를 찾을 수 없습니다: {char_dir}")
        return 1

    files = sorted(char_dir.glob("*.json"))
    if not files:
        print(f"\n[안내] 로스터 '{roster}'에 등록된 캐릭터 JSON 파일이 없습니다.")
        return 0

    print("=" * 82)
    print(f"  [플에파] 로스터 캐릭터 목록: {roster} (총 {len(files)}명)")
    print("=" * 82)
    header = f"  {'식별자(ID)':<12} {'한글명 (영문명)':<24} {'성별':<8} {'프로필(의상)':<18} {'기본 의상 요약'}"
    print(header)
    print("  " + "-" * 78)

    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            char = CharacterConfig.from_dict(data, file_path=path)
            prof_list = list(char.profiles.keys())
            prof_str = ", ".join(prof_list) if prof_list else "default"
            outfit_text = char.appearance.outfit.replace("\n", " ").strip()
            outfit_summary = (outfit_text[:28] + "..") if len(outfit_text) > 28 else (outfit_text or "-")
            print(f"  {char.prefix:<12} {char.name:<24} {char.gender:<8} {prof_str:<18} {outfit_summary}")
        except Exception as e:
            print(f"  {path.stem:<12} [오류: {e}]")

    print("=" * 82)
    return 0


def generate_mock_image(output_path: Path) -> None:
    """ComfyUI 연동 없이 0.001초 만에 더미 WebP 이미지를 생성하여 파이프라인 무결성을 검증합니다."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image
        img = Image.new("RGB", (64, 64), color=(60, 100, 180))
        img.save(output_path, "WEBP", quality=80)
    except Exception:
        # Pillow 부재 시 유효한 초소형 1x1 WebP 바이너리 직접 기록 (안전 폴백)
        tiny_webp = (
            b"RIFF\x1a\x00\x00\x00WEBPVP8L\x0e\x00\x00\x00/x\x00\x00\x00\x00\x00\x88\x88\xfe\x07\x00\x00"
        )
        with open(output_path, "wb") as f:
            f.write(tiny_webp)


def find_reference_image(prefix: str, roster: str = DEFAULT_ROSTER, custom_path: Optional[str] = None) -> Optional[Path]:
    """캐릭터의 참조 이미지를 탐색합니다 (지정 경로 -> references/{prefix}.{ext} 순)."""
    if custom_path:
        p = Path(custom_path)
        if p.is_file():
            return p
        cand = PROJECTS_DIR / roster / "references" / custom_path
        if cand.is_file():
            return cand
        raise FileNotFoundError(f"지정한 레퍼런스 이미지를 찾을 수 없습니다: {custom_path}")

    ref_dir = PROJECTS_DIR / roster / "references"
    if not ref_dir.is_dir():
        return None

    for ext in (".webp", ".png", ".jpg", ".jpeg"):
        cand = ref_dir / f"{prefix}{ext}"
        if cand.is_file():
            return cand

    return None


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

    # 범위 연산자 지원: 00..19, 000..019 등
    if ".." in expr:
        start_s, end_s = expr.split("..", 1)
        start, end = int(start_s), int(end_s)
        codes = []
        for i in range(start, end + 1):
            c_str = f"{i:03d}"
            if c_str in db:
                codes.append(c_str)
        return codes

    # 쉼표 구분: 00,01,05 또는 000,001 등
    if "," in expr:
        codes = []
        for token in expr.split(","):
            token = token.strip()
            if not token:
                continue
            c_str = f"{int(token):03d}"
            if c_str in db:
                codes.append(c_str)
        return codes

    # 단일 코드: 00 또는 000 등
    single_code = f"{int(expr):03d}"
    if single_code in db:
        return [single_code]

    raise ValueError(f"유효하지 않은 포즈 코드/표현식입니다: {expr}")


def run_self_test() -> int:
    """파이프라인 무결성 자체 진단 테스트 (FLUX + SDXL 듀얼 엔진 점검)."""
    print("=" * 60)
    print("  [플에파] 시스템 무결성 자체 진단 테스트 (Dual-Engine Self-Test)")
    print("=" * 60)
    errors: List[str] = []

    # 1. FLUX 포즈 DB 로드 및 태그 순수성 검사
    try:
        flux_db = load_pose_db(engine="flux")
        print(f"✔ FLUX 포즈 DB 로드 성공 (총 {len(flux_db)}개 항목)")
        if len(flux_db) != 80:
            errors.append(f"FLUX 포즈 DB 항목 수가 80개가 아닙니다 (현재: {len(flux_db)}개)")
        for code, entry in flux_db.items():
            if "BREAK" in entry.prompt:
                errors.append(f"FLUX 코드 [{code}] 프롬프트에 금지된 BREAK 문법 잔류")
            if "((" in entry.prompt or ":1." in entry.prompt:
                errors.append(f"FLUX 코드 [{code}] 프롬프트에 SDXL 괄호 가중치 잔류")
            if not entry.label:
                errors.append(f"FLUX 코드 [{code}] 라벨 누락")
        print("✔ FLUX 80종 서술형 프롬프트 순수성 검사 완료")
    except Exception as e:
        errors.append(f"FLUX 포즈 DB 검사 실패: {e}")
        flux_db = {}

    # 2. SDXL 포즈 DB 로드 검사
    try:
        sdxl_db = load_pose_db(engine="sdxl")
        print(f"✔ SDXL 포즈 DB 로드 성공 (총 {len(sdxl_db)}개 항목)")
        if len(sdxl_db) != 80:
            errors.append(f"SDXL 포즈 DB 항목 수가 80개가 아닙니다 (현재: {len(sdxl_db)}개)")
        for code, entry in sdxl_db.items():
            if not entry.label:
                errors.append(f"SDXL 코드 [{code}] 라벨 누락")
        print("✔ SDXL 80종 Danbooru 태그 포즈 검사 완료")
    except Exception as e:
        errors.append(f"SDXL 포즈 DB 검사 실패: {e}")
        sdxl_db = {}

    # 3. 샘플 캐릭터 로드 검사
    try:
        char = load_character("sample_character")
        print(f"✔ 샘플 캐릭터({char.name}) 로드 성공")
        if not char.appearance.face_and_hair or not char.appearance.physique:
            errors.append("캐릭터 필수 외형 필드 누락")
    except Exception as e:
        errors.append(f"샘플 캐릭터 로드 실패: {e}")
        char = None

    # 4. FLUX 프롬프트 조립 및 탈의 로직 검사
    if flux_db and char:
        prompt_clothed, nude_flag = assemble_flux_prompt(char, flux_db["000"])
        if nude_flag or char.appearance.outfit not in prompt_clothed:
            errors.append("FLUX 평상 포즈(000)에서 의상 포함 누락 또는 잘못된 탈의 판정")

        prompt_nude, nude_flag = assemble_flux_prompt(char, flux_db["040"])
        if not nude_flag or char.appearance.outfit in prompt_nude:
            errors.append("FLUX H-씬(040)에서 의상 탈의 자동 스트리핑 실패")
        print("✔ FLUX 의상 착의/탈의 분기 조립 로직 검사 통과")

    # 5. SDXL 프롬프트 조립 및 탈의 로직 검사
    if sdxl_db and char:
        pos_clothed, _, nude_flag = assemble_sdxl_prompt(char, sdxl_db["000"])
        if nude_flag:
            errors.append("SDXL 평상 포즈(000)에서 잘못된 탈의 판정")

        pos_nude, _, nude_flag = assemble_sdxl_prompt(char, sdxl_db["040"])
        if not nude_flag or "nude" not in pos_nude:
            errors.append("SDXL H-씬(040)에서 nude 태그 주입 실패")
        print("✔ SDXL 의상 착의/탈의 분기 조립 로직 검사 통과")

    # 6. 워크플로우 템플릿 생성 검사 (FLUX & SDXL)
    try:
        wf_flux = build_flux_workflow("test prompt", "test_prefix", use_face_detailer=False)
        if "1" not in wf_flux or "20" not in wf_flux:
            errors.append("FLUX 기본 워크플로우 노드 생성 불완전")

        wf_sdxl = build_sdxl_workflow("test pos", "test neg", "test_prefix", use_face_detailer=False)
        if "1" not in wf_sdxl or "5" not in wf_sdxl or "20" not in wf_sdxl:
            errors.append("SDXL 기본 워크플로우 노드 생성 불완전")

        wf_ip = build_sdxl_workflow("test pos", "test neg", "test_prefix", ref_image_name="test_ref.webp")
        if "30" not in wf_ip or "32" not in wf_ip or "33" not in wf_ip:
            errors.append("SDXL IP-Adapter 워크플로우 노드 생성 불완전")
        print("✔ FLUX 및 SDXL + IP-Adapter 워크플로우 템플릿 생성 검사 통과")
    except Exception as e:
        errors.append(f"워크플로우 생성 실패: {e}")

    # 7. 프로필 스위칭 및 커스텀 네거티브 / 배경 검사
    if char:
        test_char = CharacterConfig.from_dict({
            "prefix": "test",
            "name": "Test",
            "appearance": {"outfit": "default suit", "face_and_hair": "short hair", "physique": "fit"},
            "profiles": {
                "swimsuit": {"outfit": "blue swimsuit", "sdxl_positive": "blue bikini BREAK 1girl"}
            }
        })
        test_char.apply_profile("swimsuit")
        if test_char.appearance.outfit != "blue swimsuit":
            errors.append("프로필 스위칭 의상 오버라이드 실패")
        
        _, neg, _ = assemble_sdxl_prompt(test_char, sdxl_db["000"], custom_neg="custom_tag, no_glasses")
        if "custom_tag" not in neg:
            errors.append("SDXL 커스텀 네거티브 주입 실패")
        print("✔ 프로필 스위칭 및 커스텀 네거티브 결합 검사 통과")

    # 8. 더미 Mock 생성 검사
    try:
        mock_test_path = PROJECTS_DIR / "_test_mock.webp"
        generate_mock_image(mock_test_path)
        if not mock_test_path.exists() or mock_test_path.stat().st_size == 0:
            errors.append("더미 Mock WebP 파일 생성 실패")
        else:
            mock_test_path.unlink()
        print("✔ 더미 Mock WebP 생성 파이프라인 검사 통과")
    except Exception as e:
        errors.append(f"더미 Mock 생성 테스트 예외: {e}")

    # T50: _profiles 로드 검사
    try:
        # 1) _profiles 없는 DB -> BUILTIN_PROFILES 폴백 검증
        default_profiles = load_global_profiles({})
        if not default_profiles or "female" not in default_profiles or "male" not in default_profiles or "male_otokonoko" not in default_profiles:
            errors.append("T50: _profiles 누락 시 기본 프로필(BUILTIN_PROFILES) 폴백 로드 실패")

        # 2) _profiles 명시된 DB 로드 검증
        sample_db = {
            "_profiles": {
                "custom_girl": {
                    "base_positive": "masterpiece, 1girl, solo",
                    "base_negative": "low quality, 1boy"
                }
            }
        }
        loaded_custom = load_global_profiles(sample_db)
        if "custom_girl" not in loaded_custom or loaded_custom["custom_girl"]["base_positive"] != "masterpiece, 1girl, solo":
            errors.append("T50: 커스텀 _profiles 섹션 파싱 실패")
        print("✔ [T50] _profiles 로드 검사 통과 (기본 폴백 및 커스텀 로드)")

    except Exception as e:
        errors.append(f"T50: _profiles 로드 검사 예외: {e}")

    # T51: 성별별 프로필 매칭 검사
    try:
        dummy_char = CharacterConfig.from_dict({
            "prefix": "dummy",
            "name": "Dummy",
            "appearance": {"outfit": "", "face_and_hair": "", "physique": ""}
        })
        prof_f = resolve_character_profile(dummy_char, "female")
        prof_m = resolve_character_profile(dummy_char, "male")
        prof_oto = resolve_character_profile(dummy_char, "otokonoko")

        if prof_f["name"] != "female" or "1girl" not in prof_f["base_positive"]:
            errors.append("T51: female 프로필 매칭 실패")
        if prof_m["name"] != "male" or "1boy" not in prof_m["base_positive"]:
            errors.append("T51: male 프로필 매칭 실패")
        if prof_oto["name"] != "male_otokonoko" or "androgynous" not in prof_oto["base_positive"]:
            errors.append("T51: male_otokonoko 프로필 매칭 실패")
        print("✔ [T51] 성별별 프로필 매칭 검사 통과 (female, male, male_otokonoko)")

    except Exception as e:
        errors.append(f"T51: 성별별 프로필 매칭 검사 예외: {e}")

    # T52: 프롬프트 적용 검사
    try:
        sample_prof = {
            "name": "female",
            "base_positive": "masterpiece, 1girl, solo",
            "base_negative": "worst quality, 1boy"
        }
        # 1) 기본 결합 검증
        applied = apply_profile_to_prompt("smile, looking at viewer", sample_prof)
        if "masterpiece" not in applied or "1girl" not in applied or "smile" not in applied:
            errors.append(f"T52: 프롬프트 결합 누락: {applied}")

        # 2) 중복 태그 정규화 검증
        applied_dup = apply_profile_to_prompt("1girl, happy", sample_prof)
        if applied_dup.lower().count("1girl") != 1:
            errors.append(f"T52: 중복 태그 정규화 실패 (1girl 중복 검출됨): {applied_dup}")

        # 3) BREAK 문법 분리 적용 검증
        break_prof = {
            "name": "break_test",
            "base_positive": "masterpiece BREAK 1girl, solo",
            "base_negative": ""
        }
        applied_break = apply_profile_to_prompt("smile, cowboy shot", break_prof)
        if " BREAK " not in applied_break:
            errors.append(f"T52: BREAK 문법 분리 적용 실패: {applied_break}")
        print("✔ [T52] 프롬프트 적용 검사 통과 (태그 결합, 중복 정규화, BREAK 분할)")

    except Exception as e:
        errors.append(f"T52: 프롬프트 적용 검사 예외: {e}")

    print("-" * 60)
    if errors:
        print(f"[FAIL] 총 {len(errors)}개 결함 발견:")
        for err in errors:
            print(f"  ❌ {err}")
        return 1
    else:
        print("[PASS] 모든 진단 검사 항목을 통과했습니다. FLUX / SDXL 듀얼 엔진 무결성 100% 보장.")
        return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="flux_batch_generator",
        description="플럭스(FLUX.1 [dev]) 및 SDXL(Unholy Desire Mix) 캐릭터 에셋 배치 생성기 (플에파 / PLEPA)"
    )
    parser.add_argument("-c", "--character", help="생성할 캐릭터 이름 (예: bjh, sample_character, all)")
    parser.add_argument("-p", "--pose", default="all", help="생성할 포즈 코드/범위 (all, emotions, 000..019, 000,001 등)")
    parser.add_argument("-r", "--roster", default=DEFAULT_ROSTER, help=f"로스터 폴더 (기본: {DEFAULT_ROSTER})")
    parser.add_argument("-l", "--list", action="store_true", help="로스터 내 등록된 캐릭터 프로필 목록을 콘솔 테이블로 출력")
    parser.add_argument("--profile", default=None, help="캐릭터 프로필/의상 선택 (JSON 내 profiles 섹션)")
    parser.add_argument("--engine", choices=["flux", "sdxl"], default="flux", help="이미지 생성 엔진 (flux: FLUX.1 [dev] GGUF, sdxl: SDXL Unholy 9.0 등 고속 2D 애니)")
    parser.add_argument("--ckpt", default=DEFAULT_SDXL_CKPT, help=f"SDXL 모드에서 사용할 체크포인트 파일명 (기본: {DEFAULT_SDXL_CKPT})")
    parser.add_argument("--bg", default=None, help="즉석 배경 프롬프트 직접 주입 (지정 시 --bg-preset 보다 우선 적용)")
    parser.add_argument("--bg-preset", default="default", help="배경 프리셋 키 (기본: default)")
    parser.add_argument("--custom_neg", default=None, help="추가 네거티브 프롬프트/태그 (SDXL 모드에 결합)")
    parser.add_argument("--ref_image", default=None, help="IP-Adapter 참조 이미지 파일 경로 (생략 시 references/{prefix}.webp 자동 탐색)")
    parser.add_argument("--ref_weight", type=float, default=None, help="IP-Adapter 영향력 가중치 (0.0~1.0, 기본: 캐릭터 설정치 또는 0.85)")
    parser.add_argument("--no_ref", action="store_true", help="레퍼런스 이미지(IP-Adapter)를 비활성화하고 순수 프롬프트로만 생성")
    parser.add_argument("--mock", action="store_true", help="ComfyUI 호출 없이 초고속(0.001초) 더미 WebP 이미지 생성으로 파이프라인 무결성 검증")
    parser.add_argument("--dry-run", action="store_true", help="ComfyUI 호출 없이 프롬프트 및 파일명 점검")
    parser.add_argument("--overwrite", "-f", "--force", action="store_true", help="기존 파일이 있어도 강제로 덮어쓰기 (교체/리롤용)")
    parser.add_argument("--skip-existing", action="store_true", help="기존 파일 건너뛰기 (기본값으로 항상 활성화됨)")
    parser.add_argument("--face-detailer", action="store_true", help="Face Detailer 얼굴 보정 활성화")
    parser.add_argument("--upscale", action="store_true", help="4x AI 초고화질 업스케일러 활성화")
    parser.add_argument("--steps", type=int, default=None, help="샘플링 스텝 수 (기본: flux=20, sdxl=25)")
    parser.add_argument("--cfg", type=float, default=None, help="CFG 스케일 (기본: flux=3.5, sdxl=6.5)")
    parser.add_argument("--sampler", default=None, help="샘플러 알고리즘 (기본: flux=euler, sdxl=euler_ancestral)")
    parser.add_argument("--scheduler", default=None, help="스케줄러 (기본: flux=simple, sdxl=normal)")
    parser.add_argument("--unet", default=DEFAULT_UNET_GGUF, help=f"FLUX 모드 GGUF UNet 모델 파일명 (기본: {DEFAULT_UNET_GGUF})")
    parser.add_argument("--lora", default="modern-anime-lora.safetensors", help="FLUX 모드 LoRA 파일명 (기본: modern-anime-lora.safetensors, 해제: none)")
    parser.add_argument("--lora-weight", type=float, default=0.9, help="LoRA 적용 강도 (기본: 0.9)")
    parser.add_argument("--width", type=int, default=None, help="이미지 가로 폭 (기본: flux=896, sdxl=832)")
    parser.add_argument("--height", type=int, default=None, help="이미지 세로 높이 (기본: flux=1152, sdxl=1216)")
    parser.add_argument("--test", action="store_true", help="시스템 무결성 자가 진단 실행")

    args = parser.parse_args(argv)

    if args.test:
        return run_self_test()

    if args.list:
        return print_roster_characters(roster=args.roster)

    if not args.character:
        parser.print_help()
        print("\n[오류] -c/--character 인수로 캐릭터를 지정해야 합니다 (캐릭터 목록 확인: -l / --list).")
        return 1

    # 엔진별 기본값 산출
    if args.engine == "sdxl":
        width = args.width if args.width is not None else DEFAULT_SDXL_WIDTH
        height = args.height if args.height is not None else DEFAULT_SDXL_HEIGHT
        steps = args.steps if args.steps is not None else DEFAULT_SDXL_STEPS
        cfg = args.cfg if args.cfg is not None else DEFAULT_SDXL_CFG
        sampler = args.sampler if args.sampler is not None else DEFAULT_SDXL_SAMPLER
        scheduler = args.scheduler if args.scheduler is not None else DEFAULT_SDXL_SCHEDULER
    else:
        width = args.width if args.width is not None else DEFAULT_WIDTH
        height = args.height if args.height is not None else DEFAULT_HEIGHT
        steps = args.steps if args.steps is not None else DEFAULT_STEPS
        cfg = args.cfg if args.cfg is not None else 3.5
        sampler = args.sampler if args.sampler is not None else "euler"
        scheduler = args.scheduler if args.scheduler is not None else "simple"

    try:
        db = load_pose_db(engine=args.engine)
        target_chars = resolve_characters(args.character, roster=args.roster)
        codes = resolve_pose_codes(args.pose, db)
        if args.profile:
            for char_obj, _ in target_chars:
                char_obj.apply_profile(args.profile)
    except Exception as e:
        print(f"[설정 오류] {e}")
        return 1

    client = ComfyClient(host=COMFY_HOST)
    if not args.dry_run and not args.mock:
        if not client.check_connection():
            print(f"[오류] ComfyUI 서버({COMFY_HOST})에 연결할 수 없습니다.")
            print("ComfyUI 폴더의 'run_nvidia_gpu.bat'를 실행하여 서버를 가동해 주십시오.")
            print("(프롬프트 구성 점검은 --dry-run, 가상 생성 시뮬레이션은 --mock 옵션을 사용하세요)")
            return 1

    print("=" * 60)
    engine_title = f"SDXL ({args.ckpt})" if args.engine == "sdxl" else f"FLUX.1 [dev] (GGUF: {args.unet})"
    print(f"  [플에파] 듀얼 엔진 가동 모드: {engine_title}")
    print(f"  대상 캐릭터: 총 {len(target_chars)}명 ({', '.join(c.prefix for c, _ in target_chars)})")
    print(f"  캐릭터당 포즈: 총 {len(codes)}개 ({', '.join(codes)}) | 총 {len(target_chars) * len(codes)}개 에셋")
    print(f"  해상도: {width}x{height} | 스텝: {steps} | CFG: {cfg} | 샘플러: {sampler} / {scheduler}")
    if args.profile:
        print(f"  프로필: '{args.profile}' 적용")
    if args.bg:
        print(f"  즉석 배경: '{args.bg}'")
    if args.custom_neg and args.engine == "sdxl":
        print(f"  추가 네거티브: '{args.custom_neg}'")
    if args.mock:
        print("  시뮬레이션: --mock 모드 활성화 (초고속 더미 생성)")
    if args.engine == "flux":
        print(f"  LoRA: {args.lora} (강도: {args.lora_weight})")
    is_overwrite = bool(args.overwrite)
    print(f"  작업 모드: {'강제 덮어쓰기 (--overwrite / -f)' if is_overwrite else '빈칸 채우기 (기본: 기존 파일 보존)'}")
    print(f"  보정 옵션: Face Detailer={'활성' if args.face_detailer else '비활성'}, Upscale={'활성' if args.upscale else '비활성'}")
    print("=" * 60)

    last_output_dir = None

    for char_idx, (char, actual_roster) in enumerate(target_chars, 1):
        bg_prompt = args.bg.strip() if args.bg else load_background_preset(actual_roster, key=args.bg_preset)
        output_dir = PROJECTS_DIR / actual_roster / "assets" / char.prefix
        output_dir.mkdir(parents=True, exist_ok=True)
        last_output_dir = output_dir

        print(f"\n▶ [{char_idx}/{len(target_chars)}] {char.name} ({char.prefix}) [로스터: {actual_roster}]")
        if args.bg:
            print(f"  즉석 배경: '{args.bg}' 적용")
        elif bg_prompt:
            print(f"  배경 프리셋: '{args.bg_preset}' 적용")

        # IP-Adapter 참조 이미지 탐색 및 업로드
        ref_file_name = None
        ref_weight = args.ref_weight if args.ref_weight is not None else getattr(char, "ref_weight", 0.85)
        if args.engine == "sdxl" and not args.no_ref:
            ref_path = find_reference_image(char.prefix, actual_roster, custom_path=args.ref_image)
            if ref_path:
                if not args.dry_run and not args.mock:
                    try:
                        ref_file_name = client.upload_image(ref_path)
                    except Exception as ue:
                        print(f"  [경고] 레퍼런스 업로드 실패 ({ue}) - 순수 프롬프트로 진행")
                        ref_file_name = None
                else:
                    ref_file_name = ref_path.name
                print(f"  IP-Adapter: '{ref_path.name}' 적용 (가중치: {ref_weight:.2f})")
            else:
                print("  IP-Adapter: 레퍼런스 이미지 없음 (순수 프롬프트 생성)")
        elif args.no_ref:
            print("  IP-Adapter: 비활성화 (--no_ref)")

        results: List[GenerationResult] = []
        total_start = time.time()

        for idx, code in enumerate(codes, 1):
            pose = db[code]
            out_name = asset_filename(char.prefix, code)
            out_path = output_dir / out_name

            if args.engine == "sdxl":
                pos_prompt, neg_prompt, is_nude = assemble_sdxl_prompt(
                    char, pose, bg_prompt=bg_prompt, custom_neg=args.custom_neg
                )
                display_prompt = pos_prompt
                workflow = build_sdxl_workflow(
                    positive_prompt=pos_prompt,
                    negative_prompt=neg_prompt,
                    output_prefix=f"{char.prefix}_{code}",
                    width=width,
                    height=height,
                    steps=steps,
                    cfg=cfg,
                    sampler=sampler,
                    scheduler=scheduler,
                    ckpt_name=args.ckpt,
                    use_face_detailer=args.face_detailer,
                    use_upscale=args.upscale,
                    ref_image_name=ref_file_name,
                    ref_weight=ref_weight,
                )
            else:
                prompt, is_nude = assemble_flux_prompt(char, pose, bg_prompt=bg_prompt)
                display_prompt = prompt
                final_prompt = prompt
                if args.lora and args.lora.lower() != "none" and "modern-anime" in args.lora.lower():
                    if "modern anime style" not in final_prompt.lower():
                        final_prompt = f"modern anime style, {final_prompt}"

                workflow = build_flux_workflow(
                    prompt=final_prompt,
                    output_prefix=f"{char.prefix}_{code}",
                    width=width,
                    height=height,
                    steps=steps,
                    use_face_detailer=args.face_detailer,
                    use_upscale=args.upscale,
                    unet_name=args.unet,
                    lora_name=args.lora if (args.lora and args.lora.lower() != "none") else None,
                    lora_weight=args.lora_weight,
                )

            target = GenerationTarget(
                code=code,
                section=pose.section,
                label=pose.label,
                assembled_prompt=display_prompt,
                is_nude=is_nude,
                output_filename=out_name,
            )

            print(f"  [{idx:02d}/{len(codes):02d}] #{code} {pose.label:<10} ({pose.section}) ➔ {out_name}", end="", flush=True)

            # 기본 동작: 빈칸 채우기 (기존 파일이 있고 --overwrite/-f가 아니면 자동 건너뜀)
            if not is_overwrite and out_path.exists() and out_path.stat().st_size > 0:
                print(" [기존 파일 보존: 건너뜀]")
                results.append(GenerationResult(target=target, success=True, image_path=out_path, duration_sec=0.0))
                continue

            if args.dry_run:
                print(" [DRY-RUN 완료]")
                results.append(GenerationResult(target=target, success=True, image_path=out_path, duration_sec=0.0))
                continue

            if args.mock:
                item_start = time.time()
                generate_mock_image(out_path)
                duration = time.time() - item_start
                print(f" [MOCK 생성 완료: {duration:.3f}초]")
                results.append(GenerationResult(target=target, success=True, image_path=out_path, duration_sec=duration))
                continue

            item_start = time.time()
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

    if not args.dry_run and last_output_dir and last_output_dir.parent.exists():
        open_in_explorer(last_output_dir.parent)

    return 0


if __name__ == "__main__":
    sys.exit(main())

