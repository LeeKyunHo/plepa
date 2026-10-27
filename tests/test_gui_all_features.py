# -*- coding: utf-8 -*-
"""
tests.test_gui_all_features
GUI의 모든 기능, 페이지 라우트, 서비스 계층의 무결성을 동적 계약(Contract-Driven)으로 전수 검사하는 스위트.
"""
import json
import unittest
from pathlib import Path

from plepa_engine.config import PROJECTS_DIR, THEMES_DIR
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.genit_exporter import default_genit_exporter
from plepa_engine.services.pose_service import default_pose_service


class TestGuiAllFeatures(unittest.TestCase):
    """PLEPA GUI 및 서비스 계층 전수 기능 동적 계약 검증."""

    def test_pose_db_has_all_theme_and_wuxia_codes(self):
        """data/themes/ 내 모든 테마 파일의 포즈 코드들이 포즈 DB 로드 시 100% 누락 없이 병합되는지 동적 검증."""
        db = default_pose_service.load_pose_db(engine="sdxl", roster="murim")
        theme_files = list(THEMES_DIR.glob("*.json"))
        self.assertGreater(len(theme_files), 0)

        for tf in theme_files:
            with open(tf, "r", encoding="utf-8") as f:
                t_data = json.load(f)
            for sec_name, sec_dict in t_data.items():
                if sec_name.startswith("_") or not isinstance(sec_dict, dict):
                    continue
                for raw_code, item in sec_dict.items():
                    if not isinstance(item, dict):
                        continue
                    code = default_pose_service.normalize_code(raw_code)
                    self.assertIn(code, db, f"테마 파일({tf.name})의 포즈 코드 {code}가 DB에 병합되지 않았습니다.")
                    effective_prompt = db[code].get_prompt("female") or db[code].prompt
                    self.assertGreater(len(effective_prompt), 0, f"{code} 프롬프트가 비어있습니다.")

    def test_pose_sets_integrity(self):
        """pose_sets.json에 등록된 모든 포즈 세트가 비어있지 않고 resolve_pose_codes() 호출 시 유효한 DB 코드만 반환하는지 동적 계약 검증."""
        sets = default_pose_service.load_pose_sets()
        self.assertGreater(len(sets), 0, "포즈 세트가 최소 1개 이상 존재해야 합니다.")

        # 전체 테마 및 캠퍼스/무협 이벤트가 포함된 통합 DB
        full_db = default_pose_service.load_pose_db(engine="sdxl", roster="campus")
        murim_db = default_pose_service.load_pose_db(engine="sdxl", roster="murim")
        spy_db = default_pose_service.load_pose_db(engine="sdxl", roster="spy")
        combined_db = {**full_db, **murim_db, **spy_db}

        for pset in sets:
            self.assertGreater(len(pset.codes), 0, f"포즈 세트 '{pset.id}'의 코드 목록이 비어있습니다.")
            resolved = default_pose_service.resolve_pose_codes(pset.id, combined_db)
            self.assertGreater(len(resolved), 0, f"포즈 세트 '{pset.id}' 해석 결과가 비어있습니다.")
            for code in resolved:
                self.assertIn(
                    code,
                    combined_db,
                    f"포즈 세트 '{pset.id}' 해석 결과에 미등록 코드 '{code}'가 포함되어 있습니다.",
                )

    def test_character_service_rosters(self):
        """모든 활성 로스터의 디스크 캐릭터 JSON 파일들과 character_service 조회 결과가 1:1로 일치하는지 동적 검증."""
        for roster in default_character_service.list_rosters():
            char_dir = PROJECTS_DIR / roster / "characters"
            if not char_dir.is_dir():
                continue
            disk_files = list(char_dir.glob("*.json"))
            loaded_chars = default_character_service.list_characters(roster=roster)
            self.assertEqual(
                len(loaded_chars),
                len(disk_files),
                f"[{roster}] 디스크 캐릭터 JSON 수({len(disk_files)})와 서비스 로드 수({len(loaded_chars)})가 일치해야 합니다.",
            )

    def test_asset_service_alphanumeric_mapping(self):
        """에셋 서비스가 영숫자 복합 포즈 코드(A00 등) 및 숫자 코드를 정상 파싱하고 매트릭스에 매핑하는지 검증."""
        assets_srh = default_asset_service.list_character_assets("srh", roster="spy")
        self.assertGreater(len(assets_srh), 0, "srh 캐릭터의 에셋 목록이 0개입니다.")

        first_code = assets_srh[0]["code"]
        matrix = default_asset_service.get_matrix_map(["srh"], [first_code], roster="spy")
        self.assertIn("srh", matrix)
        self.assertIn(first_code, matrix["srh"])

    def test_genit_exporter_code_resolution(self):
        """Genit 내보내기 코드 해석기가 2자리 대문자 코드를 올바르게 산출하는지 검증."""
        code_aa = default_genit_exporter.resolve_export_code("백설아", "aa")
        self.assertEqual(len(code_aa), 2)
        self.assertTrue(code_aa.isupper())

    def test_gui_pages_import_and_render_declarations(self):
        """GUI 모든 7개 페이지 모듈이 문법 오류 없이 정상 로드되고 렌더 함수를 보유하는지 검증."""
        import plepa_gui.pages.generate as p_gen
        import plepa_gui.pages.gallery as p_gal
        import plepa_gui.pages.characters as p_char
        import plepa_gui.pages.poses as p_pos
        import plepa_gui.pages.pose_sets as p_sets
        import plepa_gui.pages.backgrounds as p_bg
        import plepa_gui.pages.settings as p_set

        self.assertTrue(callable(getattr(p_gen, "render_generate_page", None)))
        self.assertTrue(callable(getattr(p_gal, "render_gallery_page", None)))
        self.assertTrue(callable(getattr(p_char, "render_characters_page", None)))
        self.assertTrue(callable(getattr(p_pos, "render_poses_page", None)))
        self.assertTrue(callable(getattr(p_sets, "render_pose_sets_page", None)))
        self.assertTrue(callable(getattr(p_bg, "render_backgrounds_page", None)))
        self.assertTrue(callable(getattr(p_set, "render_settings_page", None)))

    def test_gui_poses_page_tabs_and_sections_sync(self):
        """GUI 포즈 페이지의 SECTION_LABELS와 실제 포즈 DB 및 pose_service.SECTION_NAMES 간의 동기화 무결성 검증."""
        from plepa_engine.services.pose_service import SECTION_NAMES
        from plepa_gui.pages.poses import SECTION_LABELS

        for sec in SECTION_NAMES:
            self.assertIn(sec, SECTION_LABELS, f"포즈 서비스의 섹션 '{sec}'이 poses.py의 SECTION_LABELS에 누락되었습니다.")

        for engine in ("flux", "sdxl"):
            db = default_pose_service.load_pose_db(engine=engine)
            db_sections = {e.section for e in db.values() if e.section}
            for sec in db_sections:
                self.assertIn(sec, SECTION_NAMES, f"[{engine}] 포즈 DB의 섹션 '{sec}'이 pose_service.SECTION_NAMES에 등록되지 않았습니다.")
                self.assertIn(sec, SECTION_LABELS, f"[{engine}] 포즈 DB의 섹션 '{sec}'이 poses.py의 SECTION_LABELS에 누락되었습니다.")

    def test_all_poses_details_rendering_safety(self):
        """DB에 등록된 모든 포즈의 get_pose_details() 조회가 예외 없이 100% 성공하는지 전수 검증."""
        for engine in ("flux", "sdxl"):
            db = default_pose_service.load_pose_db(engine=engine)
            self.assertGreater(len(db), 0, f"[{engine}] 포즈 DB가 비어있습니다.")
            for code in db:
                try:
                    details = default_pose_service.get_pose_details(code)
                    self.assertEqual(details["code"], code)
                    self.assertIn("flux_prompt", details)
                    self.assertIn("sdxl_prompt", details)
                except Exception as ex:
                    self.fail(f"[{engine}] 포즈 코드 '{code}' 상세 조회 중 예외 발생: {ex}")

    def test_active_sections_dynamic_metadata_contract(self):
        """get_active_sections()가 활성 섹션의 카운트와 라벨을 메타데이터와 결합하여 정상 반환하는지 검증."""
        actives = default_pose_service.get_active_sections(engine="sdxl")
        self.assertGreaterEqual(len(actives), 4, "최소 4개 이상의 활성 섹션이 반환되어야 합니다.")

        from plepa_engine.services.pose_service import SECTION_METADATA
        orders = [SECTION_METADATA[s["id"]]["order"] for s in actives]
        self.assertEqual(orders, sorted(orders), "활성 섹션 정렬 순서가 메타데이터 order와 일치하지 않습니다.")


if __name__ == "__main__":
    unittest.main()
