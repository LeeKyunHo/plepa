"""
update_assets_to_illustrious.py
Illustrious-XL / Meichi IL-ust MIX V1에 맞춘 포즈 DB 및 캐릭터 JSON 전수 베스트 프랙티스 최적화.
1. 퀄리티 태그 정규화: 'masterpiece, best quality, very aesthetic, absurdres, newest'
2. 네거티브 프롬프트 다이어트: 2D 선화 파괴 태그(flat color, thick lineart, paint, 3d 등) 제거
3. 과도한 괄호 및 가중치(1.35) 정규화 (최대 1.15)
4. man 로스터 7개 캐릭터 JSON 규격화 (sdxl_positive/negative, ref_weight 0.5)
5. sdxl_pose_database.json의 구형 가중치 및 배경 태그 정제
"""

import json
import re
from pathlib import Path
from plepa_engine.config import configure_stdio

configure_stdio()

ROOT_DIR = Path(__file__).resolve().parent

IL_QUALITY = "masterpiece, best quality, very aesthetic, absurdres, newest"

# Illustrious 표준 베스트 프랙티스 공통 네거티브
IL_NEG_BASE = (
    "lowres, worst quality, bad quality, bad anatomy, bad proportions, bad hands, "
    "missing fingers, extra digits, deformed, jpeg artifacts, signature, watermark, "
    "username, artist name, blurry, 1boy, male, (comic:1.2), (multiple views:1.2), (panel layout:1.2)"
)

IL_NEG_OTOKONOKO_BASE = (
    "lowres, worst quality, bad quality, bad anatomy, bad proportions, bad hands, "
    "missing fingers, extra digits, deformed, jpeg artifacts, signature, watermark, "
    "username, artist name, blurry, 1girl, female, (comic:1.2), (multiple views:1.2), (panel layout:1.2)"
)


def normalize_prompt_weights(text: str, max_weight: float = 1.15) -> str:
    """1.15 초과 가중치 클램핑 및 다중 괄호 단일화."""
    if not text:
        return ""

    def _clamp(m):
        w = float(m.group(1))
        return f":{min(w, max_weight):.2f}"

    res = re.sub(r":([0-9]+\.[0-9]+)", _clamp, text)
    # ((태그)) -> (태그)
    res = re.sub(r"\({2,}", "(", res)
    res = re.sub(r"\){2,}", ")", res)
    # 연속 쉼표 정리
    res = re.sub(r"\s*,\s*", ", ", res).strip(", ")
    return res


def optimize_character_json(char_path: Path, is_otokonoko: bool = False, custom_avoid: str = ""):
    with open(char_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. 포지티브 프롬프트 추출 및 퀄리티 태그 정규화
    raw_pos = data.get("sdxl_positive") or data.get("positive") or ""
    if " BREAK " in raw_pos:
        q_chunk, char_chunk = raw_pos.split(" BREAK ", 1)
        norm_char_chunk = normalize_prompt_weights(char_chunk)
        new_pos = f"{IL_QUALITY} BREAK {norm_char_chunk}"
    else:
        norm_pos = normalize_prompt_weights(raw_pos)
        new_pos = f"{IL_QUALITY} BREAK {norm_pos}"

    # 2. 네거티브 프롬프트 정규화
    base_neg = IL_NEG_OTOKONOKO_BASE if is_otokonoko else IL_NEG_BASE
    if custom_avoid:
        norm_avoid = normalize_prompt_weights(custom_avoid)
        new_neg = f"{base_neg}, {norm_avoid}"
    else:
        new_neg = base_neg

    new_neg = re.sub(r"\s*,\s*", ", ", new_neg).strip(", ")

    # 3. 데이터 갱신 및 키 정규화
    data["sdxl_positive"] = new_pos
    data["sdxl_negative"] = new_neg
    data["ref_weight"] = 0.5

    # 구형 키 제거
    data.pop("positive", None)
    data.pop("negative", None)

    with open(char_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✔ [{char_path.name}] Illustrious XL 베스트 프랙티스 적용 완료")


def main():
    print("============================================================")
    print("  Illustrious-XL / Meichi 베스트 프랙티스 일괄 적용 시작")
    print("============================================================\n")

    # ── 1. don 로스터 캐릭터 6종 최적화 ──
    don_dir = ROOT_DIR / "projects" / "don" / "characters"
    don_avoids = {
        "bjh.json": "(white dress, light-colored dress:1.15), hair down, short hair, bob cut, dark hair, brunette, covered underboob, pants, jeans",
        "jhy.json": "(white clothes, light-colored outfit:1.15), long hair, ponytail, twin tails, red hair, blonde hair, pants, jeans, shorts",
        "ksn.json": "(black dress, dark clothes:1.15), short hair, ponytail, bun, dark hair, blonde hair, pants, jeans",
        "oes.json": "(dark dress, black dress:1.15), short hair, long hair down, ponytail, twintails, blonde hair, colored hair, pants, jeans",
        "sce.json": "(dark skin, pale skin:1.15), dark hair, black hair, blonde hair, short hair, bob cut, pants, jeans",
        "shn.json": "large breasts, huge breasts, cleavage, muscular, bulky, manly, beard, mustache, (skirt, dress:1.2), (bare legs, exposed thighs:1.15), jewelry",
    }
    for filename, avoid in don_avoids.items():
        p = don_dir / filename
        if p.exists():
            is_otoko = (filename == "shn.json")
            optimize_character_json(p, is_otokonoko=is_otoko, custom_avoid=avoid)

    # ── 2. man 로스터 캐릭터 7종 최적화 ──
    man_dir = ROOT_DIR / "projects" / "man" / "characters"
    man_avoids = {
        "bge.json": "blonde hair, short hair, skirt, dress, loose pants, cat ears, animal ears",
        "cyr.json": "dark skin, short haircut, black hair, pants, leather, formal suit, cat ears, animal ears",
        "hsh.json": "short hair, black hair, dark hair, casual t-shirt, jeans, pants, sneakers, cat ears, animal ears",
        "kma.json": "dark hair, black hair, casual clothes, t-shirt, jeans, sneakers, flat chest, cat ears, animal ears",
        "lhe.json": "long hair down, ponytail, neat dress, colorful dress, pastel clothes, cat ears, animal ears",
        "sja.json": "short hair, ponytail, casual wear, jeans, t-shirt, bright dress, cat ears, animal ears",
        "yca.json": "short hair, blonde hair, black hair, casual t-shirt, jeans, pants, sneakers, cat ears, animal ears",
    }
    for filename, avoid in man_avoids.items():
        p = man_dir / filename
        if p.exists():
            optimize_character_json(p, is_otokonoko=False, custom_avoid=avoid)

    # ── 3. sdxl_pose_database.json 포즈 DB 최적화 ──
    pose_db_path = ROOT_DIR / "sdxl_pose_database.json"
    if pose_db_path.exists():
        with open(pose_db_path, "r", encoding="utf-8") as f:
            pdb = json.load(f)

        for sec in ["emotions", "poses", "h_scenes", "scenes_otokonoko"]:
            for code, item in pdb.get(sec, {}).items():
                prompt = item.get("prompt", "")
                norm_prompt = normalize_prompt_weights(prompt, max_weight=1.15)
                # 'simple clean background' -> 'clean background'로 통일하여 배경 치환 정상화
                norm_prompt = norm_prompt.replace("simple clean background", "clean background")
                item["prompt"] = norm_prompt

        with open(pose_db_path, "w", encoding="utf-8") as f:
            json.dump(pdb, f, ensure_ascii=False, indent=2)

        print("✔ [sdxl_pose_database.json] 80종 포즈 가중치 및 배경 태그 정규화 완료")

    print("\n============================================================")
    print("  [완료] Illustrious-XL / Meichi 베스트 프랙티스 전체 적용 완료!")
    print("============================================================")


if __name__ == "__main__":
    main()
