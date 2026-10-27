"""
tests/test_v2_migration.py
포즈 DB의 의상 슬롯(required_outfit), 착의/탈의 판정(is_nude_pose),
그리고 여성-오토코노코 +70 거울 대칭 계약을 하드코딩 없이 100% 동적으로 검증하는 테스트.
"""

import unittest
from plepa_engine.services.pose_service import default_pose_service
from plepa_engine.prompt_builder import is_nude_pose, resolve_pose_outfit_slot


ADULT_SECTIONS = {
    "h_scenes",
    "special_h",
    "special_female_h",
    "scenes_otokonoko",
    "special_otokonoko",
    "special_otokonoko_h",
}


class TestV2MigrationIntegrity(unittest.TestCase):
    """데이터 주도형(Contract-Driven) 포즈 대역 및 의상 슬롯 무결성 테스트."""

    def setUp(self):
        self.db = default_pose_service.load_pose_db(engine="sdxl", roster="campus")

    def test_romance_nude_poses_detection(self):
        """romance 섹션에서 required_outfit == 'nude'로 선언된 모든 포즈가 is_nude == True로 판정되는지 동적 검증."""
        nude_romance = [
            entry for entry in self.db.values()
            if entry.section == "romance" and entry.required_outfit == "nude"
        ]
        self.assertGreater(len(nude_romance), 0, "romance 섹션에 nude 슬롯 포즈가 최소 1개 이상 존재해야 합니다.")
        for entry in nude_romance:
            self.assertTrue(
                is_nude_pose(entry),
                f"romance 탈의 포즈 {entry.code} ({entry.label})는 is_nude_pose == True여야 합니다.",
            )
            self.assertEqual(resolve_pose_outfit_slot(entry), "nude")

    def test_romance_dressed_pose_detection(self):
        """romance 섹션에서 required_outfit == 'default'로 선언된 모든 포즈가 is_nude == False로 판정되는지 동적 검증."""
        dressed_romance = [
            entry for entry in self.db.values()
            if entry.section == "romance" and entry.required_outfit == "default"
        ]
        self.assertGreater(len(dressed_romance), 0, "romance 섹션에 default 착의 포즈가 최소 1개 이상 존재해야 합니다.")
        for entry in dressed_romance:
            self.assertFalse(
                is_nude_pose(entry),
                f"romance 착의 포즈 {entry.code} ({entry.label})는 is_nude_pose == False여야 합니다.",
            )
            self.assertEqual(resolve_pose_outfit_slot(entry), "default")

    def test_adult_dressed_scenes_detection(self):
        """
        성인 섹션 내부에서 required_outfit이 비탈의('default', 'wedding' 등)로 선언된 모든 포즈들을
        동적으로 수집하여, is_nude_pose == False(의상 유지)로 작동하는지 전수 계약 검증.
        """
        dressed_adult_entries = [
            entry for entry in self.db.values()
            if entry.section in ADULT_SECTIONS
            and entry.required_outfit
            and entry.required_outfit != "nude"
        ]
        self.assertGreater(len(dressed_adult_entries), 0, "성인 섹션 내 착의 포즈가 최소 1개 이상 존재해야 합니다.")

        for entry in dressed_adult_entries:
            self.assertFalse(
                is_nude_pose(entry),
                f"성인 착의 포즈 {entry.code} ({entry.label}, slot={entry.required_outfit})는 is_nude_pose == False여야 합니다.",
            )
            self.assertEqual(resolve_pose_outfit_slot(entry), entry.required_outfit)

    def test_symmetric_offset_70(self):
        """h_scenes 섹션에 존재하는 모든 숫자 포즈 코드에 대해 +70 대칭 코드가 scenes_otokonoko에 실존하는지 동적 검증."""
        h_scene_entries = [
            entry for entry in self.db.values()
            if entry.section == "h_scenes" and entry.code.isdigit()
        ]
        self.assertGreater(len(h_scene_entries), 0, "h_scenes 포즈가 존재해야 합니다.")

        for f_entry in h_scene_entries:
            f_num = int(f_entry.code)
            o_code = f"{f_num + 70:03d}"
            self.assertIn(
                o_code,
                self.db,
                f"여성 성인 포즈 {f_entry.code}({f_entry.label})에 대응하는 +70 오토코노코 코드 {o_code}가 DB에 존재해야 합니다.",
            )
            o_entry = self.db[o_code]
            self.assertEqual(o_entry.section, "scenes_otokonoko")

    def test_special_event_adult_slots_symmetry(self):
        """로스터 특수 성인 씬(special_female_h / special_h)의 모든 코드가 +70 오토코노코 대칭 슬롯을 보유하는지 동적 검증."""
        special_female = [
            entry for entry in self.db.values()
            if entry.section in ("special_h", "special_female_h") and entry.code.isdigit()
        ]
        self.assertGreater(len(special_female), 0, "특수 성인 씬이 최소 1개 이상 존재해야 합니다.")

        for f_entry in special_female:
            f_num = int(f_entry.code)
            o_code_v3 = f"{f_num + 70:03d}"
            self.assertIn(
                o_code_v3,
                self.db,
                f"특수 포즈 {f_entry.code}에 대응하는 +70 대칭 포즈 {o_code_v3}가 로드되어야 합니다.",
            )
            self.assertIn(self.db[o_code_v3].section, ("special_otokonoko", "special_otokonoko_h"))
            self.assertEqual(f_entry.required_outfit, self.db[o_code_v3].required_outfit)


if __name__ == "__main__":
    unittest.main()
