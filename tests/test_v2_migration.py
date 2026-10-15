import unittest
from plepa_engine.services.pose_service import default_pose_service
from plepa_engine.prompt_builder import is_nude_pose, resolve_pose_outfit_slot
from plepa_engine.models import CharacterAppearance, CharacterConfig

class TestV2MigrationIntegrity(unittest.TestCase):
    """V2 대역 개편 및 무결성 단위 테스트."""

    def setUp(self):
        self.db = default_pose_service.load_pose_db(engine="sdxl", roster="campus")

    def test_romance_nude_poses_detection(self):
        """061, 062, 063 (romance 탈의 씬)이 정확히 is_nude == True 및 nude 슬롯으로 판정되는지 검증."""
        for code in ("061", "062", "063"):
            self.assertIn(code, self.db, f"포즈 코드 '{code}'가 DB에 존재해야 합니다.")
            entry = self.db[code]
            self.assertEqual(entry.section, "romance")
            self.assertEqual(entry.required_outfit, "nude")
            self.assertTrue(is_nude_pose(entry), f"포즈 {code}는 is_nude_pose == True여야 합니다.")
            self.assertEqual(resolve_pose_outfit_slot(entry), "nude")

    def test_romance_dressed_pose_detection(self):
        """060 (romance 딥키스 착의 씬)은 required_outfit == 'default'이며 is_nude == False여야 함."""
        entry = self.db["060"]
        self.assertEqual(entry.section, "romance")
        self.assertEqual(entry.required_outfit, "default")
        self.assertFalse(is_nude_pose(entry))
        self.assertEqual(resolve_pose_outfit_slot(entry), "default")

    def test_adult_dressed_scenes_detection(self):
        """
        성인 섹션(h_scenes, special_h, scenes_otokonoko, special_otokonoko) 내부의 착의 씬들은
        'required_outfit: default'가 우선 적용되어 is_nude == False(의상 유지)로 작동하는지 검증.
        여성 착의씬: 112, 113, 115, 126, 127, 130
        오토코노코 착의씬: 182, 183, 196, 197, 200
        """
        dressed_codes = ["112", "113", "115", "126", "127", "130", "182", "183", "196", "197", "200"]
        for code in dressed_codes:
            self.assertIn(code, self.db, f"포즈 코드 '{code}'가 DB에 존재해야 합니다.")
            entry = self.db[code]
            self.assertEqual(
                entry.required_outfit, "default",
                f"포즈 {code} ({entry.label})의 required_outfit은 'default'여야 합니다."
            )
            self.assertFalse(
                is_nude_pose(entry),
                f"성인 착의 포즈 {code} ({entry.label})는 is_nude_pose == False여야 합니다 (의상 유지)."
            )
            self.assertEqual(resolve_pose_outfit_slot(entry), "default")

    def test_symmetric_offset_70(self):
        """여성 기본 성인(080~127, 48종)과 오토코노코(150~197, 48종)의 +70 대칭성 검증."""
        for f_num in range(80, 128):
            f_code = f"{f_num:03d}"
            o_code = f"{f_num + 70:03d}"
            self.assertIn(f_code, self.db)
            self.assertIn(o_code, self.db)
            f_entry = self.db[f_code]
            o_entry = self.db[o_code]
            self.assertEqual(f_entry.section, "h_scenes")
            self.assertEqual(o_entry.section, "scenes_otokonoko")

    def test_special_symmetric_offset_70(self):
        """특수 성인 씬 여성(130)과 오토코노코(200)의 +70 대칭성 검증."""
        self.assertIn("130", self.db)
        self.assertIn("200", self.db)
        self.assertEqual(self.db["130"].section, "special_h")
        self.assertEqual(self.db["200"].section, "special_otokonoko")
