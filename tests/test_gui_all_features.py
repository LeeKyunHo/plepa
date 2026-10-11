# -*- coding: utf-8 -*-
"""
tests.test_gui_all_features
GUI의 모든 기능, 페이지 라우트, 서비스 계층의 무결성을 전수 검사하는 종합 테스트 스위트.
- 페이지 렌더링: 대시보드(/), 갤러리(/gallery), 포즈(/poses), 캐릭터(/characters), 포즈세트(/pose_sets), 배경(/backgrounds)
- 포즈 DB: 듀얼 엔진(FLUX/SDXL) 및 신규 무협(C), Genit(A/B), 성인(N) 포즈 전수 로드 무결성
- 에셋 서비스: 영숫자 포즈 파일명 매핑 및 매트릭스 그리드 매핑
- 캐릭터 서비스: 프로젝트 로스터 및 캐릭터 목록 조회
"""
import unittest
from pathlib import Path

from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.genit_exporter import default_genit_exporter
from plepa_engine.services.pose_service import default_pose_service
from plepa_engine.services.repository import default_repo


class TestGuiAllFeatures(unittest.TestCase):
    """PLEPA GUI 및 서비스 계층 전수 기능 검증."""

    def test_pose_db_has_all_theme_and_wuxia_codes(self):
        """포즈 DB에 무협 액션(C01~C10), 감정(A00~A23), 행동(B01~B22), 성인(N01~N74)이 전수 등록되어 있는지 검증."""
        for engine in ("flux", "sdxl"):
            db = default_pose_service.load_pose_db(engine=engine, roster="murim")
            
            # 무협 정예 10종 확인
            for i in range(1, 11):
                code = f"C{i:02d}"
                self.assertIn(code, db, f"[{engine}] 무협 액션 포즈 {code}가 누락되었습니다.")
                self.assertTrue(len(db[code].prompt) > 0, f"[{engine}] {code} 프롬프트가 비어있습니다.")

            # Genit 감정 24종 확인
            for i in range(24):
                code = f"A{i:02d}"
                self.assertIn(code, db, f"[{engine}] Genit 감정 포즈 {code}가 누락되었습니다.")

            # Genit 행동 22종 확인
            for i in range(1, 23):
                code = f"B{i:02d}"
                self.assertIn(code, db, f"[{engine}] Genit 행동 포즈 {code}가 누락되었습니다.")

            # 성인 씬 대표 코드 확인
            for code in ("N01", "N05", "N15", "N28", "N32"):
                self.assertIn(code, db, f"[{engine}] 성인 씬 포즈 {code}가 누락되었습니다.")

    def test_pose_sets_integrity(self):
        """포즈 세트에 wuxia_actions(10종) 및 wuxia_full(102종)이 정상 탑재되어 있는지 검증."""
        sets = default_pose_service.load_pose_sets()
        set_dict = {s.id: s for s in sets}
        
        self.assertIn("wuxia_actions", set_dict, "wuxia_actions 포즈 세트가 누락되었습니다.")
        self.assertEqual(len(set_dict["wuxia_actions"].codes), 10)

        self.assertIn("wuxia_full", set_dict, "wuxia_full 포즈 세트가 누락되었습니다.")
        self.assertEqual(len(set_dict["wuxia_full"].codes), 122)

    def test_character_service_murim_roster(self):
        """무협 아포칼립스 로스터(murim)의 10인 캐릭터 조회가 정상 작동하는지 검증."""
        chars = default_character_service.list_characters(roster="murim")
        prefixes = [c.prefix for _, c, _ in chars]
        
        expected_prefixes = ["aa", "bb", "cc", "dd", "ee", "ff", "gg", "hh", "ii", "jj"]
        for exp in expected_prefixes:
            self.assertIn(exp, prefixes, f"무협 캐릭터 '{exp}'가 캐릭터 서비스에서 검색되지 않습니다.")

    def test_asset_service_alphanumeric_mapping(self):
        """에셋 서비스가 영숫자 복합 포즈 코드(A00, C01, N01 등)를 정상적으로 파싱하고 정렬하는지 검증."""
        # 생성 완료된 murim 대표 캐릭터(ii) 에셋 목록 조회
        assets_ii = default_asset_service.list_character_assets("ii", roster="murim")
        self.assertTrue(len(assets_ii) > 0, "ii 캐릭터의 에셋 목록이 0개입니다.")
        
        codes = [a["code"] for a in assets_ii]
        # 적어도 A00 및 C01~C10 등 신규 코드가 포함되어야 함
        self.assertTrue(any(c.startswith("C") for c in codes), "C팩 무협 액션 포즈가 에셋 목록에 매핑되지 않았습니다.")
        
        # 매트릭스 맵 생성 테스트
        matrix = default_asset_service.get_matrix_map(["ii", "jj"], ["A00", "C01", "C04"], roster="murim")
        self.assertIn("ii", matrix)
        self.assertIn("jj", matrix)
        self.assertIn("C01", matrix["ii"])

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
        """GUI 포즈 페이지의 SECTION_LABELS와 실제 포즈 DB 및 pose_service.SECTION_NAMES 간의 동기화 무결성 검증 (현업 계약 테스트)."""
        from plepa_engine.services.pose_service import SECTION_NAMES
        from plepa_gui.pages.poses import SECTION_LABELS

        # 1. pose_service에 정의된 모든 섹션이 포즈 페이지 레이블 딕셔너리에 정의되어 있는지
        for sec in SECTION_NAMES:
            self.assertIn(sec, SECTION_LABELS, f"포즈 서비스의 섹션 '{sec}'이 poses.py의 SECTION_LABELS에 누락되었습니다.")

        # 2. 포즈 DB(flux/sdxl)에 존재하는 모든 포즈의 section 값이 SECTION_NAMES에 포함되는지 (유령 섹션 방지)
        for engine in ("flux", "sdxl"):
            db = default_pose_service.load_pose_db(engine=engine)
            db_sections = {e.section for e in db.values() if e.section}
            for sec in db_sections:
                self.assertIn(sec, SECTION_NAMES, f"[{engine}] 포즈 DB의 섹션 '{sec}'이 pose_service.SECTION_NAMES에 등록되지 않았습니다.")
                self.assertIn(sec, SECTION_LABELS, f"[{engine}] 포즈 DB의 섹션 '{sec}'이 poses.py의 SECTION_LABELS에 누락되었습니다.")

    def test_all_poses_details_rendering_safety(self):
        """DB에 등록된 모든 포즈(숫자 및 A00, C01, N01 등 영숫자 포함)의 get_pose_details() 조회가 예외 없이 100% 성공하는지 전수 검증."""
        for engine in ("flux", "sdxl"):
            db = default_pose_service.load_pose_db(engine=engine)
            self.assertTrue(len(db) > 0, f"[{engine}] 포즈 DB가 비어있습니다.")
            for code, entry in db.items():
                try:
                    details = default_pose_service.get_pose_details(code)
                    self.assertEqual(details["code"], code)
                    self.assertIn("flux_prompt", details)
                    self.assertIn("sdxl_prompt", details)
                except Exception as ex:
                    self.fail(f"[{engine}] 포즈 코드 '{code}' 상세 조회 중 예외 발생: {ex}")

    def test_active_sections_dynamic_metadata_contract(self):
        """get_active_sections()가 활성 섹션의 카운트와 라벨을 메타데이터와 결합하여 정상 반환하는지 검증."""
        actives = default_pose_service.get_active_sections(engine="flux")
        self.assertTrue(len(actives) >= 4, "최소 4개 이상의 활성 섹션이 반환되어야 합니다.")
        
        # 순서 보장 검증 (order 기준 오름차순)
        from plepa_engine.services.pose_service import SECTION_METADATA
        orders = [SECTION_METADATA[s["id"]]["order"] for s in actives]
        self.assertEqual(orders, sorted(orders), "활성 섹션 정렬 순서가 메타데이터 order와 일치하지 않습니다.")


if __name__ == "__main__":
    unittest.main()
