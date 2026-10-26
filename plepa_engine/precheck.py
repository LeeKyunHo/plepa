"""
plepa_engine.precheck
이미지 배치 생산 전 캐릭터 JSON, 포즈 DB 제작 규칙, 착의 의상 고정 및 H씬 알몸 전환 무결성을 전수 검증하는 모듈.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

from plepa_engine.config import PROJECTS_DIR
from plepa_engine.prompt_builder import (
    assemble_sdxl_prompt,
    resolve_pose_outfit_slot,
)
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.pose_service import default_pose_service


@dataclass
class PrecheckReport:
    roster: str
    total_characters: int = 0
    total_poses: int = 0
    total_combinations_checked: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0


# 캐릭터별 기본 착의(default) 고유 시그니처 의상 핵심 키워드 (spy 로스터 기준, 타 로스터는 appearance.outfit에서 자동 추출)
_SIGNATURE_OUTFIT_TOKENS: Dict[str, Tuple[str, ...]] = {
    # spy 로스터
    "kzk": ("doctor coat", "halter bikini top", "garter belt"),
    "chl": ("cheongsam qipao", "gold embroidery", "high side slits"),
    "rvn": ("collared shirt", "loose black necktie", "micro pencil skirt"),
    "dom": ("black lace robe", "crimson", "micro corset"),
    "evl": ("nurse cap", "nurse uniform mini dress", "white thighhighs"),
    "srh": ("bunny suit", "bolero jacket", "black bunny ears"),
    "vic": ("white silk blouse", "navy corset vest", "black pencil skirt"),
    "cla": ("collared blouse", "slate-navy blue corset vest", "micro pencil skirt"),
    "viv": ("collared blouse", "leather shoulder holster", "garter straps"),
    "scl": ("cropped leather jacket", "buckle strap across chest", "leather micro shorts"),
    # campus 로스터
    "aya": ("dress shirt", "shorts"),
    "har": ("knit cardigan", "skirt"),
    "kao": ("black dress", "denim jacket"),
    "mai": ("lab coat", "sweater"),
    "shz": ("sweatshirt", "hotpants"),
    "yur": ("knit top", "miniskirt"),
    # ykn 로스터
    "hay": ("button-up blouse", "pleated skirt"),
    "ser": ("knit cardigan", "blouse", "pleated skirt"),
    "sia": ("trench jacket", "collared blouse", "pleated skirt"),
    "yua": ("knit cardigan", "collared blouse", "pleated skirt"),
}
_SPY_SIGNATURE_OUTFIT_TOKENS = _SIGNATURE_OUTFIT_TOKENS

# 탈의(nude) 및 테마 스왑 시 캐릭터 본체 파트(BREAK 뒷단)에 절대 남아있으면 안 되는 기본 의상 키워드
_FORBIDDEN_LEAK_TOKENS_IN_NUDE: Tuple[str, ...] = (
    "doctor coat",
    "cheongsam",
    "qipao",
    "loose black necktie",
    "micro pencil skirt",
    "pencil skirt",
    "black lace robe",
    "nurse cap",
    "nurse uniform",
    "bolero jacket",
    "navy corset vest",
    "slate-navy blue corset vest",
    "leather shoulder holster",
    "cropped leather jacket",
    "leather micro shorts",
    "ankle boots",
)


def run_pregeneration_check(roster: str = "campus") -> PrecheckReport:
    """지정된 로스터와 SDXL V2 포즈 DB에 대해 5단계 이미지 생산 사전 점검을 수행합니다."""
    report = PrecheckReport(roster=roster)

    sdxl_db = default_pose_service.load_pose_db(engine="sdxl", roster=roster)
    report.total_poses = len(sdxl_db)

    # -------------------------------------------------------------------------
    # [1단계] 포즈 DB 제작 규칙 준수 전수 검사 (SDXL V2 단일 파이프라인)
    # -------------------------------------------------------------------------
    for code, entry in sdxl_db.items():
        # 1-1. 라벨 규격 (2~15글자)
        if not (2 <= len(entry.label) <= 15):
            report.errors.append(
                f"[포즈규칙] sdxl:{code} 라벨 길이 규격 위반 ({entry.label!r}, 길이={len(entry.label)})"
            )
        # 1-2. 상세 연출 설명(description) 필수
        if not entry.description or len(entry.description.strip()) < 5:
            report.errors.append(f"[포즈규칙] sdxl:{code} description 누락 또는 너무 짧음")

        # 1-3. 프롬프트 내 금지어 및 충돌 태그 검사
        for field_name, p_field in (
            ("prompt", entry.prompt),
            ("prompt_female", entry.prompt_female),
            ("prompt_otokonoko", entry.prompt_otokonoko),
        ):
            if not p_field:
                continue
            low = p_field.lower()
            for bad in (
                "introduction pose",
                "blank face",
                "featureless face",
                "mermaid",
                "fishtail",
                "chandelier",
                "curtains",
                "pulling collar down",
                "bra strap",
            ):
                if re.search(r"\b" + re.escape(bad) + r"\b", low):
                    report.errors.append(f"[포즈규칙] sdxl:{code} ({field_name}) 금지어 포함 ({bad!r})")
            if "parted lips" in low and "puckered lips" in low:
                report.errors.append(
                    f"[포즈규칙] sdxl:{code} ({field_name}) 구강 왜곡 유발 동시 사용 (parted lips + puckered lips)"
                )

            # 오토코노코 전용 섹션 또는 prompt_otokonoko 필드에 1girl 포함 금지
            if entry.section == "scenes_otokonoko" or field_name == "prompt_otokonoko":
                if re.search(r"\b1girl\b", low):
                    report.errors.append(
                        f"[포즈규칙] sdxl:{code} ({field_name}) 오토코노코 프롬프트 내 1girl 하드코딩 금지 위반"
                    )
            # 공용 섹션에서 prompt_otokonoko 분기가 없는데 기본 prompt에 1girl이 하드코딩된 경우 금지
            elif entry.section in ("emotions", "poses", "romance", "spy_actions", "wuxia_actions"):
                if field_name == "prompt" and not entry.prompt_otokonoko and re.search(r"\b1girl\b", low):
                    report.errors.append(
                        f"[포즈규칙] sdxl:{code} 공용 섹션({entry.section}) 내 prompt_otokonoko 분기 없이 1girl 하드코딩 금지 위반"
                    )

    # -------------------------------------------------------------------------
    # [2단계] 캐릭터 JSON 외형·비율·가중치·슬롯 무결성 검사
    # -------------------------------------------------------------------------
    chars = default_character_service.list_characters(roster=roster)
    report.total_characters = len(chars)
    if not chars:
        report.errors.append(f"[캐릭터규칙] 로스터 '{roster}'에 등록된 캐릭터가 없습니다.")
        return report

    bg_file = PROJECTS_DIR / roster / "background.json"
    if bg_file.exists():
        bg_raw = json.loads(bg_file.read_text(encoding="utf-8"))
        default_sdxl_bg = bg_raw.get("presets", {}).get("default", {}).get("sdxl", "").lower()
        for bad_bg in ("chandelier", "ceiling", "sofa", "couch", "curtains", "drapes"):
            if re.search(r"\b" + re.escape(bad_bg) + r"\b", default_sdxl_bg):
                report.errors.append(
                    f"[배경규칙] {roster}/background.json default 프리셋에 전신 스케일 왜곡 유발 어휘 포함 ({bad_bg!r})"
                )

    for _, char, char_path in chars:
        pfx = char.prefix
        pos = char.sdxl_positive or ""
        nude_pos = getattr(char, "sdxl_nude_positive", "") or ""
        neg = char.sdxl_negative or ""

        if " BREAK " not in pos:
            report.errors.append(f"[캐릭터규칙] {pfx}: sdxl_positive에 ' BREAK ' 구분자 누락")
        if not nude_pos or " BREAK " not in nude_pos:
            report.errors.append(f"[캐릭터규칙] {pfx}: sdxl_nude_positive 누락 또는 ' BREAK ' 구분자 누락")

        if "long slender limbs" in pos.lower() or "long slender limbs" in nude_pos.lower():
            report.errors.append(f"[캐릭터규칙] {pfx}: 9~10등신 기형 유발 태그 'long slender limbs' 잔류")

        for bad_char in (
            "holding ",
            "syringe",
            "cigarette holder",
            "folder",
            "front tie",
            "front button",
            "wrap front",
            "front cleavage",
            "exposed cleavage",
            "heavy cleavage",
            "mermaid",
            "clean background",
            "soft lighting",
        ):
            if bad_char in pos.lower() or bad_char in nude_pos.lower():
                report.errors.append(f"[캐릭터규칙] {pfx}: 캐릭터 JSON 금지어 포함 ({bad_char!r})")

        for bad_neg in ("sweat,", "liquid", "splatter"):
            if bad_neg in neg.lower():
                report.errors.append(f"[캐릭터규칙] {pfx}: sdxl_negative에 체액 차단 금지어 포함 ({bad_neg!r})")

        # ---------------------------------------------------------------------
        # [3~5단계] 전 포즈 조립 시뮬레이션: 착의 고정 / H씬 알몸 전환 / 테마 의상 격리
        # ---------------------------------------------------------------------
        sig_tokens = _SPY_SIGNATURE_OUTFIT_TOKENS.get(pfx)
        if sig_tokens is None:
            outfit_desc = getattr(char.appearance, "outfit", "") or ""
            if not outfit_desc and char.sdxl_positive and " BREAK " in char.sdxl_positive:
                outfit_desc = char.sdxl_positive.split(" BREAK ")[1]
            extracted = [t.strip().translate(str.maketrans("", "", "()[]{}")).split(":")[0] for t in outfit_desc.split(",") if len(t.strip()) > 3]
            sig_tokens = tuple(extracted[:3])
        for code, pose in sdxl_db.items():
            report.total_combinations_checked += 1
            slot = resolve_pose_outfit_slot(pose)
            pos_out, neg_out, is_nude = assemble_sdxl_prompt(char, pose)

            # BREAK 뒷단(캐릭터 본체 파트) 분리
            char_chunk = pos_out.split(" BREAK ")[1].lower() if " BREAK " in pos_out else pos_out.lower()

            if slot == "default":
                # [3단계] 착의 씬: 고유 의상 핵심 키워드가 100% 고정 유지되는지 확인
                if is_nude:
                    report.errors.append(f"[착의고정] {pfx}:{code} default 슬롯인데 is_nude=True 반환")
                for tok in sig_tokens:
                    if tok.lower() not in char_chunk:
                        report.errors.append(
                            f"[착의고정] {pfx}:{code} 착의 씬에서 고유 의상 토큰 누락 ({tok!r})"
                        )
                if "completely nude" in char_chunk:
                    report.errors.append(f"[착의고정] {pfx}:{code} 착의 씬에 completely nude 오주입")

            elif slot == "nude":
                # [4단계] 탈의/H씬: 기본 의상 태그 0% 잔류 + 알몸 태그 주입 + [패치 A] 네거티브 주입 확인
                if not is_nude:
                    report.errors.append(f"[알몸전환] {pfx}:{code} nude 슬롯인데 is_nude=False 반환")
                if "nude, completely nude" not in pos_out.lower():
                    report.errors.append(f"[알몸전환] {pfx}:{code} 긍정 프롬프트에 'nude, completely nude' 누락")
                for leak in _FORBIDDEN_LEAK_TOKENS_IN_NUDE:
                    if leak in char_chunk:
                        report.errors.append(
                            f"[알몸전환] {pfx}:{code} H씬/탈의 프롬프트에 기본 의상 잔류 ({leak!r})"
                        )
                if "(clothes:1.25)" not in neg_out.lower() and "(clothes:1.35)" not in neg_out.lower():
                    report.errors.append(f"[알몸전환] {pfx}:{code} 부정 프롬프트에 [패치 A] 의상 차단 태그 누락")

            else:
                # [5단계] 테마 의상 스왑(swimsuit, bunny, maid, bdsm, underwear, combat, wedding)
                if is_nude:
                    report.errors.append(f"[테마스왑] {pfx}:{code} 테마 슬롯({slot})인데 is_nude=True 반환")
                # 기본 의상이 테마 슬롯(combat 제외)에 잔류하지 않는지 확인
                if slot != "combat":
                    for leak in ("doctor coat", "cheongsam", "nurse uniform", "cropped leather jacket"):
                        if leak in char_chunk:
                            report.errors.append(
                                f"[테마스왑] {pfx}:{code} ({slot}) 프롬프트에 기본 의상 잔류 ({leak!r})"
                            )

    # -------------------------------------------------------------------------
    # [6단계] 로스터별 포즈 배경 매핑(pose_background_mapping.json) 무결성 검사
    # -------------------------------------------------------------------------
    mapping_file = PROJECTS_DIR / roster / "pose_background_mapping.json"
    if mapping_file.exists():
        try:
            map_data = json.loads(mapping_file.read_text(encoding="utf-8"))
            default_bg_key = map_data.get("default_background", "default")

            valid_bg_keys = set()
            if bg_file.exists():
                bg_raw = json.loads(bg_file.read_text(encoding="utf-8"))
                valid_bg_keys = set(bg_raw.keys())
                if "presets" in bg_raw:
                    valid_bg_keys.update(bg_raw["presets"].keys())

            if valid_bg_keys and default_bg_key not in valid_bg_keys:
                report.errors.append(
                    f"[배경매핑규칙] {roster}/pose_background_mapping.json의 default_background '{default_bg_key}'가 background.json에 정의되어 있지 않습니다."
                )

            pose_maps = map_data.get("pose_mappings", {})
            for code_pattern, mapped_bg in pose_maps.items():
                if mapped_bg not in ("none", "auto") and valid_bg_keys and mapped_bg not in valid_bg_keys:
                    report.errors.append(
                        f"[배경매핑규칙] {roster} 포즈 대역 '{code_pattern}'에 매핑된 배경 '{mapped_bg}'가 background.json에 실존하지 않습니다."
                    )
        except Exception as e:
            report.errors.append(f"[배경매핑규칙] {roster}/pose_background_mapping.json 파싱 실패: {e}")

    return report


if __name__ == "__main__":
    import argparse
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="플에파 이미지 생산 사전 점검기 (Pre-Generation Validator)")
    parser.add_argument("-r", "--roster", default="spy", help="점검할 로스터 이름 (기본값: spy)")
    args = parser.parse_args()

    rep = run_pregeneration_check(args.roster)
    print("=" * 68)
    print(f"  [플에파] 이미지 생산 6단계 사전 점검 보고서 (로스터: {rep.roster})")
    print("=" * 68)
    print(f"• 점검 캐릭터 수 : {rep.total_characters}명")
    print(f"• 점검 포즈 DB 수: {rep.total_poses}종 (SDXL V2)")
    print(f"• 조립 시뮬레이션: 총 {rep.total_combinations_checked}개 조합 (착의 고정 / H씬 알몸 전환 / 테마 스왑)")
    print("-" * 68)
    if rep.passed:
        print("✔ [PASS] 위반 사항 0건! 모든 캐릭터와 포즈가 이미지 생산 표준을 100% 준수합니다.")
        sys.exit(0)
    else:
        print(f"❌ [FAIL] 총 {len(rep.errors)}건의 규칙 위반이 감지되었습니다:")
        for err in rep.errors:
            print(f"  - {err}")
        sys.exit(1)
