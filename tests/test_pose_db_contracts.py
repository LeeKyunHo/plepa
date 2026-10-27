"""
tests/test_pose_db_contracts.py
포즈 데이터베이스(sdxl_pose_database.json) 및 로스터 이벤트(events.json)의
스키마 무결성과 POSE_MAPPING.md 문서 동기화(Pose Mapping Sync Rule)를 상시 보증하는 헌법 계약 테스트.
"""

import json
from pathlib import Path
from plepa_engine.config import PROJECTS_DIR, ROOT_DIR, SDXL_POSE_DB_PATH
from plepa_engine.services.pose_service import SECTION_METADATA, default_pose_service

ALLOWED_OUTFIT_SLOTS = {
    "",
    "default",
    "nude",
    "wedding",
    "swimsuit",
    "bunny",
    "bdsm",
    "maid",
    "combat",
    "office",
    "doctor",
    "hanfu",
    "coat",
    "suit",
    "underwear",
}


def test_core_pose_db_schema_contract():
    """코어 포즈 DB의 모든 포즈가 필수 필드(label, description, prompt)와 유효한 의상 슬롯을 갖추었는지 검증."""
    with open(SDXL_POSE_DB_PATH, "r", encoding="utf-8") as f:
        raw_db = json.load(f)

    total_checked = 0
    for sec_name, sec_dict in raw_db.items():
        if sec_name.startswith("_") or not isinstance(sec_dict, dict):
            continue
        assert sec_name in SECTION_METADATA, f"미등록 섹션 '{sec_name}'이 DB에 존재합니다."

        for code, pdata in sec_dict.items():
            assert isinstance(pdata, dict), f"[{sec_name}/{code}] 포즈 데이터가 dict가 아닙니다."
            label = pdata.get("label", "").strip()
            prompt = pdata.get("prompt", "").strip()
            desc = pdata.get("description", "").strip()

            assert label, f"[{sec_name}/{code}] label이 비어있습니다."
            assert prompt, f"[{sec_name}/{code}] prompt가 비어있습니다."
            assert desc, f"[{sec_name}/{code}] description이 비어있습니다."

            outfit = pdata.get("required_outfit", "")
            assert outfit in ALLOWED_OUTFIT_SLOTS, (
                f"[{sec_name}/{code}] 허용되지 않은 required_outfit 슬롯: '{outfit}'"
            )

            for meta_key in ("legacy_labels", "aliases"):
                if meta_key in pdata:
                    assert isinstance(pdata[meta_key], list), f"[{sec_name}/{code}] {meta_key}는 list여야 합니다."
                    assert all(isinstance(x, str) and x.strip() for x in pdata[meta_key]), (
                        f"[{sec_name}/{code}] {meta_key}의 모든 원소는 비어있지 않은 문자열이어야 합니다."
                    )

            total_checked += 1

    assert total_checked >= 150, f"검사된 코어 포즈 수가 비정상적으로 적습니다: {total_checked}"


def test_roster_events_schema_contract():
    """모든 로스터의 events.json이 유효한 스키마와 필수 필드를 준수하는지 동적 검증."""
    for event_file in sorted(PROJECTS_DIR.glob("*/events.json")):
        with open(event_file, "r", encoding="utf-8") as f:
            ev_data = json.load(f)

        for sec_name, sec_dict in ev_data.items():
            if sec_name.startswith("_") or not isinstance(sec_dict, dict):
                continue
            for code, pdata in sec_dict.items():
                assert isinstance(pdata, dict)
                assert pdata.get("label", "").strip(), f"[{event_file.parent.name}/{code}] label 누락"
                assert pdata.get("prompt", "").strip(), f"[{event_file.parent.name}/{code}] prompt 누락"


def test_pose_mapping_md_sync_contract():
    """
    GEMINI.md 포즈 매핑 문서 실시간 동기화 원칙(Pose Mapping Sync Rule) 자동 검증:
    코어 DB의 주요 포즈 코드(000~127)가 루트 POSE_MAPPING.md에 누락 없이 기재되어 있는지 확인.
    """
    mapping_md_path = ROOT_DIR / "POSE_MAPPING.md"
    assert mapping_md_path.is_file(), "루트에 POSE_MAPPING.md가 존재해야 합니다."
    md_text = mapping_md_path.read_text(encoding="utf-8")

    db = default_pose_service.load_pose_db(engine="sdxl")
    missing_in_doc = []
    for code, entry in sorted(db.items()):
        if not code.isdigit():
            continue
        c_int = int(code)
        if 0 <= c_int <= 127:
            if f"`{code}`" not in md_text and f"{code}_" not in md_text:
                missing_in_doc.append(f"{code}_{entry.label}")

    assert len(missing_in_doc) == 0, (
        "POSE_MAPPING.md에 누락된 코어 포즈가 있습니다:\n" + ", ".join(missing_in_doc)
    )
